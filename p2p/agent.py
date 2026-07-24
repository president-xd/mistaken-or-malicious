"""A single peer agent, backed by an AutoGen AssistantAgent + local Ollama model.

Every agent is the SAME kind of peer: they share one persona and differ only by
a runtime-generated name (Agent_A, Agent_B, ...). A peer can do two things:
  * solve()       -- answer the question independently, hearing nobody
  * reconsider()  -- after hearing chosen peers, keep or change its answer
The AssistantAgent keeps its own conversation memory across both calls, so each
peer genuinely "remembers" its reasoning while it debates.
"""

from __future__ import annotations

import re

from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken
from autogen_core.models import ModelInfo
from autogen_ext.models.ollama import OllamaChatCompletionClient

# Shared character for every peer -- identical agents, so any disagreement comes
# from the model's own reasoning rather than from different instructions.
PERSONA = (
    "a careful problem-solver. You reason step by step, keep it brief, and you "
    "are genuinely willing to change your answer when a peer is more convincing."
)

# The ANSWER line must START its own line (allowing bullets/markdown like
# "* " or "**"), so prose such as "My current answer: No" can no longer be
# mistaken for the verdict. We also take the LAST match, because a model that
# restates itself puts its real conclusion at the end.
_ANSWER_RE = re.compile(r"^\W{0,4}ANSWER\W{0,4}:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_CONVINCED_RE = re.compile(r"^\W{0,4}CONVINCED_BY\W{0,4}:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_NO_ONE = {"none", "no one", "nobody", "n/a", "na", "myself", "self", ""}
_TRIM = " *_\"'`"
# Lines where an agent is quoting/discussing a peer rather than reasoning itself.
_QUOTES_PEER_RE = re.compile(
    r"(agent_\w+|peer_\w+|their reasoning|says\s*:)", re.IGNORECASE)


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


def make_model_client(model: str) -> OllamaChatCompletionClient:
    """A client for a local Ollama server (defaults to http://localhost:11434).

    Ollama models aren't in AutoGen's built-in registry, so we declare their
    capabilities explicitly via ModelInfo.
    """
    return OllamaChatCompletionClient(
        model=model,
        model_info=ModelInfo(
            vision=False,
            function_calling=False,
            json_output=False,
            family="unknown",
            structured_output=False,
        ),
    )


class PeerAgent:
    """One node in the network."""

    def __init__(self, name: str, client: OllamaChatCompletionClient):
        self.name = name
        self.answer = ""       # current one-line answer (the ANSWER: value)
        self.reasoning = ""    # full text of the latest reply
        self.parsed = True     # did the latest reply contain a usable ANSWER line?
        self._agent = AssistantAgent(
            name=name,
            model_client=client,
            system_message=(
                f"You are {name}, {PERSONA} "
                "Always end your reply with a line exactly like:\n"
                "ANSWER: <your final answer>"
            ),
        )

    async def _run(self, prompt: str) -> str:
        result = await self._agent.run(task=prompt)
        return result.messages[-1].content.strip()

    async def reset(self) -> None:
        """Clear this agent's memory (via the SDK) before a new question."""
        await self._agent.on_reset(CancellationToken())
        self.answer = ""
        self.reasoning = ""

    async def solve(self, question: str) -> str:
        """Phase 1: answer independently, having heard no peer yet."""
        text = await self._run(
            f"Solve this question on your own:\n{question}\n\n"
            "Show brief reasoning, then the ANSWER line."
        )
        self._absorb(text)
        return text

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

    async def reconsider(self, question: str, heard: dict[str, tuple[str, str]]) -> tuple[str, bool, str]:
        """Phase 2: hear neighbours; keep or change your own answer.

        `heard` maps a neighbour name -> (its answer, its reasoning-or-"").
        Returns (full_reply_text, changed?, convinced_by). `convinced_by` is the
        neighbour the model itself credits for changing its mind, or "" if none.
        """
        peers = "\n".join(
            f"- {n} answered: {a}" + (f"\n    (their working: {why})" if why else "")
            for n, (a, why) in heard.items()
        ) or "(nobody)"
        previous = self.answer
        text = await self._run(
            f"The question is:\n{question}\n\n"
            f"Your current answer: {previous}\n\n"
            f"Peers you can hear right now:\n{peers}\n\n"
            "If a peer's reasoning is more convincing, adopt the better answer and "
            "briefly say why. Otherwise defend yours.\n"
            "Add a line naming who changed your mind (a peer name, or 'none'):\n"
            "CONVINCED_BY: <name or none>\n"
            "Then end with the ANSWER line."
        )
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
        self.parsed = bool(hits)
        if hits:
            self.answer = hits[-1].strip(_TRIM)
        elif not self.answer:  # no ANSWER line at all on the very first turn
            self.answer = text.splitlines()[-1].strip(_TRIM) if text else ""
