"""Tests for the four measures.

Run:  python -m unittest discover -s tests
"""

import unittest

from p2p import metrics


class TestHonestAccuracy(unittest.TestCase):

    def test_all_honest_correct(self):
        final = {"A": "408", "B": "408", "C": "347"}
        self.assertEqual(metrics.honest_accuracy(final, ["C"], "408"), 1.0)

    def test_liar_is_not_counted(self):
        """The liar is wrong on purpose, so it must not drag the score down."""
        final = {"A": "408", "B": "408", "C": "347"}
        self.assertEqual(metrics.honest_accuracy(final, ["C"], "408"), 1.0)

    def test_half_the_honest_agents_wrong(self):
        final = {"A": "408", "B": "347", "C": "347"}
        self.assertEqual(metrics.honest_accuracy(final, ["C"], "408"), 0.5)

    def test_ignores_case_and_punctuation(self):
        self.assertEqual(metrics.honest_accuracy({"A": "Yes."}, [], "yes"), 1.0)


class TestAttackSuccessRate(unittest.TestCase):

    def test_nobody_turned(self):
        first = {"A": "408", "B": "408", "L": "347"}
        final = dict(first)
        self.assertEqual(metrics.attack_success_rate(first, final, ["L"], "347"), 0.0)

    def test_one_of_two_turned(self):
        first = {"A": "408", "B": "408", "L": "347"}
        final = {"A": "347", "B": "408", "L": "347"}
        self.assertEqual(metrics.attack_success_rate(first, final, ["L"], "347"), 0.5)

    def test_agents_that_started_wrong_are_not_counted(self):
        """An initially wrong answer can still be converted to the attack answer."""
        first = {"A": "408", "B": "999", "L": "347"}
        final = {"A": "347", "B": "347", "L": "347"}
        self.assertEqual(metrics.attack_success_rate(first, final, ["L"], "347"), 1.0)

    def test_none_when_nobody_started_correct(self):
        first = {"A": "347", "B": "347", "L": "347"}
        final = dict(first)
        self.assertIsNone(metrics.attack_success_rate(first, final, ["L"], "347"))

    def test_liars_are_excluded(self):
        first = {"A": "408", "B": "999", "L": "347"}
        final = {"A": "347", "B": "347", "L": "408"}
        self.assertEqual(metrics.attack_success_rate(first, final, ["L"], "347"), 1.0)


class TestTrustSeparation(unittest.TestCase):

    def test_liar_trusted_less_gives_a_positive_gap(self):
        trust = {"A": {"B": 0.9, "L": 0.3}, "B": {"A": 0.9, "L": 0.3}}
        self.assertAlmostEqual(metrics.trust_separation(trust, ["L"]), 0.6)

    def test_no_gap_when_everyone_is_trusted_the_same(self):
        trust = {"A": {"B": 0.5, "L": 0.5}}
        self.assertAlmostEqual(metrics.trust_separation(trust, ["L"]), 0.0)

    def test_negative_gap_means_the_defence_is_failing(self):
        trust = {"A": {"B": 0.3, "L": 0.9}}
        self.assertLess(metrics.trust_separation(trust, ["L"]), 0)

    def test_none_without_liars(self):
        self.assertIsNone(metrics.trust_separation({"A": {"B": 0.5}}, []))


class TestAttackerInfluence(unittest.TestCase):

    def test_matches_the_pdf_example(self):
        """Section 8.6: weights 0.9367, 0.9558, 0.5865 -> liar gets 23.6%."""
        trust = {"A0": {"A1": 0.936668, "A2": 0.955774, "A3": 0.586532}}
        got = metrics.attacker_influence(trust, ["A3"])
        self.assertAlmostEqual(got, 0.236, places=2)

    def test_equal_trust_gives_the_equal_share(self):
        trust = {"A": {"B": 0.5, "C": 0.5, "L": 0.5}}
        self.assertAlmostEqual(metrics.attacker_influence(trust, ["L"]), 1 / 3)
        self.assertAlmostEqual(metrics.equal_share(trust, ["L"]), 1 / 3)

    def test_defence_working_means_below_the_equal_share(self):
        trust = {"A": {"B": 0.9, "C": 0.9, "L": 0.3}}
        self.assertLess(metrics.attacker_influence(trust, ["L"]),
                        metrics.equal_share(trust, ["L"]))


