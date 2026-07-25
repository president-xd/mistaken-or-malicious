"""Tests for the parts that had no tests: config, roles, embed, results.

Found during a full test pass. Several real bugs were caught here, and each one
now has a test so it cannot come back.

Run:  python -m unittest discover -s tests
"""

import json
import os
import tempfile
import unittest

import yaml

from p2p import roles, trust
from p2p.config import Config, Question, load_config
from p2p.embed import ExactMatch, make_embedder
from p2p.results import Results, already_done


# --------------------------------------------------------------- config

def write_config(**changes):
    base = {"questions": [{"text": "Q", "answer": "a", "wrong": "b"}],
            "agents": 3, "rounds": 2}
    base.update(changes)
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(base, f)
    f.close()
    return f.name


class TestConfigRejectsBadValues(unittest.TestCase):
    """Every one of these would break the maths or the experiment."""

    def check_rejected(self, **changes):
        path = write_config(**changes)
        try:
            with self.assertRaises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)

    def test_too_few_agents(self):
        self.check_rejected(agents=1)

    def test_no_rounds(self):
        self.check_rejected(rounds=0)

    def test_unknown_topology(self):
        self.check_rejected(topology="banana")

    def test_unknown_share_mode(self):
        self.check_rejected(share="silly")

    def test_unknown_scoring_mode(self):
        self.check_rejected(scoring="silly")

    def test_more_attackers_than_agents(self):
        self.check_rejected(attackers=9)

    def test_weights_that_do_not_add_up(self):
        self.check_rejected(weight_agree=0.9, weight_consist=0.9, weight_anomaly=0.9)

    def test_trust_memory_of_one_would_freeze_trust(self):
        self.check_rejected(trust_memory=1.0)

    def test_start_trust_out_of_range(self):
        self.check_rejected(start_trust=2.0)

    def test_warm_up_uses_every_question(self):
        self.check_rejected(warmup=1, trust=True)

    def test_unknown_learning_mode(self):
        self.check_rejected(trust_learn_on="sometimes")

    def test_unknown_trait_level(self):
        self.check_rejected(agreeableness="enormous")

    def test_attacker_without_a_wrong_answer(self):
        self.check_rejected(attackers=1,
                            questions=[{"text": "Q", "answer": "a"}])

    def test_sleeper_without_an_attacker(self):
        self.check_rejected(sleeper=True, attackers=0)


class TestConfigAcceptsGoodValues(unittest.TestCase):

    def load(self, **changes):
        path = write_config(**changes)
        try:
            return load_config(path)
        finally:
            os.unlink(path)

    def test_three_thirds_are_scaled_to_exactly_one(self):
        """0.333 three times is 0.999. That is clearly what the user meant."""
        cfg = self.load(weight_agree=0.333, weight_consist=0.333,
                        weight_anomaly=0.333)
        total = cfg.weight_agree + cfg.weight_consist + cfg.weight_anomaly
        self.assertAlmostEqual(total, 1.0)

    def test_no_memory_is_allowed(self):
        self.assertEqual(self.load(trust_memory=0.0).trust_memory, 0.0)

    def test_old_style_question_list_still_works(self):
        cfg = self.load(questions=["just a plain string"])
        self.assertEqual(cfg.questions[0].text, "just a plain string")

    def test_old_name_num_agents_still_works(self):
        path = write_config()
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        del raw["agents"]
        raw["num_agents"] = 5
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(raw, f)
        try:
            self.assertEqual(load_config(path).agents, 5)
        finally:
            os.unlink(path)


