"""Turn an agent's answer text into a vector, so answers can be compared.

The trust signals need to measure how close two answers are. To do that we ask
a small embedding model to turn each answer into a list of numbers. Answers
that mean similar things end up close together.

There are two ways to compare answers, chosen by `scoring` in the config:

  "answer"  compare the answer text directly. Two agents agree if they wrote
            the same thing. Simple, exact, needs no extra model.

  "text"    use the embedding model. Works when answers are open text and
            there is no single right wording.

A warning that is easy to miss: embedding models measure what an answer is
ABOUT, not whether it agrees. We measured "Yes, a hot dog is a sandwich"
against "No, a hot dog is not a sandwich" and got 0.98 similarity, because the
two sentences are about the same thing. This is why `trust.sharpen` exists and
why "answer" is the default.
"""

from __future__ import annotations

import ollama

from .agent import _norm


class Embedder:
    """Makes vectors from text. Remembers what it has already done."""

    def __init__(self, model: str = "nomic-embed-text"):
        self.model = model
        self._seen: dict[str, list[float]] = {}

    def vector(self, text: str) -> list[float]:
        """The vector for one piece of text. Repeated text is not re-sent."""
        key = text.strip()
        if key not in self._seen:
            reply = ollama.embeddings(model=self.model, prompt=key or " ")
            self._seen[key] = list(reply["embedding"])
        return self._seen[key]


class ExactMatch:
    """The simple alternative to embeddings.

    Every distinct answer becomes its own direction, so two agents score 1.0
    when they wrote the same answer and 0.0 when they did not. No model needed,
    and the separation is perfectly clean.
    """

    def __init__(self):
        self._slots: dict[str, int] = {}

    def _same_as_existing(self, key: str) -> str | None:
        """Find an answer already seen that means the same thing.

        Real agents write the same answer in different words: "shakespeare" and
        "william shakespeare", or "Tokyo" and "Tokyo, Japan". Comparing the raw
        text would call those two different answers, so two honest agents that
        actually agree would look like they disagree.

        The rule: if one answer's words are all inside the other's, they are the
        same answer. "canberra" and "melbourne" share no words, so they stay
        different, and so do "yes" and "no".
        """
        words = set(key.split())
        if not words:
            return None
        for seen in self._slots:
            other = set(seen.split())
            if other and (words <= other or other <= words):
                return seen
        return None

    def vector(self, text: str) -> list[float]:
        key = _norm(text)
        match = self._same_as_existing(key)
        if match is not None:
            key = match
        if key not in self._slots:
            self._slots[key] = len(self._slots)
        # A one-hot vector: 1 in this answer's slot, 0 everywhere else.
        size = len(self._slots)
        vec = [0.0] * size
        vec[self._slots[key]] = 1.0
        return vec

    def pad_all(self, vectors: list[list[float]]) -> list[list[float]]:
        """Make every vector the same length, since new answers keep appearing."""
        width = len(self._slots)
        return [v + [0.0] * (width - len(v)) for v in vectors]


def make_embedder(scoring: str, model: str):
    """Pick the comparer named in the config."""
    return Embedder(model) if scoring == "text" else ExactMatch()
