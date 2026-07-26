"""The dynamic trust formula. Pure maths - no model calls, no network code.

Master formula:

    new_trust = memory * old_trust + (1 - memory) * score

The score grades how an agent behaved this round:

    score = w_agree * agree + w_consist * consist + w_anomaly * (1 - anomaly)
    (the three weights must add up to 1)

The three signals, all between 0 and 1:

    agree    how close this agent is to the average of the others
    consist  how close its answer is to its own answer last round
    anomaly  how far it sits from every other agent

`anomaly` is flipped with (1 - anomaly) because a high anomaly is bad, while
high agree and high consist are good. Every part of the score must point the
same way.

Two facts that come out of the formula and are useful when reading results:
  * trust always ends up at the score value (if the score stays the same)
  * it takes ln(0.5)/ln(memory) rounds to lose half of an old trust value
"""

from __future__ import annotations

import math

# "I have no information." Used when a signal cannot be measured at all, such
# as consistency in the very first round when there is no previous answer yet.
#
# This is NOT a similarity value, so it must never be passed through
# stretch_exact. Doing so maps it to 0.0, the worst possible score, and
# punishes every agent for having no history. See network.update_trust.
NEUTRAL = 0.5


# --------------------------------------------------------------- basic tools

def similarity(a: list[float], b: list[float]) -> float:
    """How alike two vectors are, as a number from 0 to 1.

    Cosine gives -1 to +1, so we shift it into 0 to 1 with (cos + 1) / 2.
    Every signal below uses this, never raw cosine, so scores stay in range.
    """
    dot = sum(x * y for x, y in zip(a, b))
    size_a = math.sqrt(sum(x * x for x in a))
    size_b = math.sqrt(sum(x * x for x in b))
    if size_a == 0 or size_b == 0:
        return 0.5  # nothing to compare, stay neutral
    return (dot / (size_a * size_b) + 1) / 2


def average_vector(vectors: list[list[float]]) -> list[float]:
    """The middle point of a group of vectors."""
    if not vectors:
        return []
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(len(vectors[0]))]


# ------------------------------------------------------------- three signals

def agree_score(speaker: list[float], others: list[list[float]]) -> float:
    """Does this agent match the group?

    The speaker is left out of the group average. If we left it in, it would be
    partly compared against itself, which would flatter its score.
    """
    if not others:
        return 0.5
    return similarity(speaker, average_vector(others))


def consist_score(now: list[float], before: list[float] | None) -> float:
    """Is this agent saying the same thing as last round?

    In round 1 there is no previous answer, so we return 0.5 (neutral).

    NOTE, and this matters when reading results: this signal REWARDS an agent
    that never moves. A liar that repeats the same wrong answer scores high
    here, while an honest agent that is genuinely persuaded scores low. The
    other two signals are what catch the liar. If your attacker always says the
    same thing, lower `weight_consist` in the config.
    """
    if before is None:
        return 0.5
    return similarity(now, before)


def anomaly_score(speaker: list[float], others: list[list[float]]) -> float:
    """How far is this agent from everyone else?

    Different from `agree`: agree compares against one averaged point, this
    compares against each agent separately and then averages. They disagree
    when the group has split into two camps.
    """
    if not others:
        return 0.0
    mean_similarity = sum(similarity(speaker, o) for o in others) / len(others)
    return 1 - mean_similarity


# -------------------------------------------------------------- the score

def behaviour_score(agree: float, consist: float, anomaly: float,
                    w_agree: float, w_consist: float, w_anomaly: float) -> float:
    """Turn the three signals into one grade from 0 to 1."""
    return w_agree * agree + w_consist * consist + w_anomaly * (1 - anomaly)


def update_trust(old_trust: float, score: float, memory: float) -> float:
    """The master formula. `memory` is beta: how much of the old value to keep."""
    return memory * old_trust + (1 - memory) * score


# ---------------------------------------------------------- helpful readings

def influence_shares(trust_row: dict[str, float]) -> dict[str, float]:
    """Turn one agent's trust scores into shares that add up to 1.

    This is 'communication strength': how much of this listener's attention
    each speaker actually gets. Without trust everyone gets an equal share.
    """
    total = sum(trust_row.values())
    if total <= 0:
        equal = 1 / len(trust_row) if trust_row else 0
        return {name: equal for name in trust_row}
    return {name: value / total for name, value in trust_row.items()}


def half_life(memory: float) -> float:
    """How many rounds until an old trust value loses half its weight."""
    if not 0 < memory < 1:
        return float("inf")
    return math.log(0.5) / math.log(memory)


def memory_length(memory: float) -> float:
    """Roughly how many past rounds the trust value is averaging over."""
    return float("inf") if memory >= 1 else 1 / (1 - memory)


def settles_at(score: float) -> float:
    """Where trust ends up if the score stays the same. It is just the score."""
    return score


def trust_after(rounds: int, start: float, score: float, memory: float) -> float:
    """Jump straight to any round without looping. Used to check the loop."""
    return score + (start - score) * (memory ** rounds)


# ------------------------------------------------------------ making it fair

def stretch_exact(value: float, is_anomaly: bool = False) -> float:
    """Fix the range when answers are compared exactly instead of by meaning.

    With exact matching, each answer becomes its own direction. Two different
    answers are then at right angles, and a right angle gives similarity 0.5,
    not 0. So the signal only ever moves between 0.5 and 1.0 - half the range
    the formula expects. A stubborn liar would score 0.667, which is above the
    neutral 0.5, so it would look better than a fair coin.

    This stretches the used half back over the full 0 to 1 range.
    """
    if is_anomaly:
        # anomaly = 1 - mean similarity, so it sits in 0 .. 0.5
        return min(1.0, max(0.0, 2 * value))
    return min(1.0, max(0.0, 2 * value - 1))


def sharpen(scores: dict[str, float], smallest_gap: float = 0.05) -> dict[str, float]:
    """Stretch a set of scores so small differences become visible.

    Why this exists: real text embeddings squash everything into a narrow band.
    Measured on our own answers, an honest agent scored 0.9914 and a liar 0.9228
    - a gap of only 0.07, where the design assumed about 0.40. Left alone, the
    defence would barely work.

    So we stretch whatever range we actually saw across the full 0 to 1 range.

    If everybody really is alike (the gap is below `smallest_gap`), we leave the
    scores untouched. Otherwise a network of honest agents would be pulled apart
    for no reason.
    """
    if not scores:
        return {}
    low, high = min(scores.values()), max(scores.values())
    if high - low < smallest_gap:
        return dict(scores)
    return {name: (value - low) / (high - low) for name, value in scores.items()}