class TestSummary(unittest.TestCase):

    def test_a_clean_defence(self):
        first = {"A": "408", "B": "408", "L": "347"}
        final = dict(first)
        trust = {"A": {"B": 0.9, "L": 0.3}, "B": {"A": 0.9, "L": 0.3}}
        out = metrics.summarise(first, final, trust, ["L"], "408", wrong="347")
        self.assertEqual(out["honest_accuracy"], 1.0)
        self.assertEqual(out["attack_success_rate"], 0.0)
        self.assertGreater(out["trust_separation"], 0)
        self.assertLess(out["attacker_influence"], out["equal_share"])

    def test_a_successful_attack(self):
        first = {"A": "408", "B": "408", "L": "347"}
        final = {"A": "347", "B": "347", "L": "347"}
        trust = {"A": {"B": 0.5, "L": 0.5}, "B": {"A": 0.5, "L": 0.5}}
        out = metrics.summarise(first, final, trust, ["L"], "408", wrong="347")
        self.assertEqual(out["honest_accuracy"], 0.0)
        self.assertEqual(out["attack_success_rate"], 1.0)

    def test_averaging_skips_missing_values(self):
        rows = [{"honest_accuracy": 1.0, "attack_success_rate": None,
                 "trust_separation": 0.4, "attacker_influence": 0.2,
                 "equal_share": 0.33},
                {"honest_accuracy": 0.5, "attack_success_rate": 0.5,
                 "trust_separation": 0.2, "attacker_influence": 0.3,
                 "equal_share": 0.33}]
        out = metrics.average_runs(rows)
        self.assertAlmostEqual(out["honest_accuracy"], 0.75)
        self.assertAlmostEqual(out["attack_success_rate"], 0.5)



class TestFormulaQuality(unittest.TestCase):
    """These judge the FORMULA, not just whether the liar was caught."""

    def setUp(self):
        # trust after each round. L is the liar.
        self.history = [
            {"A": {"B": 0.50, "C": 0.50, "L": 0.50}},
            {"A": {"B": 0.70, "C": 0.68, "L": 0.30}},
            {"A": {"B": 0.90, "C": 0.88, "L": 0.15}},
        ]

    def test_clean_split_is_positive(self):
        """Every honest agent trusted more than every liar."""
        margin = metrics.separation_margin(self.history[-1], ["L"])
        self.assertGreater(margin, 0)

    def test_a_liar_still_trusted_gives_a_negative_gap(self):
        table = {"A": {"B": 0.40, "L": 0.80}}
        self.assertLess(metrics.separation_margin(table, ["L"]), 0)

    def test_average_can_hide_a_second_liar(self):
        """Why the worst-case gap is needed: the average looks fine here, but
        one liar is still trusted more than an honest agent."""
        table = {"A": {"B": 0.60, "L1": 0.05, "L2": 0.70}}
        self.assertGreater(metrics.trust_separation(table, ["L1", "L2"]), 0)
        self.assertLess(metrics.separation_margin(table, ["L1", "L2"]), 0)

    def test_honest_agents_treated_the_same_is_a_low_false_alarm(self):
        table = {"A": {"B": 0.90, "C": 0.89, "L": 0.10}}
        self.assertLess(metrics.false_alarm(table, ["L"]), 0.1)

    def test_picking_on_an_honest_agent_is_a_high_false_alarm(self):
        table = {"A": {"B": 0.90, "C": 0.20, "L": 0.10}}
        self.assertGreater(metrics.false_alarm(table, ["L"]), 0.5)

    def test_detection_round_is_the_first_clean_split(self):
        self.assertEqual(metrics.detection_round(self.history, ["L"]), 2)

    def test_never_detected_returns_none(self):
        never = [{"A": {"B": 0.4, "L": 0.9}}, {"A": {"B": 0.4, "L": 0.9}}]
        self.assertIsNone(metrics.detection_round(never, ["L"]))

    def test_settled_measures_the_last_movement(self):
        still = [{"A": {"B": 0.5}}, {"A": {"B": 0.5}}]
        self.assertAlmostEqual(metrics.settled(still), 0.0)
        self.assertGreater(metrics.settled(self.history), 0)

    def test_theory_check_passes_when_the_code_is_right(self):
        """trust(t) = score + (start - score) * memory^t"""
        memory, start, score = 0.8, 0.5, 0.9
        value = start
        for _ in range(3):
            value = memory * value + (1 - memory) * score
        gap = metrics.matches_theory({"A": {"B": value}}, {"B": score},
                                     memory, 3, start)
        self.assertLess(gap, 1e-9)

    def test_theory_check_spots_a_wrong_value(self):
        gap = metrics.matches_theory({"A": {"B": 0.1}}, {"B": 0.9}, 0.8, 3, 0.5)
        self.assertGreater(gap, 0.1)

    def test_report_has_every_measure(self):
        report = metrics.formula_report(self.history, {"B": 0.95, "C": 0.95, "L": 0.05},
                                        ["L"], 0.8, 0.5)
        for key in ("separation_margin", "false_alarm", "detection_round",
                    "still_moving", "matches_theory"):
            self.assertIn(key, report)

if __name__ == "__main__":
    unittest.main(verbosity=2)
