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
        first = {"A": "408", "B": "408"}
        final = {"A": "408", "B": "408"}
        self.assertEqual(metrics.attack_success_rate(first, final, [], "408"), 0.0)

    def test_one_of_two_turned(self):
        first = {"A": "408", "B": "408"}
        final = {"A": "408", "B": "347"}
        self.assertEqual(metrics.attack_success_rate(first, final, [], "408"), 0.5)

    def test_agents_that_started_wrong_are_not_counted(self):
        """The measure is about damage done, not about model quality."""
        first = {"A": "408", "B": "999"}
        final = {"A": "347", "B": "347"}
        self.assertEqual(metrics.attack_success_rate(first, final, [], "408"), 1.0)

    def test_none_when_nobody_started_correct(self):
        first = {"A": "1", "B": "2"}
        final = {"A": "3", "B": "4"}
        self.assertIsNone(metrics.attack_success_rate(first, final, [], "408"))

    def test_liars_are_excluded(self):
        first = {"A": "408", "L": "408"}
        final = {"A": "408", "L": "347"}
        self.assertEqual(metrics.attack_success_rate(first, final, ["L"], "408"), 0.0)


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
        final = {"A": "408", "B": "408", "L": "347"}
        trust = {"A": {"B": 0.9, "L": 0.3}, "B": {"A": 0.9, "L": 0.3}}
        out = metrics.summarise(first, final, trust, ["L"], "408")
        self.assertEqual(out["honest_accuracy"], 1.0)
        self.assertEqual(out["attack_success_rate"], 0.0)
        self.assertGreater(out["trust_separation"], 0)
        self.assertLess(out["attacker_influence"], out["equal_share"])

    def test_a_successful_attack(self):
        first = {"A": "408", "B": "408", "L": "347"}
        final = {"A": "347", "B": "347", "L": "347"}
        trust = {"A": {"B": 0.5, "L": 0.5}, "B": {"A": 0.5, "L": 0.5}}
        out = metrics.summarise(first, final, trust, ["L"], "408")
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
