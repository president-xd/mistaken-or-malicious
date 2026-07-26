"""What the trust formula can and cannot do.

These tests do not check for bugs. They record, in code, the real limits of the
method, measured with agents whose answers we control exactly. If someone later
changes the formula, these tests will show whether the limits moved.

Every case here was found by testing. The reasoning is in README.md, under
"Things worth knowing".

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import unittest

from p2p.config import Config, Question
from p2p.network import Network


class Fixed:
    """An agent that always gives the same answer, so we can set up any case."""

    def __init__(self, name, answer):
        self.name, self.answer = name, answer
        self.belief = {answer: 1.0}
        self.parsed, self.retried = True, False

    def argument(self):
        return ""

    async def solve(self, question):
        return f"ANSWER: {self.answer}"

    async def reconsider(self, question, heard, trust=None):
        return f"ANSWER: {self.answer}", False, ""

    async def reset(self):
        pass


def play(answers, liars, rounds=3):
    """Run one question with fixed answers. Returns (scores, average trust)."""
    agents = {n: Fixed(n, a) for n, a in answers.items()}
    cfg = Config(questions=[Question("Q", "Mercury")], agents=len(agents),
                 rounds=rounds, trust=True, scoring="answer",
                 attackers=len(liars))
    net = Network(cfg, None, agents=agents)
    net.liars = list(liars)
    with contextlib.redirect_stdout(io.StringIO()):
        scores = asyncio.run(net.run_question(Question("Q", "Mercury")))
    trust = {}
    for name in agents:
        got = [row[name] for row in net.trust.values() if name in row]
        trust[name] = sum(got) / len(got) if got else 0.0
    return scores, trust


class TestWhatWorks(unittest.TestCase):

    def test_a_lone_liar_is_caught(self):
        """The case the method is built for: honest agents agree, the liar does
        not. It should be trusted less and given a smaller share of the talking."""
        scores, trust = play({"A": "Mercury", "B": "Mercury", "C": "Venus"}, ["C"])
        self.assertLess(trust["C"], trust["A"])
        self.assertGreater(scores["separation_margin"], 0)
        self.assertLess(scores["attacker_influence"], scores["equal_share"])

    def test_honest_agents_are_treated_the_same(self):
        """No honest agent should be singled out. This is the check the formula
        document asks for."""
        _, trust = play({"A": "Mercury", "B": "Mercury", "C": "Venus"}, ["C"])
        self.assertAlmostEqual(trust["A"], trust["B"], places=6)


class TestWhatDoesNotWork(unittest.TestCase):
    """Real limits. These are not bugs. They are things the method cannot do,
    and anyone using the results needs to know about them."""

    def test_it_cannot_help_once_everyone_believes_the_lie(self):
        """If the liar has already convinced the whole group, nothing looks odd
        any more, so the formula has nothing to find. Trust stays equal."""
        scores, trust = play({"A": "Venus", "B": "Venus", "C": "Venus"}, ["C"])
        self.assertAlmostEqual(trust["A"], trust["C"], places=6)
        self.assertAlmostEqual(scores["separation_margin"], 0.0, places=6)

    def test_it_cannot_work_when_nobody_agrees_with_anybody(self):
        """The small-model case. If honest agents cannot even agree with each
        other, everyone looks like an outlier and everyone is punished equally.
        The formula needs an honest majority that actually agrees."""
        scores, trust = play({"A": "Mercury", "B": "Venus", "C": "Mars"}, ["C"])
        self.assertAlmostEqual(trust["A"], trust["C"], places=6)
        self.assertAlmostEqual(scores["separation_margin"], 0.0, places=6)
        # And everyone ends up with LOW trust, not high.
        self.assertLess(trust["A"], 0.5)

    def test_it_gets_it_backwards_when_the_liars_are_the_majority(self):
        """The most serious limit. Two liars that agree with each other look
        like the group, so they GAIN trust, and the one honest agent is
        punished. The defence helps the attackers here.

        This matches the warning in the formula document: without knowing the
        right answer, nothing can tell which side is honest.
        """
        scores, trust = play({"A": "Venus", "B": "Venus", "C": "Mercury"},
                             ["A", "B"])
        self.assertGreater(trust["A"], trust["C"])          # liar trusted more
        self.assertLess(scores["separation_margin"], 0)      # not a clean split
        self.assertGreater(scores["attacker_influence"],
                           scores["equal_share"])            # liars talk MORE


class TestTheseLimitsAreVisibleInTheNumbers(unittest.TestCase):
    """A user must be able to SEE that a run hit one of the limits above,
    instead of reading a good-looking number that means nothing."""

    def test_a_failed_split_shows_as_a_negative_worst_gap(self):
        scores, _ = play({"A": "Venus", "B": "Venus", "C": "Mercury"}, ["A", "B"])
        self.assertIsNotNone(scores["separation_margin"])
        self.assertLess(scores["separation_margin"], 0)

    def test_no_information_shows_as_a_zero_gap(self):
        scores, _ = play({"A": "Venus", "B": "Venus", "C": "Venus"}, ["C"])
        self.assertAlmostEqual(scores["separation_margin"], 0.0, places=6)

    def test_a_working_run_shows_a_positive_gap(self):
        scores, _ = play({"A": "Mercury", "B": "Mercury", "C": "Venus"}, ["C"])
        self.assertGreater(scores["separation_margin"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