class TestQuestionsFromAFile(unittest.TestCase):

    def load_with_file(self, text, suffix, **changes):
        qf = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False,
                                         encoding="utf-8")
        qf.write(text)
        qf.close()
        path = write_config(questions_file=qf.name, **changes)
        try:
            return load_config(path)
        finally:
            os.unlink(path)
            os.unlink(qf.name)

    def test_yaml_file(self):
        cfg = self.load_with_file(
            "- text: Q1\n  answer: a\n  wrong: b\n- text: Q2\n  answer: c\n", ".yaml")
        self.assertEqual(len(cfg.questions), 2)
        self.assertEqual(cfg.questions[0].wrong, "b")

    def test_jsonl_file(self):
        cfg = self.load_with_file(
            '{"text":"Q1","answer":"a"}\n{"text":"Q2","answer":"b"}\n', ".jsonl")
        self.assertEqual(len(cfg.questions), 2)

    def test_max_questions_limits_the_list(self):
        cfg = self.load_with_file(
            "- text: Q1\n- text: Q2\n- text: Q3\n", ".yaml", max_questions=2)
        self.assertEqual(len(cfg.questions), 2)

    def test_missing_file_is_reported(self):
        path = write_config(questions_file="does_not_exist.yaml")
        try:
            with self.assertRaises(SystemExit):
                load_config(path)
        finally:
            os.unlink(path)


# --------------------------------------------------------------- roles

class TestChoosingLiarSeats(unittest.TestCase):

    def setUp(self):
        self.names = ["Agent_A", "Agent_B", "Agent_C", "Agent_D"]

    def pick(self, count, places, topo="mesh", seed=1):
        return roles.choose_seats(self.names, count, places, topo, seed)

    def test_no_attackers(self):
        self.assertEqual(self.pick(0, "random"), [])

    def test_random_picks_the_right_number(self):
        self.assertEqual(len(self.pick(2, "random")), 2)

    def test_random_is_repeatable_with_the_same_seed(self):
        self.assertEqual(self.pick(2, "random", seed=7),
                         self.pick(2, "random", seed=7))

    def test_random_changes_with_another_seed(self):
        # Not guaranteed for every pair of seeds, but must not be fixed.
        picks = {tuple(self.pick(1, "random", seed=s)) for s in range(20)}
        self.assertGreater(len(picks), 1)

    def test_exact_seats(self):
        self.assertEqual(self.pick(2, "0,3"), ["Agent_A", "Agent_D"])

    def test_duplicate_seats_are_removed(self):
        self.assertEqual(self.pick(1, "0,0,0"), ["Agent_A"])

    def test_hub_seat_for_a_star(self):
        self.assertEqual(self.pick(1, "center", "star"), ["Agent_A"])

    def test_outer_seat_for_a_star(self):
        self.assertEqual(self.pick(1, "leaf", "star"), ["Agent_B"])

    def test_never_more_liars_than_agents(self):
        self.assertEqual(len(self.pick(99, "random")), len(self.names))

    def test_a_seat_that_does_not_exist_is_ignored(self):
        # Falls back to a random seat rather than crashing.
        self.assertEqual(len(self.pick(1, "99")), 1)


# --------------------------------------------------------------- embed

class TestExactMatch(unittest.TestCase):
    """Compares answers by exact text rather than by meaning."""

    def test_same_answer_scores_one(self):
        e = ExactMatch()
        a, b = e.pad_all([e.vector("yes"), e.vector("yes")])
        self.assertAlmostEqual(trust.similarity(a, b), 1.0)

    def test_case_and_punctuation_do_not_matter(self):
        e = ExactMatch()
        a, b = e.pad_all([e.vector("Yes."), e.vector("yes")])
        self.assertAlmostEqual(trust.similarity(a, b), 1.0)

    def test_different_answers_are_stretched_to_zero(self):
        """The bug this catches: two different answers scored 0.5, not 0.

        Two different answers become two directions at right angles, and a right
        angle gives 0.5. That is only half the range the formula needs.
        """
        e = ExactMatch()
        a, b = e.pad_all([e.vector("yes"), e.vector("no")])
        raw = trust.similarity(a, b)
        self.assertAlmostEqual(raw, 0.5)                      # what we get
        self.assertAlmostEqual(trust.stretch_exact(raw), 0.0)  # what we need

    def test_a_stubborn_liar_scores_below_neutral(self):
        """Before the fix a liar that never moved scored 0.667, which is ABOVE
        neutral, so it would have gained trust."""
        agree = trust.stretch_exact(0.5)                    # agrees with nobody
        consist = trust.stretch_exact(1.0)                  # never moves
        anomaly = trust.stretch_exact(0.5, is_anomaly=True)  # far from everyone
        score = trust.behaviour_score(agree, consist, anomaly, 1/3, 1/3, 1/3)
        self.assertLess(score, 0.5)

    def test_make_embedder_picks_the_right_one(self):
        self.assertIsInstance(make_embedder("answer", "x"), ExactMatch)

    def test_empty_answer_does_not_crash(self):
        self.assertTrue(ExactMatch().vector(""))


