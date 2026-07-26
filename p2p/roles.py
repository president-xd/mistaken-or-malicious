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


def check_places(names: list[str], count: int, places: str) -> list[str]:
    """Problems with `attacker_places` that would otherwise pass unnoticed.

    None of these stop a run. Each one means you quietly got a different
    experiment from the one you asked for, which is worse than a crash because
    the numbers still look fine.

    Measured examples, all silent before this existed:
      attackers: 2, places "1,1"  ->  ONE liar, because the repeat collapses
      attackers: 1, places "99"   ->  a RANDOM seat, because 99 does not exist
      attackers: 1, places "-1"   ->  a RANDOM seat, because "-1" is not a digit
      attackers: 1, places "x,y"  ->  a RANDOM seat, because nothing parsed
    """
    wanted = (places or "random").strip().lower()
    if count <= 0:
        return []
    if not any(ch.isdigit() for ch in wanted):
        # No digits at all, so it must be one of the words. Anything else is a
        # typo that silently behaves like "random" - e.g. "centre", "hub".
        if wanted not in ("random", "center", "leaf"):
            return [f"'attacker_places: {places}' is not understood. Use "
                    f"random, center, leaf, or seat numbers like \"0,2\". "
                    f"The seats were picked at RANDOM instead."]
        return []

    problems, seats = [], []
    for part in wanted.replace(" ", "").split(","):
        if not part:
            continue
        if not part.isdigit():
            problems.append(f"seat {part!r} is not a whole number and was ignored")
        elif int(part) >= len(names):
            problems.append(f"seat {part} does not exist - there are only "
                            f"{len(names)} agents (0 to {len(names) - 1})")
        else:
            seats.append(int(part))

    unique = list(dict.fromkeys(seats))
    if len(unique) < len(seats):
        problems.append(f"the same seat was listed more than once, so you get "
                        f"{len(unique)} liar(s), not {len(seats)}")
    if not unique and problems:
        problems.append("no usable seat was given, so the seats were picked at "
                        "RANDOM instead")
    elif unique and len(unique) != count:
        problems.append(f"'attackers' asks for {count} but the seat list names "
                        f"{len(unique)} - the seat list wins")
    return problems


def describe(seats: list[str], places: str) -> str:
    """One short line for the terminal, saying who lies and how it was decided."""
    if not seats:
        return "none - every agent is honest"
    how = "seat chosen at random" if (places or "random").lower() == "random" \
        else f"seat set by config ({places})"
    return f"{', '.join(seats)}  ({how})"
