"""Honesty test harness for the P2P network.

Runs the REAL program (`python -m p2p`) across different questions, agent counts,
and topologies, then parses the terminal logs to answer one question:

    Are agents changing their mind because a peer convinced them,
    or is the "change" hard-coded?

Evidence we collect per run:
  * how many changes happened,
  * how many of those name a REAL neighbour as the convincer
    (the parser in agent.py only accepts a peer the agent could actually hear),
  * whether behaviour differs across questions/topologies (a hard-coded rule
    would behave identically regardless).

Usage:  python run_experiments.py
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ANSI = re.compile(r"\x1b\[[0-9;]*m")
CHANGED = re.compile(r"(Agent_\w+) CHANGED its mind - (convinced by (Agent_\w+)|on its own)")
CONSENSUS = re.compile(r"(CONSENSUS reached|No full consensus)")

# question, num_agents, topology  -- varied on purpose to expose any hard-coding.
MATRIX = [
    ("What is the capital of Australia? Answer with just the city name.", 3, "star"),
    ("What is 17 * 24? Show your working.", 4, "ring"),
    ("Is a hot dog a sandwich? Answer yes or no and justify briefly.", 2, "line"),
    ("What is the capital of Australia? Answer with just the city name.", 4, "mesh"),
]


def run_one(question: str, num_agents: int, topology: str) -> dict:
    cfg = {
        "question": question,
        "model": "llama3.2:1b",
        "num_agents": num_agents,
        "rounds": 2,
        "topology": topology,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
        path = f.name

    out = subprocess.run(
        [sys.executable, "-m", "p2p", path],
        capture_output=True, text=True, encoding="utf-8", cwd=Path(__file__).parent,
    ).stdout
    Path(path).unlink(missing_ok=True)
    clean = ANSI.sub("", out)

    changes = CHANGED.findall(clean)              # list of (agent, tail, convincer)
    peer_driven = [c for c in changes if c[2]]    # a real neighbour was credited
    consensus = (CONSENSUS.search(clean) or [""])[0]
    return {
        "changes": len(changes),
        "peer_driven": len(peer_driven),
        "convincers": [f"{c[0]}<-{c[2]}" for c in peer_driven],
        "consensus": consensus,
    }


def main() -> None:
    print("Running experiments (this calls the real model, please wait)...\n")
    rows = []
    for question, n, topo in MATRIX:
        r = run_one(question, n, topo)
        rows.append((question, n, topo, r))
        print(f"[done] agents={n} topology={topo:5} "
              f"changes={r['changes']} peer-driven={r['peer_driven']} "
              f"| {r['consensus']}")

    print("\n================ SUMMARY ================")
    for question, n, topo, r in rows:
        print(f"\nQ: {question}")
        print(f"   agents={n} topology={topo}")
        print(f"   mind-changes: {r['changes']} "
              f"(peer-driven: {r['peer_driven']})")
        if r["convincers"]:
            print(f"   who convinced whom: {', '.join(r['convincers'])}")
        print(f"   outcome: {r['consensus']}")


if __name__ == "__main__":
    main()
