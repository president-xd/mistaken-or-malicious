"""Tests that a comparison is fair.

When `compare_baseline` is on we run the same test twice: once without trust,
once with it. The two halves MUST be scored on exactly the same questions.
Warm-up questions are not scored, so they have to be removed from BOTH halves,
even though only the trust half actually uses them.

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import unittest

from p2p.config import Config, Question
from p2p.network import Network, _run_all


class ScriptedAgent:
    """A stand-in agent that always gives the same answer."""

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


def run(cfg, use_trust):
    agents = {"Agent_A": ScriptedAgent("Agent_A", "yes"),
              "Agent_B": ScriptedAgent("Agent_B", "no")}
    net = Network(cfg, client=None, force_trust=use_trust, agents=agents)
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(_run_all(net, cfg, None))
    return net


class TestWarmUpIsFair(unittest.TestCase):

    def setUp(self):
        self.cfg = Config(
            questions=[Question("Q1", "yes"), Question("Q2", "yes"),
                       Question("Q3", "yes")],
            agents=2, rounds=2, warmup=1, trust=True, scoring="answer")

    def test_both_halves_score_the_same_number_of_questions(self):
        """The bug this catches: without trust the warm-up question was still
        scored, so the two halves were not comparable."""
        without = run(self.cfg, use_trust=False)
        with_trust = run(self.cfg, use_trust=True)
        self.assertEqual(len(without.rows), len(with_trust.rows))

    def test_the_warm_up_question_is_not_scored(self):
        net = run(self.cfg, use_trust=True)
        self.assertEqual(len(net.rows), 2)   # 3 questions, 1 used for warm-up

    def test_no_warm_up_means_every_question_is_scored(self):
        cfg = Config(questions=self.cfg.questions, agents=2, rounds=2,
                     warmup=0, trust=True, scoring="answer")
        self.assertEqual(len(run(cfg, use_trust=True).rows), 3)


class TestParallelChangesNothing(unittest.TestCase):
    """Running agents together must give exactly the same answers as running
    them one at a time. If it does not, the snapshot is leaking."""

    def test_same_result_either_way(self):
        questions = [Question("Q1", "yes"), Question("Q2", "yes")]
        one_at_a_time = run(Config(questions=questions, agents=2, rounds=3,
                                   trust=True, scoring="answer", parallel=False),
                            use_trust=True)
        together = run(Config(questions=questions, agents=2, rounds=3,
                              trust=True, scoring="answer", parallel=True),
                       use_trust=True)
        self.assertEqual(one_at_a_time.rows, together.rows)
        self.assertEqual(one_at_a_time.trust, together.trust)


if __name__ == "__main__":
    unittest.main(verbosity=2)
