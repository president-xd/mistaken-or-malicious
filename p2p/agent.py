"""A single peer agent, backed by an AutoGen AssistantAgent + local Ollama model.

Every agent is the SAME kind of peer: they share one persona and differ only by
a runtime-generated name (Agent_A, Agent_B, ...). A peer can do two things:
  * solve()       -- answer the question independently, hearing nobody
  * reconsider()  -- after hearing chosen peers, keep or change its answer
The AssistantAgent keeps its own conversation memory across both calls, so each
peer genuinely "remembers" its reasoning while it debates.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken

from . import letters, prompts, providers

# Kept for older code that imported it. The real text lives in prompts.py.
PERSONA = prompts.HONEST

# The ANSWER line must START its own line (allowing bullets/markdown like
# "* " or "**"), so prose such as "My current answer: No" can no longer be
# mistaken for the verdict. We also take the LAST match, because a model that
# restates itself puts its real conclusion at the end.
_ANSWER_RE = re.compile(r"^\W{0,4}ANSWER\W{0,4}:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
# DOTALL so the JSON object may sit on the line AFTER the label, which models do.
_BELIEF_RE = re.compile(r"^\W{0,4}BELIEF\W{0,4}:\s*(\{.*?\})",
                        re.IGNORECASE | re.MULTILINE | re.DOTALL)
_CONVINCED_RE = re.compile(r"^\W{0,4}CONVINCED_BY\W{0,4}:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_NO_ONE = {"none", "no one", "nobody", "n/a", "na", "myself", "self", ""}
_TRIM = " *_\"'`"
# Lines where an agent is quoting/discussing a peer rather than reasoning itself.
_QUOTES_PEER_RE = re.compile(
    r"(agent_\w+|peer_\w+|their reasoning|says\s*:)", re.IGNORECASE)


# Used only when salvaging a reply that has no ANSWER line.
_EQUALS_RE = re.compile(r"=|\bequals\b|\bis equal to\b", re.IGNORECASE)
_YESNO_RE = re.compile(r"\b(yes|no)\b", re.IGNORECASE)
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_VALUE_WORDS = 3        # up to this many words is a value, not a sentence
_MAX_ANSWER_WORDS = 6   # a stated ANSWER longer than this is prose -> re-ask
_SHORT_ANSWER = 60      # hard cap on anything we salvage from prose

# Sent ALONE when the model forgot its ANSWER line. Re-sending the whole question
# just reproduces the same failure, so instead we ask only for the missing line --
# the agent still has its own reply in context and only has to name its verdict.
def _salvage(text: str) -> str:
    """Best-effort answer when the model omitted its ANSWER line even after a retry.

    The goal is a SHORT, comparable value. A whole equation ("340 + 68 = 408") or
    a paragraph of prose can never match a peer who simply wrote "408", and if it
    is stored it also gets forwarded to neighbours as that agent's answer, which
    pollutes their prompts. So we peel off the conclusion, and if the reply ends
    in prose we look for a short verdict instead.
    """
    # Ignore bookkeeping lines: a reply that ends on "CONVINCED_BY: Agent_C"
    # would otherwise have that stored as its answer.
    lines = [ln.strip() for ln in text.splitlines()
             if ln.strip() and not _CONVINCED_RE.match(ln.strip())]
    if not lines:
        return ""

    return _condense(lines[-1], text)


def _condense(value: str, context: str = "") -> str:
    """Reduce a stated answer to something short and comparable.

    Applied to the ANSWER line as well as to salvaged text, because a model will
    happily write a whole sentence after "ANSWER:" -- and two agents that both
    mean "no" can then never be seen to agree.
    """
    # "340 + 68 = 408" / "17 * 24 equals 408" -> keep only the final value.
    tail = _EQUALS_RE.split(value)[-1].strip(_TRIM).rstrip(".").strip()

    # A couple of words is already a value ("408", "No", "Sydney") -- keep it.
    if tail and len(tail.split()) <= _VALUE_WORDS:
        return tail

    # It is a sentence. Pull out an unambiguous verdict if there is one, looking
    # at the sentence itself before the wider reply.
    for scope in (value, context):
        for pattern in (_YESNO_RE, _NUMBER_RE):
            found = pattern.findall(scope)
            if found:
                return found[-1]

    # Nothing quotable. Keep it short so it cannot flood a neighbour's prompt.
    return (tail or value)[:_SHORT_ANSWER]


def parse_belief(text: str) -> dict:
    """Pull the BELIEF JSON object out of a reply, or {} if absent/malformed."""
    hits = _BELIEF_RE.findall(text)
    for raw in reversed(hits):
        try:
            got = json.loads(raw)
            if isinstance(got, dict):
                return got
        except (ValueError, TypeError):
            continue
    return {}


def normalize_belief(raw: dict, candidates: list[str], fallback: str) -> dict:
    """Map a raw belief onto the answers in play and rescale it to sum to 1.

    Unlike a fixed A-E question, our candidate set is whatever answers currently
    exist in the network, so keys are matched to them case/punctuation
    insensitively. Negative or unparseable weights are dropped, unknown keys are
    ignored, and an empty result falls back to certainty in `fallback` -- so a
    model that skips or mangles the line still yields a valid distribution.
    """
    options = list(dict.fromkeys([c for c in candidates if c] + ([fallback] if fallback else [])))
    if not options:
        return {}
    out = {c: 0.0 for c in options}
    index = {_norm(c): c for c in options}
    for key, value in (raw or {}).items():
        target = index.get(_norm(str(key)))
        if target is None:
            continue
        try:
            out[target] += max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    total = sum(out.values())
    if total <= 0:
        if fallback in out:
            return {c: (1.0 if c == fallback else 0.0) for c in options}
        return {c: 1.0 / len(options) for c in options}
    return {c: v / total for c, v in out.items()}


def belief_shift(before: dict, after: dict) -> float:
    """How much probability mass moved between two beliefs (0 = none, 1 = all).

    Total-variation distance: half the sum of absolute changes. This is the
    number that makes a PARTIAL concession visible -- an agent can move 0.3 of
    its mass toward a peer while its top answer never changes.
    """
    keys = set(before) | set(after)
    return sum(abs(after.get(k, 0.0) - before.get(k, 0.0)) for k in keys) / 2


def top_answer(belief: dict) -> str:
    """The answer holding the most belief mass."""
    return max(belief, key=belief.get) if belief else ""


def _norm(answer: str) -> str:
    """Comparison key for an answer: case- and punctuation-insensitive.

    Used for BOTH "did it change?" and the consensus check, so the two can never
    disagree -- "Yes", "yes" and "yes." are one and the same answer.
    """
    return re.sub(r"[^\w\s]", "", answer).strip().lower()


def _credited_peer(text: str, heard: dict[str, str]) -> str:
    """Which neighbour the model credits for changing its mind.

    We only trust a name the agent could actually hear, so a hallucinated or
    non-neighbour credit is dropped -- this is also how we verify the change is
    grounded in a real peer rather than made up.
    """
    hits = _CONVINCED_RE.findall(text)
    raw = (hits[-1].strip(_TRIM).strip(".") if hits else "").lower()
    if raw in _NO_ONE:
        return ""
    named = [name for name in heard if name.lower() in raw]
    # A model sometimes credits several peers ("both Agent_A and Agent_C");
    # report them all rather than silently keeping only the first.
    return " + ".join(named)


def agent_names(count: int) -> list[str]:
    """Generate agent names at runtime: Agent_A..Agent_Z, then Agent_27, ..."""
    names = []
    for i in range(count):
        tag = chr(ord("A") + i) if i < 26 else str(i + 1)
        names.append(f"Agent_{tag}")
    return names


def make_model_client(model: str, provider: str = "ollama",
                      seed: int | None = None, temperature: float = 0.7):
    """A client for whichever provider the config asked for.

    The choice itself lives in providers.py. This stays here only so older
    code that imported it keeps working.
    """
    return providers.make_client(provider, model, seed, temperature)


def make_clients(model: str, provider: str, seed: int | None, count: int,
                 temperature: float = 0.7):
    """One client per agent, each with its OWN seed.

    Every agent must be repeatable, but they must not all become the same
    agent. A single shared seed would make every honest agent produce the
    identical reply to the identical question, so the network would really
    hold one opinion wearing several names, and `agree` would be measuring
    nothing.

    Giving agent i the seed `seed + i` keeps both properties: the run repeats
    exactly, and the agents still think independently.

    With no seed set, every client is unseeded and the run is not repeatable.
    """
    if seed is None:
        return [providers.make_client(provider, model, temperature=temperature)
                for _ in range(count)]
    return [providers.make_client(provider, model, seed + i, temperature)
            for i in range(count)]


class PeerAgent:
    """One node in the network."""

    # Class-level defaults so partially-built instances stay valid.
    _candidates: tuple = ()
    belief: dict = {}
    belief_ignored: bool = False    # the BELIEF line could not be used
    belief_disagrees: bool = False  # the belief contradicts the stated answer

    def __init__(self, name: str, client,
                 role: str = "honest", wrong_answer: str = "",
                 wrong_text: str = "", agreeableness: str = "",
                 persuasion: str = "", answer_format: str = "free"):
        self.name = name
        self.role = role           # "honest" or "liar"
        self.wrong_answer = wrong_answer   # the answer a liar must defend
        self.wrong_text = wrong_text
        self.initial_error_answer = ""  # seeded first-round mistake treatment
        self.answer_format = answer_format
        self.agreeableness = agreeableness  # how easily it changes its mind
        self.persuasion = persuasion        # how hard it pushes its view
        self.answer = ""       # current one-line answer (the ANSWER: value)
        self.model_answer = ""  # parsed model output before attacker enforcement
        self.belief = {}       # answer -> probability, over the answers in play
        self.reasoning = ""    # full text of the latest reply
        self.parsed = True     # did the latest reply contain a usable ANSWER line?
        self.retried = False   # did the latest turn need a re-ask to parse?
        self._candidates = []  # answers the current belief may range over
        self._agent = AssistantAgent(
            name=name,
            model_client=client,
            system_message=prompts.system_message(name, role,
                                                  agreeableness, persuasion),
        )

    @property
    def lies(self) -> bool:
        return self.role == "liar"

    async def _run(self, prompt: str) -> str:
        result = await self._agent.run(task=prompt)
        return result.messages[-1].content.strip()

    async def _ask(self, prompt: str, force_answer: str = "") -> str:
        """Run a prompt and absorb the reply, retrying ONCE if the ANSWER line is
        missing. Small models drop the format often, and an unparsed reply used
        to freeze an agent's answer for the rest of the run."""
        self.retried = False
        dump_agent = os.environ.get("P2P_DUMP_AGENT")
        dump_path = os.environ.get("P2P_DUMP_PROMPT")
        if dump_agent == self.name and dump_path and "Peers you can hear" in prompt:
            path = Path(dump_path)
            if not path.exists():
                path.write_text(prompt, encoding="utf-8")
        text = await self._run(prompt)
        self._absorb(text)
        self.model_answer = self.answer
        if force_answer:
            # Keep the model's answer for audit, then apply the protocol's
            # assigned first-round mistake or attacker commitment.
            lines = [
                line for line in text.splitlines()
                if not _ANSWER_RE.match(line)
                and not re.match(r"^\W{0,4}BELIEF\W{0,4}:", line, re.I)
            ]
            lines.extend((f'BELIEF: {json.dumps({force_answer: 1.0})}',
                          f"ANSWER: {force_answer}"))
            text = "\n".join(lines)
            self._absorb(text)
            self.belief = {self.answer: 1.0}
            return text
        if not self.parsed:
            self.retried = True
            # Ask ONLY for the missing line, then absorb both together so the
            # original reasoning is kept and the verdict comes from the follow-up.
            text = f"{text}\n{await self._run(prompts.retry(
                getattr(self, "answer_format", "free")))}"
            self._absorb(text)
        return text

    async def reset(self) -> None:
        """Clear this agent's memory (via the SDK) before a new question."""
        await self._agent.on_reset(CancellationToken())
        self.answer = ""
        self.model_answer = ""
        self.initial_error_answer = ""
        self.belief = {}
        self.reasoning = ""
        self._candidates = []

    async def solve(self, question: str) -> str:
        """Phase 1: answer independently, having heard no peer yet."""
        if self.lies and self.wrong_answer:
            return await self._ask(prompts.solve_as_liar(
                question, self.wrong_answer, self.answer_format, self.wrong_text),
                force_answer=self.wrong_answer)
        if self.initial_error_answer:
            return await self._ask(prompts.solve_with_initial_error(
                question, self.initial_error_answer, self.answer_format),
                force_answer=self.initial_error_answer)
        return await self._ask(prompts.solve(question, self.answer_format))

    def argument(self) -> str:
        """This peer's OWN reasoning, ready to share with neighbours.

        Bookkeeping lines and anything quoting another peer are dropped: a reply
        often restates what peers said, and re-sharing that would nest quotes
        inside quotes until the prompt turns to noise.
        """
        lines = [
            ln.strip() for ln in self.reasoning.splitlines()
            if ln.strip()
            and not _ANSWER_RE.match(ln)
            and not _CONVINCED_RE.match(ln)
            and not _QUOTES_PEER_RE.search(ln)
        ]
        return " ".join(lines)[:300]

    async def reconsider(self, question: str, heard: dict[str, tuple[str, str]],
                         trust: dict[str, float] | None = None) -> tuple[str, bool, str]:
        """Phase 2: hear neighbours; keep or change your own answer.

        `heard` maps a neighbour name -> (its answer, its reasoning-or-"").
        Returns (full_reply_text, changed?, convinced_by). `convinced_by` is the
        neighbour the model itself credits for changing its mind, or "" if none.
        """
        # Put the trust score next to each peer's name. This is what makes the
        # trust defence actually work: without it the score would be worked out
        # and shown, but the agent would never see it and nothing would change.
        def label(n):
            if trust and n in trust:
                return f"- {n} (trust {trust[n]:.2f}) answered:"
            return f"- {n} answered:"

        peers = "\n".join(
            f"{label(n)} {a}" + (f"\n    (their working: {why})" if why else "")
            for n, (a, why) in heard.items()
        ) or "(nobody)"
        previous = self.answer
        # The belief ranges over every answer alive in this agent's neighbourhood,
        # so it can put weight on a peer's answer without adopting it outright.
        self._candidates = list(dict.fromkeys(
            [previous] + [a for a, _ in heard.values()]))
        write = prompts.reconsider_as_liar if self.lies else prompts.reconsider
        note = prompts.TRUST_NOTE if trust else ""
        # The LIST is passed, not a formatted string, so prompts.py can build
        # the worked example out of the answers actually in play. A fixed
        # example got copied verbatim and the belief was then discarded.
        answer_for_prompt = self.wrong_answer if self.lies else previous
        text = await self._ask(
            write(question, answer_for_prompt, peers, self._candidates, note,
                self.answer_format),
            force_answer=self.wrong_answer if self.lies else "")
        self._absorb(text)
        # Compare normalized: "Yes" -> "yes." is NOT a change of mind.
        changed = _norm(self.answer) != _norm(previous)
        convinced_by = _credited_peer(text, heard) if changed else ""
        return text, changed, convinced_by

    def _absorb(self, text: str) -> None:
        """Store the reply and extract the ANSWER: value from it.

        Sets `self.parsed` so the caller can WARN instead of silently keeping a
        stale answer -- a missing ANSWER line used to hide real mind-changes.
        """
        self.reasoning = text
        hits = _ANSWER_RE.findall(text)
        if hits:
            value = hits[-1].strip(_TRIM)
            canonical = (letters.canonical_letter(value)
                         if getattr(self, "answer_format", "free") == "letter" else "")
            self.answer = canonical or _condense(value, text)
            # An ANSWER line holding a whole sentence ("It is incorrect to
            # classify a hot dog as a sandwich") is not a comparable verdict --
            # two agents that both mean "no" would never be seen to agree. Treat
            # it as unparsed so the retry asks for the short form.
            self.parsed = len(self.answer.split()) <= _MAX_ANSWER_WORDS
        else:
            self.parsed = False
            if not self.answer:  # no ANSWER line at all on the very first turn
                value = _salvage(text)
                self.answer = (letters.canonical_letter(value)
                               if getattr(self, "answer_format", "free") == "letter"
                               else value)
        # Otherwise keep the previous answer -- but the caller WARNs, because a
        # real change may have been stated in prose we could not read.

        # Belief always ends up valid: a missing or malformed BELIEF line simply
        # collapses to certainty in the stated answer, so it never fails a run.
        raw_belief = parse_belief(text)
        self.belief = normalize_belief(raw_belief, self._candidates, self.answer)

        # Two things that used to happen silently, and now get reported.
        #
        # 1. The model wrote a BELIEF line, but none of its keys matched a real
        #    answer - usually because it copied the example. Everything it said
        #    was thrown away and replaced with certainty in its own answer, so
        #    the confidence number shown was ours, not the model's.
        known = {_norm(c) for c in self._candidates} | {_norm(self.answer)}
        self.belief_ignored = bool(raw_belief) and not any(
            _norm(str(k)) in known for k in raw_belief)

        # 2. The stated answer contradicts the stated belief: the agent says
        #    one thing on its ANSWER line and puts its confidence on another.
        #    Both were stored and never compared.
        #
        #    The bar is deliberately high. Leaning 55/45 the other way is a
        #    real opinion about a close call, not a mistake, and flagging it
        #    would bury the genuine case in noise. We only report it when the
        #    agent has almost abandoned its own answer.
        best = top_answer(self.belief)
        self.belief_disagrees = bool(
            best and self.answer and _norm(best) != _norm(self.answer)
            and self.belief.get(best, 0.0) > 0.5
            and self.belief.get(self.answer, 0.0) < 0.25)
