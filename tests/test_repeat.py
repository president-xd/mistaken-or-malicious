"""Tests for repeating a run, and for showing the workings behind the ASR.

Two problems are covered here.

1. ONE RUN IS NOT A RESULT.
   With 3 honest agents, one agent changing its mind moves a score by 33
   percentage points. `repeats` runs the whole experiment several times and
   reports the average with the spread beside it.

2. THE ATTACK SUCCESS RATE HIDES ITS DENOMINATOR.
   The rate is "of the honest agents that started right, how many were
   turned". The group it is measured over changes from run to run, so two
   runs can end with exactly the same answers and still show different
   rates. We now report the counts next to the rate.

Run:  python -m unittest discover -s tests
"""

import asyncio
import contextlib
import io
import math
import unittest
from unittest import mock

from p2p import metrics, repeat
from p2p.config import Config, Question
from p2p.network import run_network


# ---------------------------------------------------------------- the maths

class TestMeanAndSpread(unittest.TestCase):
    """Checked against sums done by hand, so the maths is proved not assumed."""

    def test_mean(self):
        self.assertEqual(repeat.mean([1, 2, 3, 4, 5]), 3.0)

    def test_mean_of_nothing_is_none(self):
        self.assertIsNone(repeat.mean([]))

    def test_spread_by_hand(self):
        # values 1..5, mean 3. Gaps from the mean: 2, 1, 0, 1, 2.
        # Squared: 4, 1, 0, 1, 4  ->  total 10.  10 / (5 - 1) = 2.5.
        # Spread = square root of 2.5 = 1.5811...
        self.assertAlmostEqual(repeat.spread([1, 2, 3, 4, 5]),
                               math.sqrt(2.5), places=10)

    def test_identical_runs_have_no_spread(self):
        # Not exactly 0: 0.4 cannot be held exactly in binary, so the sum
        # leaves a speck about a hundred million times smaller than anything
        # we ever print. Rounded for display it is 0.000.
        self.assertAlmostEqual(repeat.spread([0.4, 0.4, 0.4]), 0.0, places=12)

    def test_one_run_has_no_spread_to_report(self):
        """You cannot say how far apart the runs were from a single run."""
        self.assertIsNone(repeat.spread([0.5]))


class TestCombine(unittest.TestCase):

    def setUp(self):
        self.runs = [
            {"honest_accuracy": 1.0, "attack_success_rate": 0.0},
            {"honest_accuracy": 0.0, "attack_success_rate": 1.0},
            {"honest_accuracy": 0.5, "attack_success_rate": 0.5},
        ]

    def test_reports_average_lowest_highest(self):
        out = repeat.combine(self.runs)["honest_accuracy"]
        self.assertAlmostEqual(out["mean"], 0.5)
        self.assertEqual(out["lowest"], 0.0)
        self.assertEqual(out["highest"], 1.0)
        self.assertEqual(out["runs"], 3)

    def test_a_missing_measure_is_none_not_zero(self):
        """A measure nobody could compute must not be averaged in as 0."""
        self.assertIsNone(repeat.combine(self.runs)["trust_separation"])

    def test_skips_runs_where_the_measure_was_missing(self):
        runs = [{"honest_accuracy": 1.0}, {"honest_accuracy": None},
                {"honest_accuracy": 0.0}]
        out = repeat.combine(runs)["honest_accuracy"]
        self.assertEqual(out["runs"], 2)
        self.assertAlmostEqual(out["mean"], 0.5)

    def test_means_only_flattens_it_back(self):
        flat = repeat.means_only(repeat.combine(self.runs))
        self.assertAlmostEqual(flat["honest_accuracy"], 0.5)
        self.assertIsNone(flat["trust_separation"])


class TestOverlap(unittest.TestCase):
    """Is a difference between two setups bigger than the noise?"""

    def test_separate_ranges_do_not_overlap(self):
        low = {"lowest": 0.0, "highest": 0.3}
        high = {"lowest": 0.6, "highest": 0.9}
        self.assertFalse(repeat.overlaps(low, high))

    def test_touching_ranges_do_overlap(self):
        low = {"lowest": 0.0, "highest": 0.6}
        high = {"lowest": 0.6, "highest": 0.9}
        self.assertTrue(repeat.overlaps(low, high))

    def test_missing_data_counts_as_overlapping(self):
        """When we cannot tell, we must not claim a real difference."""
        self.assertTrue(repeat.overlaps(None, {"lowest": 0.1, "highest": 0.2}))


# ------------------------------------------------- the workings behind ASR

