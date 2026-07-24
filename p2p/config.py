"""Load and validate config.yaml into a typed object.

The user picks only a handful of things: the question, how many agents, which
topology they talk over, the Ollama model, and how many discussion rounds.
Agent names/personas are NOT configured here -- they are generated at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from . import topology


@dataclass
class Config:
    questions: list[str]
    model: str = "llama3.2:1b"
    num_agents: int = 3
    rounds: int = 2
    topology: str = "mesh"


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # Accept a list under 'questions', or a single string under 'question'.
    raw_qs = raw.get("questions", raw.get("question"))
    if isinstance(raw_qs, str):
        raw_qs = [raw_qs]
    questions = [str(q).strip() for q in (raw_qs or []) if str(q).strip()]
    if not questions:
        raise SystemExit(f"config error: provide 'questions' (a list) or 'question' in {path}")

    cfg = Config(
        questions=questions,
        model=str(raw.get("model", "llama3.2:1b")),
        num_agents=int(raw.get("num_agents", 3)),
        rounds=int(raw.get("rounds", 2)),
        topology=str(raw.get("topology", "mesh")).lower(),
    )

    if cfg.num_agents < 2:
        raise SystemExit("config error: 'num_agents' must be at least 2.")
    if cfg.rounds < 1:
        raise SystemExit("config error: 'rounds' must be at least 1.")
    if cfg.topology not in topology.available():
        raise SystemExit(
            f"config error: unknown topology '{cfg.topology}'. "
            f"choose one of: {', '.join(topology.available())}"
        )

    return cfg
