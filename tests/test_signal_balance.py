"""Are the three signals treated the same way before they are added up?

WHY THIS MATTERS.

The round score is:

    score = w_agree * agree + w_consist * consist + w_anomaly * (1 - anomaly)

For the three weights to mean what they look like they mean, the three signals
have to be on the same scale. If one of them can only ever move between 0.93
and 0.99 while the other two are stretched across the full 0 to 1, then a
weight of one third on each does NOT give each signal an equal say.

`network.update_trust` sharpens `agree` and `anomaly` but not `consist`. These
tests record what that does to the balance.

This matters for a conclusion recorded in README.md. The ablation found
that `consist` contributes nothing. Part of that may not be about consistency
being a weak idea at all - it may be that our code hands it a much smaller
range to work in.

Run:  python -m unittest discover -s tests
"""

import unittest

from p2p.trust import behaviour_score, sharpen


def spread(values):
    """How much room a signal has to move the score."""
    return max(values.values()) - min(values.values())


class TestSharpenDoesWhatItSays(unittest.TestCase):

    def test_it_stretches_a_narrow_band_to_the_full_range(self):
        out = sharpen({"A": 0.99, "B": 0.92, "C": 0.98})
        self.assertAlmostEqual(min(out.values()), 0.0)
        self.assertAlmostEqual(max(out.values()), 1.0)

    def test_it_leaves_near_identical_scores_alone(self):
        """Otherwise a network of equally honest agents would be torn apart."""
        scores = {"A": 0.90, "B": 0.91, "C": 0.90}
        self.assertEqual(sharpen(scores), scores)

    def test_empty_input_is_safe(self):
        self.assertEqual(sharpen({}), {})


class TestKnownLimitationConsistIsNotSharpened(unittest.TestCase):
    """KNOWN LIMITATION, recorded on purpose.

    These tests describe what the code does today, not what we want. If
    somebody sharpens `consist` too, they will fail - that is the fix, so
    update them rather than deleting them.
    """

    # Values shaped like real embedding output: everything squashed high, with
    # the liar (B) a little lower. The GAP is the same in both signals, so any
    # difference in effect comes purely from how we treat them.
    AGREE = {"A": 0.9914, "B": 0.9228, "C": 0.9901}
    CONSIST = {"A": 0.9950, "B": 0.9300, "C": 0.9940}

    def test_the_two_signals_carry_a_similar_gap_to_begin_with(self):
        self.assertAlmostEqual(spread(self.AGREE), 0.0686, places=3)
        self.assertAlmostEqual(spread(self.CONSIST), 0.0650, places=3)

    def test_but_only_agree_gets_stretched(self):
        self.assertAlmostEqual(spread(sharpen(self.AGREE)), 1.0)
        self.assertAlmostEqual(spread(self.CONSIST), 0.065, places=3)

    def test_so_consist_has_far_less_say_despite_an_equal_weight(self):
        """With one third weight each, consist should count for as much as
        agree. It cannot: it has about a fifteenth of the room to move."""
        say_of_agree = spread(sharpen(self.AGREE))
        say_of_consist = spread(self.CONSIST)
        self.assertLess(say_of_consist / say_of_agree, 0.10,
                        "consist has been given a fair range - update this test")

    def test_the_effect_on_the_final_score(self):
        """Same weights, same starting gap, very different influence."""
        third = 1 / 3
        agree = sharpen(self.AGREE)

        def score_for(name, use_sharp_consist):
            consist = sharpen(self.CONSIST) if use_sharp_consist else self.CONSIST
            return behaviour_score(agree[name], consist[name], 0.0,
                                   third, third, third)

        # How far apart are the honest agent and the liar, as the code is now?
        as_written = score_for("A", False) - score_for("B", False)
        # And how far apart would they be if consist were treated the same way?
        if_balanced = score_for("A", True) - score_for("B", True)

        self.assertGreater(if_balanced, as_written)
        # The gap the code throws away is worth roughly a third of a signal.
        self.assertGreater(if_balanced - as_written, 0.25)


class TestExactModeIsLessAffected(unittest.TestCase):
    """In `scoring: "answer"` the values are already 0 or 1 after stretching,
    so there is little left for sharpening to do. This is why the problem is
    much smaller in the mode we use for the headline results."""

    def test_zero_one_values_survive_sharpening_unchanged(self):
        exact = {"A": 1.0, "B": 0.0, "C": 1.0}
        self.assertEqual(sharpen(exact), exact)


if __name__ == "__main__":
    unittest.main(verbosity=2)
