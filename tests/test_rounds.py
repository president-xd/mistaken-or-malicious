"""Dynamic tests for the round loop: updates must be SIMULTANEOUS, not gossip.

These drive the real discussion loop (`network._answer_one`) with recording
agents instead of live models, so the scheduling behaviour is tested directly
and deterministically -- no Ollama required.

The property under test: within one discussion round, every agent must see the
state as it was at the START of that round. An agent that takes its turn later
must NOT see an answer produced earlier in the same round.

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import unittest

from p2p.config import Config, Question
from p2p.network import Network


class RecordingAgent:
    """Stands in for a PeerAgent. Returns scripted answers and records what it
    was shown on every discussion turn."""

    def __init__(self, name, script):
        self.name = name
        self.script = script       # answer to hold after each turn, in order
        self.answer = ""
        self.belief = {}
        self.parsed = True
        self.retried = False
        self.turn = 0
        self.seen = []             # one dict per discussion turn: {peer: answer}

    def argument(self):
        return f"{self.name} working"

    async def solve(self, question):
        self.answer = self.script[0]
        return f"ANSWER: {self.answer}"

    async def reconsider(self, question, heard, trust=None):
        # Record exactly what this agent was handed this turn.
        self.seen.append({n: a for n, (a, _) in heard.items()})
        self.turn += 1
        previous = self.answer
        if self.turn < len(self.script):
            self.answer = self.script[self.turn]
        return f"ANSWER: {self.answer}", self.answer != previous, ""

    async def reset(self):
        self.answer, self.turn, self.seen = "", 0, []


def run_round_loop(scripts, topo, rounds, share="answer"):
    """Run the real discussion loop over recording agents; return them by name."""
    agents = {n: RecordingAgent(n, scripts[n]) for n in scripts}
    cfg = Config(questions=[Question("Q")], rounds=rounds, agents=len(agents),
                 topology=topo, share=share)
    net = Network(cfg, client=None, agents=agents)
    # The loop logs verbosely; keep test output clean.
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(net.run_question(Question("Q")))
    return agents


class TestSimultaneousUpdate(unittest.TestCase):

    def test_later_agent_does_not_see_earlier_agents_new_answer(self):
        """The decisive test. Agent_A changes 1 -> 10 in round 2. Agent_C takes
        its turn AFTER Agent_A, so under gossip it would see 10. Under a
        simultaneous update it must still see 1."""
        agents = run_round_loop(
            {"Agent_A": ["1", "10"], "Agent_B": ["2", "20"], "Agent_C": ["3", "30"]},
            topo="mesh", rounds=2)

        seen_by_c = agents["Agent_C"].seen[0]
        self.assertEqual(seen_by_c["Agent_A"], "1",
                         "Agent_C saw Agent_A's SAME-ROUND answer -> gossip, not simultaneous")
        self.assertEqual(seen_by_c["Agent_B"], "2")

    def test_every_agent_sees_the_same_value_for_a_given_peer(self):
        """Round consistency: in one round, all listeners of a peer must have
        been handed an identical value for it."""
        agents = run_round_loop(
            {f"Agent_{c}": [c, c * 2] for c in "ABCD"},
            topo="mesh", rounds=2)

        for peer in agents:
            values = {a.seen[0][peer] for a in agents.values() if peer in a.seen[0]}
            self.assertLessEqual(len(values), 1,
                                 f"{peer} was reported with different values in one round: {values}")

    def test_no_first_mover_disadvantage(self):
        """Agent_A goes first. Its view must be as fresh as everyone else's --
        i.e. also the round-start state, not a staler one."""
        agents = run_round_loop(
            {"Agent_A": ["1", "10"], "Agent_B": ["2", "20"], "Agent_C": ["3", "30"]},
            topo="mesh", rounds=2)

        self.assertEqual(agents["Agent_A"].seen[0], {"Agent_B": "2", "Agent_C": "3"})
        # Agent_C, going last, sees the same generation of data.
        self.assertEqual(agents["Agent_C"].seen[0], {"Agent_A": "1", "Agent_B": "2"})

    def test_information_travels_exactly_one_hop_per_round(self):
        """In a line A-B-C, A's round-1 answer must reach C in round 3, never
        in round 2 -- under gossip it could arrive a round early."""
        agents = run_round_loop(
            {"Agent_A": ["A1", "A2", "A3"],
             "Agent_B": ["B1", "B2", "B3"],
             "Agent_C": ["C1", "C2", "C3"]},
            topo="line", rounds=3)

        # line: C hears only B.
        self.assertEqual(agents["Agent_C"].seen[0], {"Agent_B": "B1"})
        self.assertEqual(agents["Agent_C"].seen[1], {"Agent_B": "B2"})

    def test_next_round_does_see_previous_round_updates(self):
        """Simultaneity must not freeze the whole run: round 3 sees round 2's
        results."""
        agents = run_round_loop(
            {"Agent_A": ["1", "10", "100"], "Agent_B": ["2", "20", "200"]},
            topo="mesh", rounds=3)

        self.assertEqual(agents["Agent_B"].seen[0]["Agent_A"], "1")   # round 2
        self.assertEqual(agents["Agent_B"].seen[1]["Agent_A"], "10")  # round 3

    def test_share_both_reasoning_is_also_snapshotted(self):
        agents = run_round_loop(
            {"Agent_A": ["1", "10"], "Agent_B": ["2", "20"]},
            topo="mesh", rounds=2, share="both")
        self.assertEqual(agents["Agent_B"].seen[0]["Agent_A"], "1")


class TestRoundBudget(unittest.TestCase):

    def test_rounds_counts_total_turns_including_the_guess(self):
        """rounds: 4 = 1 independent guess + 3 discussion turns."""
        agents = run_round_loop(
            {"Agent_A": ["1", "2", "3", "4"], "Agent_B": ["9", "8", "7", "6"]},
            topo="mesh", rounds=4)
        self.assertEqual(agents["Agent_A"].turn, 3)

    def test_rounds_one_means_no_discussion(self):
        agents = run_round_loop(
            {"Agent_A": ["1"], "Agent_B": ["2"]}, topo="mesh", rounds=1)
        self.assertEqual(agents["Agent_A"].seen, [])

    def test_early_stop_when_nobody_changes(self):
        """Scripts that never change -> loop must stop after the first
        discussion round instead of spending the budget."""
        agents = run_round_loop(
            {"Agent_A": ["1", "1", "1", "1"], "Agent_B": ["1", "1", "1", "1"]},
            topo="mesh", rounds=4)
        self.assertEqual(agents["Agent_A"].turn, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
