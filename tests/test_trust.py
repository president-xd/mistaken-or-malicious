"""Tests for the dynamic trust formula.

Every expected number comes from the worked example in
`Formula-Explanation.pdf`, section 8. The PDF uses 2-D unit vectors so the
arithmetic can be checked by hand.

One correction: on page 18 the PDF squares 0.646563 as 0.417044. The correct
value is 0.418044. That single digit changes agent 1's numbers very slightly.
We use the corrected values here. Agents 2 and 3 match the PDF exactly.

Run:  python -m unittest discover -s tests
"""

import math
import unittest

from p2p import trust


def unit(degrees):
    """A length-1 vector at the given angle. Matches the PDF's setup."""
    r = math.radians(degrees)
    return [math.cos(r), math.sin(r)]


# The PDF's four agents. Agent 3 is the attacker.
NOW = {0: unit(0), 1: unit(10), 2: unit(20), 3: unit(90)}
BEFORE = {0: unit(0), 1: unit(15), 2: unit(25), 3: unit(10)}


def others(agents, skip):
    return [v for k, v in agents.items() if k != skip]


class TestSimilarity(unittest.TestCase):

    def test_same_vector_is_one(self):
        self.assertAlmostEqual(trust.similarity([1, 0], [1, 0]), 1.0)

    def test_opposite_vector_is_zero(self):
        self.assertAlmostEqual(trust.similarity([1, 0], [-1, 0]), 0.0)

    def test_right_angle_is_a_half(self):
        self.assertAlmostEqual(trust.similarity([1, 0], [0, 1]), 0.5)

    def test_always_between_zero_and_one(self):
        for a in (0, 45, 90, 135, 180, 270):
            for b in (0, 45, 90, 135, 180, 270):
                value = trust.similarity(unit(a), unit(b))
                self.assertGreaterEqual(value, -1e-9)
                self.assertLessEqual(value, 1 + 1e-9)

    def test_empty_vector_is_neutral(self):
        self.assertEqual(trust.similarity([0, 0], [1, 0]), 0.5)


class TestSignals(unittest.TestCase):
    """Section 8.2, 8.3 and 8.4 of the PDF."""

    def test_agree(self):
        expected = {1: 0.954335, 2: 0.991473, 3: 0.586825}  # agent 1 corrected
        for j, want in expected.items():
            got = trust.agree_score(NOW[j], others(NOW, j))
            self.assertAlmostEqual(got, want, places=5, msg=f"agent {j}")

    def test_consist(self):
        expected = {1: 0.998097, 2: 0.998097, 3: 0.586825}
        for j, want in expected.items():
            got = trust.consist_score(NOW[j], BEFORE[j])
            self.assertAlmostEqual(got, want, places=5, msg=f"agent {j}")

    def test_anomaly(self):
        expected = {1: 0.142789, 2: 0.122247, 3: 0.414055}
        for j, want in expected.items():
            got = trust.anomaly_score(NOW[j], others(NOW, j))
            self.assertAlmostEqual(got, want, places=5, msg=f"agent {j}")

    def test_first_round_consistency_is_neutral(self):
        self.assertEqual(trust.consist_score(NOW[1], None), 0.5)

    def test_attacker_stands_out(self):
        """The whole point: agent 3 must look worse than agents 1 and 2."""
        scores = {j: trust.agree_score(NOW[j], others(NOW, j)) for j in (1, 2, 3)}
        self.assertLess(scores[3], scores[1])
        self.assertLess(scores[3], scores[2])


class TestBehaviourScore(unittest.TestCase):
    """Section 8.5."""

    third = (1 / 3, 1 / 3, 1 / 3)

    def score(self, a, c, an):
        return trust.behaviour_score(a, c, an, *self.third)

    def test_pdf_example(self):
        expected = {1: 0.936547, 2: 0.955774, 3: 0.586532}  # agent 1 corrected
        for j, want in expected.items():
            got = self.score(
                trust.agree_score(NOW[j], others(NOW, j)),
                trust.consist_score(NOW[j], BEFORE[j]),
                trust.anomaly_score(NOW[j], others(NOW, j)))
            self.assertAlmostEqual(got, want, places=5, msg=f"agent {j}")

    def test_perfect_agent_scores_one(self):
        self.assertAlmostEqual(self.score(1, 1, 0), 1.0)

    def test_worst_agent_scores_zero(self):
        self.assertAlmostEqual(self.score(0, 0, 1), 0.0)

    def test_the_question_from_the_pdf(self):
        """Section 9: f(1, 0, 1) must be 1/3."""
        self.assertAlmostEqual(self.score(1, 0, 1), 1 / 3, places=4)

    def test_stubborn_neighbour(self):
        """Section 9: f(0, 1, 1) is also 1/3 - disagrees, rigid, alone."""
        self.assertAlmostEqual(self.score(0, 1, 1), 1 / 3, places=4)

    def test_score_never_leaves_zero_to_one(self):
        for a in (0, 0.5, 1):
            for c in (0, 0.5, 1):
                for an in (0, 0.5, 1):
                    value = self.score(a, c, an)
                    self.assertGreaterEqual(value, -1e-9)
                    self.assertLessEqual(value, 1 + 1e-9)


