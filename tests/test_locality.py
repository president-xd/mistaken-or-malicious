"""Does an agent's trust use only what that agent can actually hear?

WHY THIS MATTERS.

The whole point of the project is a network with NO orchestrator. Every agent
is supposed to work from what it can hear and nothing else. If the trust update
quietly uses the whole network's answers, then something with a global view is
doing the work, and the result is not really peer to peer.

In a mesh this is invisible, because everyone hears everyone anyway. It only
shows up in the other topologies.

These tests RECORD what the code does today. Two of them are marked as a known
limitation rather than a pass, because they describe behaviour we have found
and reported, not behaviour we want.

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import unittest

from p2p.config import Config, Question
from p2p.network import Network


class Fixed:
    """An agent that always says one thing, so only the maths can vary."""

    parsed, retried = True, False

    def __init__(self, name, answer):
        self.name, self.answer = name, answer
        self.belief = {answer: 1.0}

    def argument(self):
        return ""

    async def solve(self, question):
        return f"ANSWER: {self.answer}"

    async def reconsider(self, question, heard, trust=None):
        return f"ANSWER: {self.answer}", False, ""

    async def reset(self):
        pass


def run_line(answers):
    """A line: Agent_A - Agent_B - Agent_C.

    Agent_A hears only Agent_B. Agent_C hears only Agent_B. The two ends
    cannot hear each other.
    """
    cfg = Config(questions=[Question("Q1", "yes")], agents=3, rounds=2,
                 topology="line", trust=True, scoring="answer",
                 sharpen=False, trust_carry_over=False)
    agents = {name: Fixed(name, answer) for name, answer in answers.items()}
    net = Network(cfg, client=None, force_trust=True, agents=agents)
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(net.run_question(cfg.questions[0]))
    return net


class TestWhoCanHearWhom(unittest.TestCase):
    """First, prove the topology is what we think it is."""

    def test_the_ends_of_a_line_cannot_hear_each_other(self):
        net = run_line({"Agent_A": "yes", "Agent_B": "yes", "Agent_C": "yes"})
        self.assertEqual(net.adjacency["Agent_A"], ["Agent_B"])
        self.assertEqual(net.adjacency["Agent_C"], ["Agent_B"])
        self.assertNotIn("Agent_C", net.adjacency["Agent_A"])

    def test_an_agent_only_scores_peers_it_can_hear(self):
        """Agent_A keeps a trust score for Agent_B and for nobody else."""
        net = run_line({"Agent_A": "yes", "Agent_B": "yes", "Agent_C": "yes"})
        self.assertEqual(list(net.trust["Agent_A"]), ["Agent_B"])


class TestKnownLimitationGlobalScoring(unittest.TestCase):
    """KNOWN LIMITATION, recorded on purpose.

    The behaviour score for an agent is worked out against EVERY other agent
    in the network, not against the ones the listener can hear. So Agent_A's
    trust in Agent_B moves when Agent_C changes its answer, even though
    Agent_A cannot hear Agent_C at all.

    These tests fail if somebody makes the scoring local, which is the fix.
    Change them then - do not delete them.
    """

    def test_trust_changes_because_of_an_agent_you_cannot_hear(self):
        # Only Agent_C's answer differs between the two runs. Agent_A cannot
        # hear Agent_C. If scoring were local, Agent_A's trust in Agent_B
        # would be identical in both.
        same = run_line({"Agent_A": "yes", "Agent_B": "yes", "Agent_C": "yes"})
        differs = run_line({"Agent_A": "yes", "Agent_B": "yes", "Agent_C": "no"})

        a_trusts_b_when_c_agrees = same.trust["Agent_A"]["Agent_B"]
        a_trusts_b_when_c_differs = differs.trust["Agent_A"]["Agent_B"]

        self.assertNotAlmostEqual(
            a_trusts_b_when_c_agrees, a_trusts_b_when_c_differs, places=4,
            msg="scoring has become local - good. Update this test.")

    def test_every_listener_holds_the_same_trust_in_a_speaker(self):
        """Because the score is global, w_ij does not really depend on i.

        The formula is written w_ij, which suggests each listener forms its
        own view. In practice all listeners that can hear the same speaker end
        up with exactly the same number, so the trust matrix is a list in
        disguise. Worth knowing before quoting the matrix as a result.
        """
        net = run_line({"Agent_A": "yes", "Agent_B": "no", "Agent_C": "yes"})
        views_of_b = [row["Agent_B"] for row in net.trust.values()
                      if "Agent_B" in row]
        self.assertGreater(len(views_of_b), 1, "need at least two listeners")
        for value in views_of_b[1:]:
            self.assertAlmostEqual(views_of_b[0], value, places=6)


class TestMeshIsUnaffected(unittest.TestCase):
    """In a mesh everyone hears everyone, so global and local are the same
    thing. This is why the limitation never showed up in our main results."""

    def test_mesh_scoring_is_already_local(self):
        cfg = Config(questions=[Question("Q1", "yes")], agents=3, rounds=2,
                     topology="mesh", trust=True, scoring="answer")
        agents = {n: Fixed(n, a) for n, a in
                  (("Agent_A", "yes"), ("Agent_B", "no"), ("Agent_C", "yes"))}
        net = Network(cfg, client=None, force_trust=True, agents=agents)
        with contextlib.redirect_stdout(io.StringIO()):
            asyncio.run(net.run_question(cfg.questions[0]))
        for listener in net.names:
            heard = set(net.adjacency[listener])
            others = set(net.names) - {listener}
            self.assertEqual(heard, others,
                             "in a mesh, what you hear IS everyone else")


if __name__ == "__main__":
    unittest.main(verbosity=2)
