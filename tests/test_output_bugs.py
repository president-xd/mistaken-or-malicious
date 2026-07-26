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
from p2p import logging_utils as log
from p2p.network import Network
from p2p.prompts import belief_line, reconsider
from p2p.roles import check_places, choose_seats
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


# ------------------------------- 5. influence counting peers nobody listens to

class TestTrustFloorSilencesProperly(unittest.TestCase):
    """SYMPTOM: with trust_floor on, an agent printed `listens to: nobody` and
    the very next line credited its peers with a share of its attention.

    CAUSE: the floor decided who was HEARD, but influence and the metrics were
    computed from the whole trust table. A peer that had been shut out still
    counted toward `attacker_influence`, one of the four headline measures, so
    the defence looked weaker than it was.
    """

    def build(self, floor):
        agents = {"Agent_A": Scripted("Agent_A", ["yes"] * 3),
                  "Agent_B": Scripted("Agent_B", ["no"] * 3),
                  "Agent_C": Scripted("Agent_C", ["yes"] * 3)}
        net, _ = run_network(agents, trust_floor=floor, attackers=1)
        net.liars = ["Agent_B"]
        return net

    def test_a_silenced_peer_gets_no_share_of_the_attention(self):
        net = self.build(0.45)
        self.assertNotIn("Agent_B", net.heard_by("Agent_A"))
        self.assertNotIn("Agent_B", net.influence()["Agent_A"])

    def test_the_shares_still_add_up_to_one(self):
        net = self.build(0.45)
        for listener, row in net.influence().items():
            if row:
                self.assertAlmostEqual(sum(row.values()), 1.0, places=9)

    def test_the_default_floor_changes_nothing(self):
        """trust_floor is 0 by default, so ordinary runs must be untouched."""
        net = self.build(0.0)
        self.assertEqual(set(net.influence()["Agent_A"]),
                         set(net.trust["Agent_A"]))

    def test_heard_trust_is_the_full_table_when_the_floor_is_off(self):
        net = self.build(0.0)
        self.assertEqual(net.heard_trust(), net.trust)

    def test_everyone_silenced_leaves_no_shares_rather_than_crashing(self):
        net = self.build(0.99)
        for listener in net.names:
            self.assertEqual(net.heard_by(listener), [])
            self.assertEqual(net.influence()[listener], {})


# ------------------------------------- 6. seat settings that quietly do nothing

class TestBadSeatSettingsAreReported(unittest.TestCase):
    """SYMPTOM: none. That is the problem.

    Asking for 2 attackers at seats "1,1" gives ONE liar. Asking for seat 99
    in a 3-agent network gives a RANDOM seat. Both run happily and produce
    numbers that look fine, so you never learn you measured something else.
    """

    NAMES = ["Agent_A", "Agent_B", "Agent_C"]

    def problems(self, count, places):
        return check_places(self.NAMES, count, places)

    def test_a_repeated_seat_loses_a_liar(self):
        found = " ".join(self.problems(2, "1,1"))
        self.assertIn("more than once", found)
        self.assertEqual(len(choose_seats(self.NAMES, 2, "1,1", "mesh", 1)), 1)

    def test_a_seat_that_does_not_exist_is_named(self):
        found = " ".join(self.problems(1, "99"))
        self.assertIn("does not exist", found)
        self.assertIn("RANDOM", found)

    def test_a_seat_that_is_not_a_number_is_named(self):
        self.assertIn("not a whole number", " ".join(self.problems(1, "-1")))

    def test_a_misspelled_keyword_is_caught(self):
        """'centre' is not 'center', and silently became random."""
        found = " ".join(self.problems(1, "centre"))
        self.assertIn("not understood", found)
        self.assertIn("RANDOM", found)

    def test_the_count_disagreeing_with_the_list_is_named(self):
        self.assertIn("seat list wins", " ".join(self.problems(2, "0")))

    def test_good_settings_produce_no_noise(self):
        for count, places in ((2, "0,2"), (1, "0"), (1, "random"),
                              (1, "center"), (1, "leaf"), (0, "0,1")):
            self.assertEqual(self.problems(count, places), [],
                             f"{places!r} should be silent")


# ---------------------------------------------- 7. things printed badly or not at all

