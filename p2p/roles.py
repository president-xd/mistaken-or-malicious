"""Who lies, and which seat they take.

The user can do this two ways:

  attacker_places: "random"   pick the seats at random (uses the seed, so the
                              same seed always gives the same seats)
  attacker_places: "0,3"      use exactly these seats
  attacker_places: "center"   the hub seat, for star-shaped networks
  attacker_places: "leaf"     an outer seat, for star-shaped networks
  attacker_places: "strategic" topology-aware high-impact deterministic seats

The number of liars comes from `attackers`. If exact seats are listed, the list
wins and sets the count.
"""

from __future__ import annotations

import random


# Topologies where seat 0 is the hub and the rest are outer seats.
HUB_SHAPES = {"star", "tree", "hybrid"}


def _spread(indices: list[int], count: int) -> list[int]:
    """Choose deterministic, approximately evenly-spaced values from a list."""
    if count <= 0 or not indices:
        return []
    if count >= len(indices):
        return list(indices)
    if count == 1:
        return [indices[0]]
    positions = [round(i * (len(indices) - 1) / (count - 1))
                 for i in range(count)]
    return [indices[i] for i in dict.fromkeys(positions)]


def _strategic_indices(size: int, count: int, topology: str) -> list[int]:
    """Topology-aware worst-case seats, always returning exactly ``count``."""
    count = min(max(count, 0), size)
    if count == 0:
        return []
    kind = topology.lower()

    if kind in {"star", "hybrid"}:
        chosen = [0] + _spread(list(range(1, size)), count - 1)
    elif kind == "tree":
        leaves = list(range(size // 2, size))
        chosen = [0] + _spread(leaves, count - 1)
    elif kind == "line":
        center = (size - 1) // 2
        order = [center, 0, size - 1]
        order += sorted((i for i in range(size) if i not in order),
                        key=lambda i: (abs(i - center), i))
        chosen = order[:count]
    elif kind == "ring":
        chosen = _spread(list(range(size)), count)
    elif kind in {"p2p", "point-to-point"}:
        # Put attackers in different pairs before adding a second attacker to
        # any component.
        order = list(range(0, size, 2)) + list(range(1, size, 2))
        chosen = order[:count]
    else:  # mesh and bus are position-symmetric
        chosen = list(range(count))

    # Small or unusual graphs may make a strategy produce duplicates. Fill any
    # missing seats deterministically rather than silently returning fewer liars.
    chosen = list(dict.fromkeys(i for i in chosen if 0 <= i < size))
    chosen += [i for i in range(size) if i not in chosen][:count - len(chosen)]
    return chosen[:count]


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
        # A request for several attackers must never silently collapse to one.
        return names[:count]

    if wanted == "leaf":
        outer = names[1:] if topology in HUB_SHAPES else names
        picked = outer[:count]
        return picked + [n for n in names if n not in picked][:count - len(picked)]

    if wanted == "strategic":
        return [names[i] for i in _strategic_indices(len(names), count, topology)]

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
        if wanted not in ("random", "center", "leaf", "strategic"):
            return [f"'attacker_places: {places}' is not understood. Use "
                    f"random, center, leaf, strategic, or seat numbers like \"0,2\". "
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
    wanted = (places or "random").lower()
    how = ("seat chosen at random" if wanted == "random"
           else "topology-aware strategic seats" if wanted == "strategic"
           else f"seat set by config ({places})")
    return f"{', '.join(seats)}  ({how})"