class TestUpdate(unittest.TestCase):
    """Section 8.6."""

    def test_three_rounds_match_the_pdf(self):
        scores = {1: 0.936547, 2: 0.955774, 3: 0.586532}
        weights = {j: 0.5 for j in scores}
        for _ in range(3):
            for j in weights:
                weights[j] = trust.update_trust(weights[j], scores[j], 0.8)
        # PDF: 0.713095 (0.713035 corrected), 0.722418, 0.542227
        self.assertAlmostEqual(weights[1], 0.713035, places=5)
        self.assertAlmostEqual(weights[2], 0.722418, places=5)
        self.assertAlmostEqual(weights[3], 0.542227, places=5)

    def test_closed_form_matches_the_loop(self):
        """Proof 3: we can jump to any round directly."""
        score, start, memory = 0.936547, 0.5, 0.8
        value = start
        for _ in range(3):
            value = trust.update_trust(value, score, memory)
        self.assertAlmostEqual(value, trust.trust_after(3, start, score, memory), places=9)

    def test_trust_settles_at_the_score(self):
        """Proof 2: trust ends up equal to the score."""
        value = 0.5
        for _ in range(300):
            value = trust.update_trust(value, 0.5865, 0.8)
        self.assertAlmostEqual(value, 0.5865, places=6)

    def test_trust_never_leaves_zero_to_one(self):
        """Proof 1."""
        for start in (0.0, 0.5, 1.0):
            for score in (0.0, 0.5, 1.0):
                value = start
                for _ in range(50):
                    value = trust.update_trust(value, score, 0.8)
                    self.assertGreaterEqual(value, -1e-9)
                    self.assertLessEqual(value, 1 + 1e-9)

    def test_memory_of_one_freezes_trust(self):
        self.assertAlmostEqual(trust.update_trust(0.5, 0.9, 1.0), 0.5)

    def test_memory_of_zero_forgets_everything(self):
        self.assertAlmostEqual(trust.update_trust(0.5, 0.9, 0.0), 0.9)


class TestReadings(unittest.TestCase):

    def test_half_life(self):
        """PDF page 16: 3.106 rounds at memory 0.8."""
        self.assertAlmostEqual(trust.half_life(0.8), 3.106, places=3)

    def test_memory_length(self):
        self.assertAlmostEqual(trust.memory_length(0.8), 5.0)

    def test_influence_shares_add_to_one(self):
        shares = trust.influence_shares({"A": 0.9367, "B": 0.9558, "C": 0.5865})
        self.assertAlmostEqual(sum(shares.values()), 1.0)

    def test_influence_matches_the_pdf(self):
        """Section 8.6: 37.8%, 38.6%, 23.6%.

        The PDF cuts the numbers rather than rounding them: the attacker's true
        share is 0.2366, which it prints as 23.6%. So we check to 2 places.
        """
        shares = trust.influence_shares({"A": 0.936668, "B": 0.955774, "C": 0.586532})
        self.assertAlmostEqual(shares["A"], 0.378, places=2)
        self.assertAlmostEqual(shares["B"], 0.386, places=2)
        self.assertAlmostEqual(shares["C"], 0.236, places=2)
        # The liar must end up with clearly less than an equal share.
        self.assertLess(shares["C"], 1 / 3)

    def test_equal_trust_gives_equal_shares(self):
        shares = trust.influence_shares({"A": 0.5, "B": 0.5, "C": 0.5})
        for value in shares.values():
            self.assertAlmostEqual(value, 1 / 3)

    def test_zero_trust_falls_back_to_equal(self):
        shares = trust.influence_shares({"A": 0.0, "B": 0.0})
        self.assertAlmostEqual(shares["A"], 0.5)


class TestSharpen(unittest.TestCase):
    """Real embeddings squash scores together. Sharpening spreads them out."""

    def test_real_measured_values_separate(self):
        # Measured with nomic-embed-text on our own answers.
        before = {"honest1": 0.9914, "honest2": 0.9914, "liar": 0.9228}
        after = trust.sharpen(before)
        self.assertAlmostEqual(after["honest1"], 1.0)
        self.assertAlmostEqual(after["liar"], 0.0)

    def test_a_similar_group_is_left_alone(self):
        """All honest: do not invent a difference that is not there."""
        before = {"a": 0.98, "b": 0.99, "c": 0.985}
        self.assertEqual(trust.sharpen(before), before)

    def test_stays_between_zero_and_one(self):
        after = trust.sharpen({"a": 0.2, "b": 0.9, "c": 0.55})
        for value in after.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_empty_input(self):
        self.assertEqual(trust.sharpen({}), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
