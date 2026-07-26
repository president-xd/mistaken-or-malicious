"""Tests for the seven problems found by reading a real run's output.

Each test names the symptom that was actually seen on screen, so if one fails
later you can tell what a user would notice.

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import unittest

from p2p.agent import (PeerAgent, make_clients, normalize_belief, parse_belief,
                       top_answer)
from p2p.config import Config, Question
from p2p.network import Network
from p2p.prompts import belief_line, reconsider
from p2p.trust import NEUTRAL, consist_score, stretch_exact


class Scripted:
    """An agent that says exactly what we tell it to."""

    parsed, retried = True, False
    belief_ignored = belief_disagrees = False

    def __init__(self, name, answers, wrong_answer=""):
        self.name, self.script = name, list(answers)
        self.wrong_answer = wrong_answer
        self.turn, self.answer, self.belief = 0, "", {}

    def argument(self):
        return ""

    async def solve(self, question):
        self.answer = self.script[0]
        self.turn = 1
        self.belief = {self.answer: 1.0}
        return f"ANSWER: {self.answer}"

    async def reconsider(self, question, heard, trust=None):
        was = self.answer
        self.answer = self.script[min(self.turn, len(self.script) - 1)]
        self.turn += 1
        self.belief = {self.answer: 1.0}
        return f"ANSWER: {self.answer}", self.answer != was, ""

    async def reset(self):
        self.turn, self.answer = 0, ""


def run_network(agents, **overrides):
    settings = dict(questions=[Question("Q", "yes")], agents=len(agents),
                    rounds=3, topology="mesh", trust=True, scoring="answer",
                    trust_carry_over=False)
    settings.update(overrides)
    cfg = Config(**settings)
    net = Network(cfg, client=None, force_trust=True, agents=agents)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        asyncio.run(net.run_question(cfg.questions[0]))
    return net, out.getvalue()


# ------------------------------------------------- 1. the consist neutral bug

class TestNeutralConsistIsNotPunished(unittest.TestCase):
    """SYMPTOM: in the first discussion round every agent showed
    `consist 0.000`, including agents that had never changed their answer.

    CAUSE: with no previous round, consist_score returns the neutral 0.5, and
    stretch_exact maps 0.5 to 0.0 - the worst possible score.
    """

    def test_the_underlying_trap_still_exists(self):
        """stretch_exact is right for a similarity, wrong for 'no data'."""
        self.assertEqual(consist_score([1.0, 0.0], None), NEUTRAL)
        self.assertEqual(stretch_exact(NEUTRAL), 0.0)

    def test_round_one_consist_is_neutral_not_zero(self):
        agents = {n: Scripted(n, ["yes"] * 3) for n in ("A", "B", "C")}
        net, _ = run_network(agents)
        first = net.history[0]
        # Recover the score used, by inverting the trust update.
        beta, start = net.cfg.trust_memory, net.cfg.start_trust
        score = (first["A"]["B"] - beta * start) / (1 - beta)
        # All three agree and none has moved, so agree = 1 and anomaly = 0.
        # With consist neutral at 0.5 the score is (1 + 0.5 + 1)/3 = 0.8333.
        # Under the old bug consist was 0.0 and the score was 0.6667.
        self.assertAlmostEqual(score, (1.0 + NEUTRAL + 1.0) / 3, places=6)
        self.assertNotAlmostEqual(score, 2 / 3, places=6)

    def test_later_rounds_still_measure_consistency_properly(self):
        """The fix must not switch the signal off after round one."""
        agents = {"A": Scripted("A", ["yes", "yes", "yes"]),
                  "B": Scripted("B", ["yes", "yes", "yes"]),
                  "C": Scripted("C", ["yes", "yes", "yes"])}
        net, _ = run_network(agents, rounds=4)
        beta = net.cfg.trust_memory
        later = net.history[-1]["A"]["B"]
        before = net.history[-2]["A"]["B"]
        score = (later - beta * before) / (1 - beta)
        # Everyone agrees and nobody moved, so every signal is at its best.
        self.assertAlmostEqual(score, 1.0, places=6)


# ------------------------------------------- 2. the belief example being copied

class TestBeliefExampleUsesRealAnswers(unittest.TestCase):
    """SYMPTOM: agents wrote `BELIEF: {"first": 1.0, "second": 0.0}`. Those
    keys matched no real answer, so the whole line was thrown away and
    replaced with certainty in the stated answer - silently."""

    def test_the_example_names_the_real_answers(self):
        line = belief_line(["408", "347"])
        self.assertIn('"408": 0.7', line)
        self.assertIn('"347": 0.3', line)

    def test_the_placeholder_words_are_gone(self):
        line = belief_line(["408", "347"])
        for copied in ('"first"', '"second"'):
            self.assertNotIn(copied, line)

    def test_the_whole_prompt_no_longer_offers_them(self):
        prompt = reconsider("Q", "408", "- Agent_B answered: 347",
                            ["408", "347"])
        self.assertNotIn('"first"', prompt)
        self.assertNotIn('"second"', prompt)

    def test_one_option_and_no_options_do_not_crash(self):
        self.assertIn('"408"', belief_line(["408"]))
        self.assertIsInstance(belief_line([]), str)


class TestADiscardedBeliefIsReported(unittest.TestCase):
    """Even with the better prompt a model may still copy something. When the
    belief cannot be used, the confidence shown is OUR fallback, so say so."""

    def make(self, text, candidates, answer):
        agent = PeerAgent.__new__(PeerAgent)
        agent.answer, agent.reasoning = answer, text
        agent._candidates, agent.parsed = candidates, True
        agent._absorb(text)
        return agent

    def test_unusable_keys_are_flagged(self):
        agent = self.make('BELIEF: {"first": 1.0, "second": 0.0}\nANSWER: 408',
                          ["408", "347"], "408")
        self.assertTrue(agent.belief_ignored)

    def test_real_keys_are_not_flagged(self):
        agent = self.make('BELIEF: {"347": 0.3, "408": 0.7}\nANSWER: 408',
                          ["408", "347"], "408")
        self.assertFalse(agent.belief_ignored)

    def test_no_belief_line_at_all_is_not_flagged(self):
        """Nothing was thrown away, so there is nothing to warn about."""
        agent = self.make("ANSWER: 408", ["408", "347"], "408")
        self.assertFalse(agent.belief_ignored)


# ------------------------------------ 3. answer contradicting its own belief

class TestAnswerAgainstBelief(unittest.TestCase):
    """SYMPTOM: `ANSWER: 347` while `BELIEF: {"347":0,"408":1}`. Both were
    stored and never compared."""

    def make(self, text, candidates, answer):
        agent = PeerAgent.__new__(PeerAgent)
        agent.answer, agent.reasoning = answer, text
        agent._candidates, agent.parsed = candidates, True
        agent._absorb(text)
        return agent

    def test_a_contradiction_is_caught(self):
        agent = self.make('BELIEF: {"347":0,"408":1}\nANSWER: 347',
                          ["347", "408"], "347")
        self.assertTrue(agent.belief_disagrees)
        self.assertEqual(top_answer(agent.belief), "408")

    def test_agreement_is_not_flagged(self):
        agent = self.make('BELIEF: {"347":0.2,"408":0.8}\nANSWER: 408',
                          ["347", "408"], "408")
        self.assertFalse(agent.belief_disagrees)

    def test_a_split_belief_is_not_a_contradiction(self):
        """Leaning slightly the other way is a real opinion, not a mistake."""
        agent = self.make('BELIEF: {"347":0.45,"408":0.55}\nANSWER: 347',
                          ["347", "408"], "347")
        self.assertFalse(agent.belief_disagrees)


# ------------------------------------------------- 4. a liar that will not lie

class TestLiarRefusalIsDetected(unittest.TestCase):
    """SYMPTOM: the liar answered 408, the correct answer, and the run still
    called it [LIAR] and reported the experiment as though an attack had
    happened."""

    def test_a_refusing_liar_is_recorded_and_named(self):
        agents = {"A": Scripted("A", ["408"] * 3),
                  "B": Scripted("B", ["408"] * 3, wrong_answer="347"),
                  "C": Scripted("C", ["408"] * 3)}
        net, out = run_network(agents, attackers=1)
        net.liars = ["B"]
        net, out = run_network(agents, attackers=1)
        # Force B to be the liar regardless of seat choice, then re-report.
        net.liars = ["B"]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            net._report("B")
        self.assertIn("NOT attacking", buffer.getvalue())
        self.assertIn("B", net.liar_refused)

    def test_a_liar_that_does_lie_is_not_flagged(self):
        agents = {"A": Scripted("A", ["408"] * 3),
                  "B": Scripted("B", ["347"] * 3, wrong_answer="347"),
                  "C": Scripted("C", ["408"] * 3)}
        net, _ = run_network(agents, attackers=1)
        net.liars = ["B"]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            net._report("B")
        self.assertNotIn("NOT attacking", buffer.getvalue())
        self.assertEqual(net.liar_refused, set())


# ------------------------------------------------- 5. the seed reaching the model

class TestSeedReachesTheModel(unittest.TestCase):
    """SYMPTOM: two runs with the same config and the same seed gave different
    answers in round 1. The seed only ever chose which agent was the liar."""

    def test_each_agent_gets_its_own_seed(self):
        """A single shared seed would make every honest agent produce the same
        reply, so the network would hold one opinion under several names."""
        clients = make_clients("qwen2.5:14b", "ollama", seed=7, count=3)
        seeds = [c._raw_config["options"]["seed"] for c in clients]
        self.assertEqual(seeds, [7, 8, 9])

    def test_no_seed_means_no_seed_is_sent(self):
        clients = make_clients("qwen2.5:14b", "ollama", seed=None, count=2)
        for client in clients:
            self.assertFalse(client._raw_config.get("options"))

    def test_the_same_seed_builds_the_same_clients(self):
        first = make_clients("qwen2.5:14b", "ollama", seed=1, count=3)
        second = make_clients("qwen2.5:14b", "ollama", seed=1, count=3)
        self.assertEqual([c._raw_config["options"]["seed"] for c in first],
                         [c._raw_config["options"]["seed"] for c in second])


if __name__ == "__main__":
    unittest.main(verbosity=2)
