"""Tests for answer parsing and change detection.

These pin the bugs seen in real runs, where an agent said it changed its mind
but the recorded value did not move.

Run:  python -m unittest discover -s tests
"""

import unittest

from p2p.agent import PeerAgent, _credited_peer, _norm


class Peer(PeerAgent):
    """A PeerAgent without the LLM client -- we only test the parsing."""

    def __init__(self, answer=""):
        self.name = "Agent_X"
        self.answer = answer
        self.reasoning = ""
        self.parsed = True


class TestAnswerParsing(unittest.TestCase):

    def test_plain_answer_line(self):
        p = Peer()
        p._absorb("some working\nANSWER: 408")
        self.assertEqual(p.answer, "408")
        self.assertTrue(p.parsed)

    def test_prose_mentioning_answer_is_ignored(self):
        # The exact failure from a real run: "My current answer: No" used to
        # hijack the parse and discard the real verdict at the bottom.
        p = Peer("No")
        p._absorb(
            "* My current answer: No\n"
            "* Peers' reasoning: Agent_B says yes.\n"
            "CONVINCED_BY: Agent_B\n"
            "ANSWER: Yes"
        )
        self.assertEqual(p.answer, "Yes")

    def test_last_answer_wins(self):
        p = Peer()
        p._absorb("ANSWER: 340\non reflection I was wrong\nANSWER: 408")
        self.assertEqual(p.answer, "408")

    def test_markdown_and_bullets(self):
        for text, want in [("**ANSWER:** Yes", "Yes"),
                           ("- ANSWER: no", "no"),
                           ("   ANSWER:   347  ", "347")]:
            p = Peer()
            p._absorb(text)
            self.assertEqual(p.answer, want, text)

    def test_missing_answer_line_is_flagged(self):
        p = Peer("408")
        p._absorb("I change my mind based on Agent_B.\nCONVINCED_BY: Agent_B")
        self.assertFalse(p.parsed)        # caller can WARN
        self.assertEqual(p.answer, "408")  # old value kept, but not silently


class TestNormalization(unittest.TestCase):

    def test_case_and_punctuation_are_ignored(self):
        for a, b in [("Yes", "yes"), ("yes", "yes."), ("Tokyo", "TOKYO"),
                     ("Tokyo.", "tokyo")]:
            self.assertEqual(_norm(a), _norm(b), f"{a!r} vs {b!r}")

    def test_genuinely_different_answers_stay_different(self):
        self.assertNotEqual(_norm("408"), _norm("347"))
        self.assertNotEqual(_norm("Yes"), _norm("No"))


class TestCreditedPeer(unittest.TestCase):

    def setUp(self):
        self.heard = {"Agent_A": ("408", ""), "Agent_C": ("347", "")}

    def test_single_peer(self):
        self.assertEqual(
            _credited_peer("CONVINCED_BY: Agent_C", self.heard), "Agent_C")

    def test_multiple_peers_all_reported(self):
        # Used to silently keep only the first name.
        self.assertEqual(
            _credited_peer("CONVINCED_BY: both Agent_A and Agent_C", self.heard),
            "Agent_A + Agent_C")

    def test_none_means_nobody(self):
        for raw in ["none", "no one", "nobody", "N/A"]:
            self.assertEqual(_credited_peer(f"CONVINCED_BY: {raw}", self.heard), "")

    def test_non_neighbour_is_rejected(self):
        # Agent_Z is not audible here, so it must not be credited.
        self.assertEqual(_credited_peer("CONVINCED_BY: Agent_Z", self.heard), "")


class TestArgumentSharing(unittest.TestCase):

    def test_bookkeeping_lines_are_stripped(self):
        p = Peer()
        p._absorb("17 * 20 = 340\n17 * 4 = 68\nCONVINCED_BY: none\nANSWER: 408")
        arg = p.argument()
        self.assertIn("340", arg)
        self.assertNotIn("ANSWER:", arg)
        self.assertNotIn("CONVINCED_BY:", arg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