class TestTheReportReadsProperly(unittest.TestCase):
    """Three faults found by reading a real 2-attacker run."""

    def shown(self, scores, use_trust=True, refused=None, liars=("B",)):
        agents = {"A": Scripted("A", ["yes"]), "B": Scripted("B", ["no"])}
        for a in agents.values():
            a.answer = a.script[0]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            log.final_report(agents, list(liars), "yes", scores, use_trust,
                             refused)
        return out.getvalue()

    BASE = {"honest_accuracy": 1.0, "attack_success_rate": 0.0,
            "trust_separation": 0.0, "attacker_influence": 0.25,
            "separation_margin": -0.067, "false_alarm": 0.067,
            "still_moving": 0.02, "matches_theory": 0.01}

    def test_a_liar_never_caught_reads_as_english(self):
        """It used to print 'caught the liar in never round(s)'."""
        text = self.shown({**self.BASE, "detection_round": None})
        self.assertNotIn("in never round", text)
        self.assertIn("never", text)

    def test_a_liar_that_was_caught_names_the_round(self):
        text = self.shown({**self.BASE, "detection_round": 2})
        self.assertIn("in round 2", text)

    def test_a_liar_that_did_not_lie_is_labelled_as_such(self):
        """'correct [LIAR]' on its own reads like a contradiction."""
        text = self.shown({**self.BASE, "detection_round": None},
                          refused={"B"})
        self.assertIn("LIAR - did not lie", text)

    def test_a_liar_that_did_lie_keeps_the_plain_label(self):
        text = self.shown({**self.BASE, "detection_round": 1}, refused=set())
        self.assertIn("[LIAR]", text)
        self.assertNotIn("did not lie", text)

    def test_every_liar_refusing_says_the_numbers_mean_nothing(self):
        text = self.shown({**self.BASE, "detection_round": None},
                          refused={"B"}, liars=("B",))
        self.assertIn("no liar actually lied", text)
        self.assertIn("say nothing about", text)

    def test_no_refusal_prints_no_note(self):
        text = self.shown({**self.BASE, "detection_round": 1}, refused=set())
        self.assertNotIn("CAREFUL", text)


class TestRefusalIsReportedOncePerQuestion(unittest.TestCase):
    """The same sentence three rounds running is noise, and noise is what
    stops people reading warnings at all."""

    def test_a_steady_refusal_is_said_once(self):
        agents = {"A": Scripted("A", ["yes"] * 4),
                  "B": Scripted("B", ["yes"] * 4),
                  "C": Scripted("C", ["yes"] * 4)}
        net, text = run_network(agents, rounds=4, attackers=1,
                                questions=[Question("Q", "yes", "no")])
        net.liars = ["B"]
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            asyncio.run(net.run_question(net.cfg.questions[0]))
        self.assertEqual(buffer.getvalue().count("NOT attacking"), 1)

    def test_it_can_be_said_again_if_the_liar_resumes_then_stops(self):
        net = Network(Config(questions=[Question("Q", "yes", "no")], agents=3,
                             rounds=2, trust=True),
                      client=None, force_trust=True,
                      agents={n: Scripted(n, ["yes"]) for n in "ABC"})
        net.liars = ["B"]
        net.agents["B"].wrong_answer = "no"
        net.agents["B"].answer = "yes"          # refusing
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            net._report("B")
            net.agents["B"].answer = "no"       # back to attacking
            net._report("B")
            net.agents["B"].answer = "yes"      # stopped again
            net._report("B")
        self.assertEqual(buffer.getvalue().count("NOT attacking"), 2)


# ------------------------------------- 8. warnings that fire at the wrong time

class TestLiarRefusalWarningIsScoped(unittest.TestCase):
    """Two ways the refusal warning could cry wolf."""

    def test_it_is_cleared_between_questions(self):
        """Refusing on question 1 says nothing about question 2. Without this
        one refusal marked the liar as broken for the rest of the run."""
        agents = {"A": Scripted("A", ["yes"] * 3),
                  "B": Scripted("B", ["yes"] * 3),
                  "C": Scripted("C", ["yes"] * 3)}
        net, _ = run_network(agents, attackers=1,
                             questions=[Question("Q", "yes", "no")])

        # A refusal recorded on an earlier question must not survive into the
        # next one. "Ghost" is not a liar here, so nothing can put it back -
        # if it is still there afterwards, the set was never cleared.
        net.liar_refused.add("Ghost")
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(net.run_question(net.cfg.questions[0]))
        self.assertNotIn("Ghost", net.liar_refused)

    def test_a_liar_that_will_not_lie_is_still_recorded(self):
        agents = {"A": Scripted("A", ["yes"] * 3),
                  "B": Scripted("B", ["yes"] * 3),
                  "C": Scripted("C", ["yes"] * 3)}
        net, _ = run_network(agents, attackers=1,
                             questions=[Question("Q", "yes", "no")])
        net.liars = ["A"]
        # run_question sets wrong_answer from the question, so set it after.
        net.agents["A"].wrong_answer = "no"
        with contextlib.redirect_stdout(io.StringIO()):
            net._report("A")
        self.assertIn("A", net.liar_refused)

    def test_a_sleeping_sleeper_is_not_called_a_refuser(self):
        """While asleep the liar is GIVEN the correct answer to defend, so
        answering correctly is the intended behaviour, not a refusal."""
        agents = {"A": Scripted("A", ["yes"] * 3, wrong_answer="yes"),
                  "B": Scripted("B", ["yes"] * 3),
                  "C": Scripted("C", ["yes"] * 3)}
        net, _ = run_network(agents, attackers=1)
        net.liars, net.asleep = ["A"], True
        agents["A"].answer = "no"        # deviating, but it is asleep
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            net._report("A")
        self.assertNotIn("NOT attacking", buffer.getvalue())


# ------------------------------------------------- 8. the seed reaching the model

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
