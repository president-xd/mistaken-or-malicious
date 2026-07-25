"""Tests for the trust learning schedule and the trait settings.

Run:  python -m unittest discover -s tests
"""

import unittest

from p2p import prompts, schedule
from p2p.config import Config, Question


class TestPlan(unittest.TestCase):

    def test_all_means_every_question_learns(self):
        plan = schedule.build_plan(5, "all", 0.5, 1)
        self.assertEqual(plan, ["learn"] * 5)

    def test_first_learns_then_freezes(self):
        plan = schedule.build_plan(10, "first", 0.3, 1)
        self.assertEqual(plan[:3], ["learn"] * 3)
        self.assertEqual(plan[3:], ["frozen"] * 7)

    def test_random_learns_the_right_number(self):
        plan = schedule.build_plan(10, "random", 0.4, 1)
        self.assertEqual(plan.count("learn"), 4)
        self.assertEqual(len(plan), 10)

    def test_random_is_repeatable_with_the_same_seed(self):
        a = schedule.build_plan(20, "random", 0.5, 7)
        b = schedule.build_plan(20, "random", 0.5, 7)
        self.assertEqual(a, b)

    def test_random_differs_with_another_seed(self):
        a = schedule.build_plan(20, "random", 0.5, 1)
        b = schedule.build_plan(20, "random", 0.5, 2)
        self.assertNotEqual(a, b)

    def test_share_of_zero_learns_from_nothing(self):
        plan = schedule.build_plan(5, "first", 0.0, 1)
        self.assertEqual(plan.count("learn"), 0)

    def test_share_of_one_learns_from_everything(self):
        plan = schedule.build_plan(5, "first", 1.0, 1)
        self.assertEqual(plan.count("learn"), 5)

    def test_plan_length_always_matches(self):
        for mode in schedule.LEARN_MODES:
            for total in (1, 3, 10):
                self.assertEqual(len(schedule.build_plan(total, mode, 0.5, 1)), total)


class TestTraits(unittest.TestCase):

    def test_no_trait_gives_the_plain_prompt(self):
        plain = prompts.system_message("Agent_A", "honest")
        self.assertNotIn("update easily", plain)
        self.assertIn("Agent_A", plain)

    def test_high_agreeableness_is_added(self):
        text = prompts.system_message("Agent_A", "honest", agreeableness="high")
        self.assertIn("update easily", text)

    def test_low_agreeableness_is_added(self):
        text = prompts.system_message("Agent_A", "honest", agreeableness="low")
        self.assertIn("actually wrong", text)

    def test_persuasion_is_added(self):
        text = prompts.system_message("Agent_A", "honest", persuasion="high")
        self.assertIn("never hedge", text)

    def test_both_traits_together(self):
        text = prompts.system_message("Agent_A", "liar",
                                      agreeableness="low", persuasion="high")
        self.assertIn("actually wrong", text)
        self.assertIn("never hedge", text)

    def test_unknown_level_is_ignored(self):
        text = prompts.system_message("Agent_A", "honest", agreeableness="banana")
        self.assertNotIn("banana", text)

    def test_answer_line_is_always_last(self):
        for level in ("", "high", "medium", "low"):
            text = prompts.system_message("Agent_A", "honest", agreeableness=level)
            self.assertTrue(text.rstrip().endswith(">"))


class TestTraitLookup(unittest.TestCase):

    def setUp(self):
        self.cfg = Config(questions=[Question("Q")],
                          agreeableness="low,medium,high",
                          persuasion="high")

    def test_reads_each_agents_level(self):
        self.assertEqual(self.cfg.trait_for(0, "agreeableness"), "low")
        self.assertEqual(self.cfg.trait_for(1, "agreeableness"), "medium")
        self.assertEqual(self.cfg.trait_for(2, "agreeableness"), "high")

    def test_agents_past_the_list_get_nothing(self):
        self.assertEqual(self.cfg.trait_for(9, "agreeableness"), "")

    def test_a_short_list_only_covers_the_first_agents(self):
        self.assertEqual(self.cfg.trait_for(0, "persuasion"), "high")
        self.assertEqual(self.cfg.trait_for(1, "persuasion"), "")

    def test_empty_setting_gives_nothing(self):
        cfg = Config(questions=[Question("Q")])
        self.assertEqual(cfg.trait_for(0, "agreeableness"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
