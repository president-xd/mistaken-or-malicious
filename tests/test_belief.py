"""Tests for belief distributions.

An agent holds a probability distribution over the answers alive in its
neighbourhood, not just one answer string. That is what makes a PARTIAL
concession visible: shifting 30% of your weight toward a peer while still
answering the same thing.

Run:  python -m unittest discover -s tests
"""

import unittest

from p2p.agent import (belief_shift, normalize_belief, parse_belief, top_answer)


class TestParseBelief(unittest.TestCase):

    def test_plain_belief_line(self):
        self.assertEqual(
            parse_belief('reasoning\nBELIEF: {"408": 0.7, "347": 0.3}\nANSWER: 408'),
            {"408": 0.7, "347": 0.3})

    def test_json_on_the_following_line(self):
        # Real run: the model wrote "Belief:" then put the object underneath.
        self.assertEqual(
            parse_belief('CONVINCED_BY: Agent_A\nBelief:\n{"408": 0.6, "347": 0.4}\n'
                         'ANSWER: 408'),
            {"408": 0.6, "347": 0.4})

    def test_json_spanning_multiple_lines(self):
        self.assertEqual(parse_belief('BELIEF:\n{"a": 0.5,\n "b": 0.5}'),
                         {"a": 0.5, "b": 0.5})

    def test_missing_line_gives_empty(self):
        self.assertEqual(parse_belief("ANSWER: 408"), {})

    def test_malformed_json_gives_empty(self):
        self.assertEqual(parse_belief('BELIEF: {408: oops}'), {})

    def test_last_belief_wins(self):
        text = 'BELIEF: {"1": 1.0}\nrethinking\nBELIEF: {"2": 1.0}'
        self.assertEqual(parse_belief(text), {"2": 1.0})


class TestNormalizeBelief(unittest.TestCase):

    def setUp(self):
        self.cands = ["408", "347"]

    def test_rescales_to_sum_one(self):
        got = normalize_belief({"408": 3, "347": 1}, self.cands, "408")
        self.assertAlmostEqual(sum(got.values()), 1.0)
        self.assertAlmostEqual(got["408"], 0.75)

    def test_matches_keys_loosely(self):
        # The model may write "408." or "  408" -- still the same answer.
        got = normalize_belief({"408.": 1.0}, self.cands, "408")
        self.assertAlmostEqual(got["408"], 1.0)

    def test_unknown_keys_are_ignored(self):
        got = normalize_belief({"408": 1.0, "9999": 5.0}, self.cands, "408")
        self.assertAlmostEqual(got["408"], 1.0)
        self.assertNotIn("9999", got)

    def test_negative_weights_are_dropped(self):
        got = normalize_belief({"408": 1.0, "347": -5}, self.cands, "408")
        self.assertAlmostEqual(got["347"], 0.0)

    def test_missing_belief_falls_back_to_certainty(self):
        # The safety property: a model that skips BELIEF still yields a valid
        # distribution, so a run can never be broken by the extra line.
        got = normalize_belief({}, self.cands, "408")
        self.assertAlmostEqual(got["408"], 1.0)
        self.assertAlmostEqual(got["347"], 0.0)

    def test_answer_is_always_a_candidate(self):
        got = normalize_belief({}, ["347"], "408")
        self.assertIn("408", got)

    def test_no_candidates_gives_empty(self):
        self.assertEqual(normalize_belief({}, [], ""), {})


class TestBeliefShift(unittest.TestCase):

    def test_no_movement(self):
        b = {"408": 0.6, "347": 0.4}
        self.assertAlmostEqual(belief_shift(b, b), 0.0)

    def test_partial_concession_is_measured(self):
        """The headline capability: the top answer never changes, yet 30% of
        the agent's weight moved to a peer. An answer-only system sees nothing."""
        before = {"408": 1.0, "347": 0.0}
        after = {"408": 0.7, "347": 0.3}
        self.assertAlmostEqual(belief_shift(before, after), 0.3)
        self.assertEqual(top_answer(before), top_answer(after))   # answer unchanged

    def test_full_switch(self):
        self.assertAlmostEqual(
            belief_shift({"408": 1.0, "347": 0.0}, {"408": 0.0, "347": 1.0}), 1.0)

    def test_handles_new_candidates(self):
        shift = belief_shift({"408": 1.0}, {"408": 0.5, "84": 0.5})
        self.assertAlmostEqual(shift, 0.5)


class TestConcessionDetectedInTheLoop(unittest.TestCase):
    """End-to-end: the real discussion loop must SEE and REPORT a partial
    concession -- an agent that keeps its answer but moves belief to a peer."""

    class Conceder:
        """Answers 408 throughout, but slides 30% of its weight onto 347."""

        def __init__(self, name, answer, beliefs):
            self.name, self.answer = name, answer
            self.beliefs = list(beliefs)
            self.belief = self.beliefs[0]
            self.parsed, self.retried, self.turn = True, False, 0

        def argument(self):
            return ""

        async def solve(self, q):
            return f"ANSWER: {self.answer}"

        async def reconsider(self, q, heard):
            self.turn += 1
            if self.turn < len(self.beliefs):
                self.belief = self.beliefs[self.turn]
            return f"ANSWER: {self.answer}", False, ""

        async def reset(self):
            pass

    def test_partial_concession_is_logged(self):
        import asyncio, contextlib, io
        from p2p import topology
        from p2p.config import Config
        from p2p.network import _answer_one

        agents = {
            "Agent_A": self.Conceder("Agent_A", "408",
                                     [{"408": 1.0, "347": 0.0},
                                      {"408": 0.7, "347": 0.3}]),
            "Agent_B": self.Conceder("Agent_B", "347",
                                     [{"347": 1.0}, {"347": 1.0}]),
        }
        names = list(agents)
        cfg = Config(questions=["Q"], rounds=2, num_agents=2, topology="mesh")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            asyncio.run(_answer_one(cfg, agents, topology.build("mesh", names),
                                    names, "Q"))
        log = out.getvalue()

        self.assertIn("shifted 30%", log)       # the size of the concession
        self.assertIn("kept its answer", log)   # ...without switching
        self.assertIn("347", log)               # toward the right peer answer
        self.assertNotIn("Agent_A CHANGED", log)


class TestTopAnswer(unittest.TestCase):

    def test_picks_the_heaviest(self):
        self.assertEqual(top_answer({"408": 0.6, "347": 0.4}), "408")

    def test_empty(self):
        self.assertEqual(top_answer({}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
