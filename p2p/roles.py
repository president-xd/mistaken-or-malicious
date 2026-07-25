"""Who lies, and which seat they take.

The user can do this two ways:

  attacker_places: "random"   pick the seats at random (uses the seed, so the
                              same seed always gives the same seats)
  attacker_places: "0,3"      use exactly these seats
  attacker_places: "center"   the hub seat, for star-shaped networks
  attacker_places: "leaf"     an outer seat, for star-shaped networks

The number of liars comes from `attackers`. If exact seats are listed, the list
wins and sets the count.
"""

from __future__ import annotations

import random


# Topologies where seat 0 is the hub and the rest are outer seats.
HUB_SHAPES = {"star", "tree", "hybrid"}


def choose_seats(names: list[str], count: int, places: str,
                 topology: str, seed: int) -> list[str]:
    """Return the names of the agents that will lie.

    `names` is every agent in seat order. `count` is how many should lie.
    """
    if count <= 0:
        return []
    count = min(count, len(names))
    wanted = (places or "random").strip().lower()

    # An explicit list of seat numbers, e.g. "0,3".
    if any(ch.isdigit() for ch in wanted):
        seats = []
        for part in wanted.replace(" ", "").split(","):
            if part.isdigit() and int(part) < len(names):
                seats.append(int(part))
        if seats:
            return [names[i] for i in dict.fromkeys(seats)]

    if wanted == "center":
        return [names[0]] if topology in HUB_SHAPES else names[:count]

    if wanted == "leaf":
        outer = names[1:] if topology in HUB_SHAPES else names
        return outer[:count]

    # Default: random seats, but repeatable because the seed is fixed.
    return random.Random(seed).sample(names, count)


def describe(seats: list[str], places: str) -> str:
    """One short line for the terminal, saying who lies and how it was decided."""
    if not seats:
        return "none - every agent is honest"
    how = "seat chosen at random" if (places or "random").lower() == "random" \
        else f"seat set by config ({places})"
    return f"{', '.join(seats)}  ({how})"
