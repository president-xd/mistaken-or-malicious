"""Communication topologies for the peer network.

A topology answers exactly one question: for a given peer, *which other peers
can it hear* during discussion? That neighbour set is all the network needs --
the discussion loop feeds each peer only its neighbours' current answers, so the
shape of information flow emerges entirely from this file.

None of these has an orchestrator. Even the star's hub is an ordinary peer that
answers the question like everyone else; it just happens to sit at the centre of
the wiring. To add a new topology, write a builder and register it below.
"""

from __future__ import annotations

from typing import Callable

# A builder maps the ordered agent names -> adjacency: name -> peers it hears.
Builder = Callable[[list[str]], dict[str, list[str]]]


def _mesh(names: list[str]) -> dict[str, list[str]]:
    """Fully connected: everyone hears everyone else."""
    return {n: [m for m in names if m != n] for n in names}


def _ring(names: list[str]) -> dict[str, list[str]]:
    """Each peer hears its two cyclic neighbours (previous and next)."""
    n = len(names)
    return {names[i]: [names[(i - 1) % n], names[(i + 1) % n]] for i in range(n)}


def _line(names: list[str]) -> dict[str, list[str]]:
    """Open chain: each peer hears only adjacent peers, with no wrap-around."""
    n = len(names)
    adj: dict[str, list[str]] = {}
    for i in range(n):
        nb = []
        if i > 0:
            nb.append(names[i - 1])
        if i < n - 1:
            nb.append(names[i + 1])
        adj[names[i]] = nb
    return adj


def _star(names: list[str]) -> dict[str, list[str]]:
    """Hub-and-spoke: names[0] is the hub wired to every spoke; each spoke hears
    only the hub. All information routes through the hub, yet the hub is still a
    normal peer that also answers -- not an orchestrator."""
    hub, spokes = names[0], names[1:]
    adj = {hub: list(spokes)}
    for s in spokes:
        adj[s] = [hub]
    return adj


_REGISTRY: dict[str, Builder] = {
    "mesh": _mesh,
    "ring": _ring,
    "line": _line,
    "star": _star,
}


def available() -> list[str]:
    """Names of every topology the config may select."""
    return sorted(_REGISTRY)


def build(kind: str, names: list[str]) -> dict[str, list[str]]:
    """Construct the adjacency map for `kind` over `names` (deduped, self-free)."""
    if len(names) < 2:
        raise SystemExit("need at least 2 agents to form a topology.")
    adj = _REGISTRY[kind.lower()](names)
    # Guard against duplicate/self neighbours (e.g. a 2-node ring).
    return {
        node: [p for p in dict.fromkeys(peers) if p != node]
        for node, peers in adj.items()
    }