class TestVectorWidth(unittest.TestCase):
    """New answers make the vectors longer. Old and new must be padded to the
    same width before they are compared."""

    def test_switching_to_a_brand_new_answer_is_seen_as_a_change(self):
        e = ExactMatch()
        old = e.vector("yes")
        new = e.vector("banana")
        old, new = e.pad_all([old, new])
        raw = trust.consist_score(new, old)
        self.assertAlmostEqual(trust.stretch_exact(raw), 0.0)

    def test_unpadded_comparison_would_be_wrong(self):
        """Shows why the padding matters: without it the answer looks unchanged."""
        e = ExactMatch()
        old = e.vector("yes")        # length 1
        new = e.vector("banana")     # length 2
        self.assertNotEqual(len(old), len(new))
        self.assertAlmostEqual(trust.consist_score(new, old), 0.5)  # wrong


# --------------------------------------------------------------- results

class TestResultsFile(unittest.TestCase):

    def setUp(self):
        self.cfg = Config(questions=[Question("Q", "a", "b")], agents=2,
                          attackers=1, attacker_answer="b")
        self.dir = tempfile.mkdtemp()

    def test_saves_a_readable_json_file(self):
        r = Results(self.cfg, ["Agent_A", "Agent_B"], ["Agent_B"])
        r.start_question("Q", "a")
        r.finish_question({"Agent_A": "a"}, {"honest_accuracy": 1.0})
        r.set_summary({"honest_accuracy": 1.0})
        path = r.save(folder=self.dir, run_name="test")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["settings"]["agents"], 2)
        self.assertEqual(data["summary"]["honest_accuracy"], 1.0)

    def test_roles_are_written_down(self):
        r = Results(self.cfg, ["Agent_A", "Agent_B"], ["Agent_B"])
        roles_in_file = {a["name"]: a["role"] for a in r.data["agents"]}
        self.assertEqual(roles_in_file["Agent_B"], "liar")
        self.assertEqual(roles_in_file["Agent_A"], "honest")

    def test_comparison_says_which_side_is_better(self):
        r = Results(self.cfg, ["Agent_A"], [])
        r.set_comparison(
            {"honest_accuracy": 0.5, "attack_success_rate": 0.5,
             "trust_separation": 0.0, "attacker_influence": 0.33},
            {"honest_accuracy": 0.9, "attack_success_rate": 0.1,
             "trust_separation": 0.4, "attacker_influence": 0.15})
        better = r.data["comparison"]["better_with_trust"]
        self.assertTrue(better["honest_accuracy"])       # higher is better
        self.assertTrue(better["attack_success_rate"])   # lower is better
        self.assertTrue(better["trust_separation"])
        self.assertTrue(better["attacker_influence"])

    def test_a_finished_run_is_found(self):
        r = Results(self.cfg, ["Agent_A"], [])
        r.save(folder=self.dir, run_name="done")
        self.assertTrue(already_done("done", folder=self.dir))
        self.assertFalse(already_done("not_run", folder=self.dir))

    def test_no_run_name_means_nothing_is_ever_skipped(self):
        self.assertEqual(already_done("", folder=self.dir), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
