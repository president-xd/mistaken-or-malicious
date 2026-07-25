"""Decide which questions trust is allowed to learn from.

In a real system you do not get told the right answer every time. This lets you
copy that: learn from some questions, then freeze trust and test on the rest.

Three modes, set by `trust_learn_on` in the config:

  "all"     learn from every question (the simple default)
  "first"   learn from the first share of questions, then freeze
  "random"  learn from a random share, spread through the whole run

Every question gets a label that is printed and saved, so when you read the
results you can tell training questions from test questions.
"""

from __future__ import annotations

import math
import random

LEARN_MODES = ("all", "first", "random")


def build_plan(total: int, mode: str, share: float, seed: int) -> list[str]:
    """One label per question, worked out before the run starts.

    Labels: "learn" (trust updates) or "frozen" (trust is left alone).
    """
    mode = (mode or "all").lower()
    if mode == "all":
        return ["learn"] * total

    count = min(total, max(0, math.ceil(share * total)))

    if mode == "first":
        return ["learn"] * count + ["frozen"] * (total - count)

    # "random": same number of learning questions, but scattered about.
    picked = set(random.Random(seed).sample(range(total), count)) if count else set()
    return ["learn" if i in picked else "frozen" for i in range(total)]


def describe(plan: list[str], mode: str) -> str:
    """One short line for the terminal."""
    learn = plan.count("learn")
    return (f"trust learns from {learn}/{len(plan)} questions "
            f"(mode: {mode})")