class TestStartedRight(unittest.TestCase):

    def test_counts_only_honest_agents_that_began_correct(self):
        first = {"A": "Algeria", "B": "Algeria", "C": "Nigeria", "L": "Nigeria"}
        self.assertEqual(
            sorted(metrics.started_right(first, ["L"], "Algeria")), ["A", "B"])

    def test_summarise_reports_the_counts(self):
        first = {"A": "Algeria", "B": "Algeria", "C": "Nigeria", "L": "Nigeria"}
        final = {"A": "Nigeria", "B": "Algeria", "C": "Nigeria", "L": "Nigeria"}
        out = metrics.summarise(first, final, {}, ["L"], "Algeria", wrong="Nigeria")
        self.assertEqual(out["honest_agents"], 3)
        self.assertEqual(out["started_right"], 2)
        self.assertEqual(out["turned"], 1)
        self.assertAlmostEqual(out["attack_success_rate"], 0.5)

    def test_attack_rate_denominator_is_agents_not_already_on_attack_answer(self):
        """The designated attack answer and eligible group are explicit."""
        final = {"B": "Algeria", "C": "Nigeria", "D": "Nigeria", "L": "Nigeria"}

        without = metrics.summarise(
            {"B": "Algeria", "C": "Algeria", "D": "Democratic Republic of Congo",
             "L": "Nigeria"}, final, {}, ["L"], "Algeria", wrong="Nigeria")
        with_trust = metrics.summarise(
            {"B": "Algeria", "C": "Algeria", "D": "Algeria", "L": "Nigeria"},
            final, {}, ["L"], "Algeria", wrong="Nigeria")

        self.assertEqual(without["honest_accuracy"], with_trust["honest_accuracy"])
        self.assertAlmostEqual(without["attack_success_rate"], 2 / 3)
        self.assertAlmostEqual(with_trust["attack_success_rate"], 2 / 3)
        self.assertEqual(without["attack_eligible"], 3)
        self.assertEqual(with_trust["attack_eligible"], 3)

    def test_counts_are_averaged_over_questions(self):
        rows = [{k: None for k in metrics.AVERAGED} | {"started_right": 2},
                {k: None for k in metrics.AVERAGED} | {"started_right": 3}]
        self.assertAlmostEqual(metrics.average_runs(rows)["started_right"], 2.5)


# ------------------------------------- saying so when nothing was measured

class TestEmptyExperimentWarning(unittest.TestCase):
    """A run where the attack never turned anybody is not a perfect result.

    It is an experiment where nothing happened. Both halves score full accuracy
    and 0% attack success, and the table looks like a win. The program must say
    so, or a strong model quietly turns every comparison into a null result.
    """

    def show(self, without, with_trust):
        from p2p import logging_utils as log
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            log.comparison(without, with_trust)
        return out.getvalue()

    def side(self, **changes):
        base = {"honest_accuracy": 1.0, "attack_success_rate": 0.0,
                "trust_separation": 0.0, "attacker_influence": 0.25,
                "honest_agents": 3, "started_right": 3, "turned": 0}
        return base | changes

    def test_warns_when_nobody_was_ever_turned(self):
        text = self.show(self.side(), self.side(trust_separation=0.6))
        self.assertIn("no decision or diffusion damage", text)

    def test_stays_quiet_when_the_attack_worked(self):
        text = self.show(self.side(),
                         self.side(turned=1, attack_success_rate=0.33))
        self.assertNotIn("measured nothing", text)

    def test_stays_quiet_when_the_baseline_was_attacked(self):
        """Only one side needs to show damage for the comparison to be real."""
        text = self.show(self.side(turned=2, attack_success_rate=0.67),
                         self.side())
        self.assertNotIn("measured nothing", text)

    def test_stays_quiet_when_nobody_started_right(self):
        """A different problem, with a different message - do not confuse them."""
        text = self.show(self.side(started_right=0, honest_accuracy=0.0),
                         self.side(started_right=0, honest_accuracy=0.0))
        self.assertNotIn("measured nothing", text)

    def test_stays_quiet_when_the_counts_are_missing(self):
        without = {"honest_accuracy": 1.0, "attack_success_rate": 0.0,
                   "trust_separation": 0.0, "attacker_influence": 0.25}
        self.assertNotIn("measured nothing", self.show(without, dict(without)))


# ------------------------------------------------------------- end to end

class FakeAgent:
    """Stands in for a real agent so the loop can run with no model."""

    parsed, retried = True, False

    def __init__(self, name, client, role="honest", wrong_answer="",
                 agreeableness="", persuasion=""):
        self.name, self.role = name, role
        self.answer = wrong_answer if role == "liar" else "yes"
        self.belief = {self.answer: 1.0}

    def argument(self):
        return ""

    async def solve(self, question):
        return f"ANSWER: {self.answer}"

    async def reconsider(self, question, heard, trust=None):
        return f"ANSWER: {self.answer}", False, ""

    async def reset(self):
        pass


class FakeClient:
    async def close(self):
        pass


def run_quietly(cfg):
    with mock.patch("p2p.network.PeerAgent", FakeAgent), \
         mock.patch("p2p.network.make_model_client",
                    lambda model, provider="ollama": FakeClient()), \
         contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(run_network(cfg))


class TestRepeatsRunEndToEnd(unittest.TestCase):

    def setUp(self):
        self.cfg = Config(
            questions=[Question("Q1", "yes"), Question("Q2", "yes")],
            agents=3, rounds=2, trust=True, scoring="answer",
            attackers=1, attacker_answer="no", repeats=3)

    def test_the_whole_experiment_runs_the_requested_number_of_times(self):
        seen = []
        real = repeat.combine

        def spy(runs):
            seen.append(len(runs))
            return real(runs)

        with mock.patch("p2p.network.repeat.combine", spy):
            run_quietly(self.cfg)
        self.assertIn(3, seen)

    def test_one_repeat_still_works(self):
        run_quietly(Config(questions=self.cfg.questions, agents=3, rounds=2,
                           trust=True, scoring="answer", attackers=1,
                           attacker_answer="no", repeats=1))

    def test_default_is_a_single_run(self):
        self.assertEqual(Config().repeats, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
