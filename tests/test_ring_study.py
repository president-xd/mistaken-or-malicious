import json
import tempfile
import unittest
from pathlib import Path

from p2p import letters, prompts
from p2p.config import Config
from p2p.embed import ExactMatch
from p2p.gossip import aggregate_trust
from tools.validate_questions import validate


class TestRingStudyFixes(unittest.TestCase):
    def test_letter_forms_canonicalize(self):
        for value in ("C) 42", "C = 42", "Option C", "The answer is C"):
            self.assertEqual(letters.canonical_letter(value), "C")

    def test_liar_prompt_uses_wrong_text_but_letter_answer(self):
        prompt = prompts.solve_as_liar("Q", "C", "letter", "forty-two")
        self.assertIn("C) forty-two", prompt)
        self.assertTrue(prompt.rstrip().endswith("ANSWER: C"))

    def test_round_one_prompt_requests_belief(self):
        self.assertIn("BELIEF", prompts.solve("Q"))

    def test_exact_match_keeps_different_letters_separate(self):
        embedder = ExactMatch()
        self.assertNotEqual(embedder.vector("A"), embedder.vector("B"))

    def test_role_traits_have_requested_defaults_and_legacy_override(self):
        cfg = Config()
        self.assertEqual(cfg.trait_for_role(0, "honest", "agreeableness"), "high")
        self.assertEqual(cfg.trait_for_role(0, "liar", "persuasion"), "high")
        legacy = Config(agreeableness="low", persuasion="medium")
        self.assertEqual(legacy.trait_for_role(0, "honest", "agreeableness"), "low")

    def test_question_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "questions.jsonl"
            path.write_text(json.dumps({
                "text": "Q A) one B) two C) three D) four E) five",
                "answer": "A", "wrong": "B"}) + "\n", encoding="utf-8")
            self.assertEqual(validate(path), [])

    def test_gossip_toy(self):
        adjacency = {"A": ["B"], "B": ["A", "C"],
                     "C": ["B", "D"], "D": ["C"]}
        local = {"A": {"B": .9}, "B": {"C": .8},
                 "C": {"B": .7}, "D": {"C": .2}}
        previous = {name: {peer: .5 for peer in peers}
                    for name, peers in adjacency.items()}
        _, group, effective = aggregate_trust(adjacency, local, previous)
        self.assertAlmostEqual(group["A"]["B"], .8333333333, places=6)
        self.assertAlmostEqual(effective["A"]["B"], .8666666666, places=6)
        self.assertAlmostEqual(group["A"]["C"], .5, places=6)
        self.assertAlmostEqual(effective["A"]["C"], .5, places=6)

    def test_gossip_is_permutation_invariant_and_bounded(self):
        adjacency = {"A": ["B", "D"], "B": ["A", "C"],
                     "C": ["B", "D"], "D": ["A", "C"]}
        local = {name: {peer: .2 + .1 * i for i, peer in enumerate(peers)}
                 for name, peers in adjacency.items()}
        previous = {name: {peer: .5 for peer in peers}
                    for name, peers in adjacency.items()}
        _, group_a, effective_a = aggregate_trust(adjacency, local, previous)
        reversed_adjacency = {name: list(reversed(peers))
                              for name, peers in reversed(list(adjacency.items()))}
        _, group_b, effective_b = aggregate_trust(reversed_adjacency, local, previous)
        self.assertEqual(group_a, group_b)
        self.assertEqual(effective_a, effective_b)
        for table in (group_a, effective_a):
            for row in table.values():
                self.assertTrue(all(0 <= value <= 1 for value in row.values()))


if __name__ == "__main__":
    unittest.main()