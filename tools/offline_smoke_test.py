"""Run a no-provider smoke test for the five-round ring study."""

from __future__ import annotations

import asyncio
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p2p.config import Config, Question
from p2p.network import Network
from p2p.roles import choose_seats


class SmokeAgent:
    def __init__(self, name):
        self.name = name
        self.answer = ""
        self.belief = {}
        self.parsed = True
        self.retried = False
        self.turns = 0
        self.trust_seen = []

    def argument(self):
        return f"{self.name} reasoning"

    async def solve(self, question):
        self.answer = "A"
        return "ANSWER: A"

    async def reconsider(self, question, heard, trust=None):
        self.trust_seen.append(trust)
        self.turns += 1
        return "ANSWER: A", False, ""

    async def reset(self):
        self.answer = ""
        self.turns = 0


def run(trust_share: str) -> Network:
    names = [f"Agent_{letter}" for letter in "ABCDEFG"]
    agents = {name: SmokeAgent(name) for name in names}
    cfg = Config(
        questions=[Question("Q Options: A) one B) two C) three D) four E) five", "A", "B")],
        agents=7, rounds=5, topology="ring", trust=True,
        trust_share=trust_share, answer_format="letter", share="both")
    network = Network(cfg, client=None, agents=agents)
    with contextlib.redirect_stdout(io.StringIO()):
        asyncio.run(network.run_question(cfg.questions[0]))
    assert all(agent.turns == 4 for agent in agents.values())
    assert len(network.history) == 4
    assert len(network.trust_log) == 4
    if trust_share == "off":
        assert all(trust is None for agent in agents.values() for trust in agent.trust_seen)
    else:
        assert all(trust is not None for agent in agents.values() for trust in agent.trust_seen)
    return network


def main() -> int:
    names = [f"Agent_{letter}" for letter in "ABCDEFG"]
    expected = {
        "S1": ["Agent_A"], "S2": ["Agent_A", "Agent_B"],
        "S3": ["Agent_A", "Agent_D"], "S4": ["Agent_A", "Agent_B", "Agent_C"],
        "S5": ["Agent_A", "Agent_C", "Agent_E"],
    }
    for scenario, seats in (("S1", "0"), ("S2", "0,1"), ("S3", "0,3"),
                            ("S4", "0,1,2"), ("S5", "0,2,4")):
        assert choose_seats(names, len(seats.split(",")), seats, "ring", 1) == expected[scenario]
    run("off")
    run("broadcast")
    print("offline smoke: five rounds, trust visibility, logs, and seats passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())