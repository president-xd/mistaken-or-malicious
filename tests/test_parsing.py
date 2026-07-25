"""Tests for answer parsing and change detection.

These pin the bugs seen in real runs, where an agent said it changed its mind
but the recorded value did not move.

Run:  python -m unittest discover -s tests
"""

import asyncio
import unittest

from p2p.agent import PeerAgent, _credited_peer, _norm, _salvage


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


class TestSalvage(unittest.TestCase):
    """When the model omits its ANSWER line we must still store a comparable
    value -- not a whole equation that can never match a peer's bare number."""

    def test_equation_keeps_only_the_result(self):
        # The exact failure seen in a real run: Agent_A stored "340 + 68 = 408"
        # while Agent_B stored "408", so the two never counted as agreeing.
        self.assertEqual(_salvage("working...\n340 + 68 = 408"), "408")

    def test_salvaged_equation_matches_a_bare_answer(self):
        p = Peer()
        p._absorb("To solve this:\n17 * 20 = 340\n17 * 4 = 68\n340 + 68 = 408")
        self.assertFalse(p.parsed)
        self.assertEqual(_norm(p.answer), _norm("408"))

    def test_trailing_period_and_prose_prefix(self):
        self.assertEqual(_salvage("Therefore, 17 * 24 = 408."), "408")

    def test_plain_last_line_when_no_equation(self):
        self.assertEqual(_salvage("I thought about it.\nNo"), "No")

    def test_word_equals_is_handled_like_the_symbol(self):
        # Real run: "Therefore, 17 * 24 equals 408" was stored whole.
        self.assertEqual(_salvage("Therefore, 17 * 24 equals 408"), "408")

    def test_prose_verdict_is_extracted(self):
        self.assertEqual(
            _salvage("After weighing both sides I have to say no, it is not one."),
            "no")

    def test_prose_answer_is_length_bounded(self):
        # Real run: a whole paragraph became an agent's "answer" and was then
        # forwarded to its neighbours. Whatever we salvage must stay short.
        para = ("A hot dog is served in a bun, whereas a sandwich has multiple "
                "components placed between two slices of bread, and the key "
                "difference lies in the construction method")
        self.assertLessEqual(len(_salvage(para)), 60)

    def test_convinced_by_line_is_never_the_answer(self):
        # A reply ending on bookkeeping used to store "CONVINCED_BY: Agent_C"
        # as the agent's answer and forward it to its neighbours.
        got = _salvage("I would say NO.\nHot dogs stand alone.\nCONVINCED_BY: Agent_C")
        self.assertNotIn("CONVINCED_BY", got)
        self.assertEqual(_norm(got), _norm("No"))

    def test_empty_text(self):
        self.assertEqual(_salvage(""), "")


class TestRetryOnMissingAnswer(unittest.TestCase):
    """A missing ANSWER line must trigger exactly one re-ask."""

    class Scripted(PeerAgent):
        def __init__(self, replies):
            self.name = "Agent_X"
            self.answer = ""
            self.reasoning = ""
            self.parsed = True
            self.retried = False
            self._replies = list(replies)
            self.prompts = []

        async def _run(self, prompt):
            self.prompts.append(prompt)
            return self._replies.pop(0)

    def test_retry_asks_only_for_the_missing_line(self):
        """Re-sending the whole question just reproduced the same failure, so
        the follow-up must be the short nudge ALONE."""
        a = self.Scripted(["long reasoning, no label", "ANSWER: No"])
        # A realistic re-generate prompt: question + peers + instructions.
        full = ("The question is:\nWhat is 17 * 24?\n\nYour current answer: 347\n\n"
                "Peers you can hear right now:\n- Agent_A answered: 228\n"
                "- Agent_C answered: 408\n\nIf a peer's reasoning is more "
                "convincing, adopt the better answer and briefly say why.")
        asyncio.run(a._ask(full))
        self.assertNotIn("17 * 24", a.prompts[1])        # question NOT repeated
        self.assertNotIn("Agent_A", a.prompts[1])        # peers NOT repeated
        self.assertIn("ANSWER:", a.prompts[1])
        self.assertLess(len(a.prompts[1]), len(a.prompts[0]))

    def test_retry_keeps_the_original_reasoning(self):
        """share=both forwards an agent's working, so a one-line retry must not
        wipe out what it actually argued."""
        a = self.Scripted(["because 17*20=340 and 17*4=68", "ANSWER: 408"])
        asyncio.run(a._ask("solve it"))
        self.assertIn("340", a.reasoning)
        self.assertEqual(a.answer, "408")
        self.assertIn("340", a.argument())

    def test_reply_ending_on_convinced_by_recovers(self):
        """The exact repeated failure from a real run: the model wrote its
        verdict in prose, ended on CONVINCED_BY, and dropped the ANSWER line."""
        a = self.Scripted([
            "I would say NO.\nHot dogs are not sandwiches.\nCONVINCED_BY: Agent_C",
            "ANSWER: No",
        ])
        asyncio.run(a._ask("is a hot dog a sandwich?"))
        self.assertTrue(a.parsed)
        self.assertEqual(a.answer, "No")

    def test_sentence_in_the_answer_line_triggers_a_retry(self):
        """Real run: 'ANSWER: It is incorrect to classify a hot dog as a
        sandwich...' parsed fine but could never match a peer's 'No'."""
        a = self.Scripted([
            "ANSWER: It is incorrect to classify a hot dog as a sandwich "
            "due to its structural difference.",
            "ANSWER: No",
        ])
        asyncio.run(a._ask("is a hot dog a sandwich?"))
        self.assertTrue(a.retried)
        self.assertTrue(a.parsed)
        self.assertEqual(_norm(a.answer), _norm("No"))

    def test_short_multiword_answer_is_accepted(self):
        """A genuine few-word answer must NOT be treated as prose."""
        a = self.Scripted(["ANSWER: The capital is Canberra"])
        asyncio.run(a._ask("capital of Australia?"))
        self.assertFalse(a.retried)
        self.assertTrue(a.parsed)

    def test_retry_recovers_the_answer(self):
        a = self.Scripted(["some working, no label", "ANSWER: 408"])
        asyncio.run(a._ask("solve it"))
        self.assertTrue(a.retried)
        self.assertTrue(a.parsed)
        self.assertEqual(a.answer, "408")
        self.assertEqual(len(a.prompts), 2)
        self.assertIn("ANSWER:", a.prompts[1])       # the nudge was appended

    def test_no_retry_when_first_reply_is_fine(self):
        a = self.Scripted(["ANSWER: 408"])
        asyncio.run(a._ask("solve it"))
        self.assertFalse(a.retried)
        self.assertEqual(len(a.prompts), 1)

    def test_retry_happens_at_most_once(self):
        a = self.Scripted(["no label", "still no label"])
        asyncio.run(a._ask("solve it"))
        self.assertEqual(len(a.prompts), 2)          # not 3
        self.assertFalse(a.parsed)                   # caller will WARN

    def test_answer_is_not_frozen_when_retry_succeeds(self):
        """The bug this fixes: an unparsed reply used to keep the old answer for
        the rest of the run."""
        a = self.Scripted(["no label here", "ANSWER: 347"])
        a.answer = "408"
        asyncio.run(a._ask("reconsider"))
        self.assertEqual(a.answer, "347")


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
