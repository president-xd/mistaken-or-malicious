"""Prepare a paired, stratified API gate from the final ring question set.

This only writes small question/config files. It does not make model calls.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/questions_test_50.jsonl"
GATE_QUESTIONS = ROOT / "data/questions_final_ring_gate_8.jsonl"
CONFIGS = ROOT / "configs/ring/fixed_pair"
OUT = ROOT / "results/final_ring_gate"


def main() -> None:
    records = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if len(records) != 50:
        raise SystemExit(f"Expected 50 final questions, found {len(records)}")

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        groups[str(row.get("category", "uncategorized"))].append(row)
    chosen = [row for category in sorted(groups) for row in groups[category][:2]]
    if len(chosen) != 8:
        raise SystemExit(f"Expected 8 questions (2 from each of 4 categories), found {len(chosen)}")
    GATE_QUESTIONS.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in chosen),
        encoding="utf-8",
    )

    for arm, trust, trust_share in (
        ("off", False, "off"),
        ("on", True, "broadcast"),
    ):
        source = CONFIGS / f"defence_{arm}.yaml"
        config = yaml.safe_load(source.read_text(encoding="utf-8"))
        config.update({
            "questions_file": "data/questions_final_ring_gate_8.jsonl",
            "max_questions": 8,
            "repeats": 1,
            "trust": trust,
            "trust_share": trust_share,
            "skip_done": False,
            "run_name": f"final_ring_gate_defence_{arm}",
            "results_dir": f"results/final_ring_gate/defence_{arm}",
        })
        target = CONFIGS / f"final_gate_defence_{arm}.yaml"
        target.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    print(f"Questions: {GATE_QUESTIONS.relative_to(ROOT)}")
    print("Selected:", ", ".join(row["id"] for row in chosen))
    print("Configurations:")
    print("  configs/ring/fixed_pair/final_gate_defence_off.yaml")
    print("  configs/ring/fixed_pair/final_gate_defence_on.yaml")
    print("Estimated baseline model calls: 560 (8 questions x 7 agents x 5 rounds x 2 arms).")


if __name__ == "__main__":
    main()
