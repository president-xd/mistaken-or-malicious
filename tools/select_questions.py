"""Select screened questions without padding or using attack results."""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def select(screening: list[dict], seed: int, limit_per_category: int = 15) -> list[dict]:
    eligible = [item for item in screening
                if 1 <= sum(answer == item["answer"] for answer in item["samples"]) <= 2]
    random.Random(seed).shuffle(eligible)
    counts = defaultdict(int)
    selected = []
    for item in eligible:
        category = item.get("category", "uncategorized")
        if counts[category] >= limit_per_category:
            continue
        item = dict(item)
        item["wrong"] = item.get("most_frequent_wrong") or item["wrong"]
        counts[category] += 1
        selected.append(item)
    return selected


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n"
                              for item in records), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/screening_report.json"))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--calibration", type=Path,
                        default=Path("data/questions_calibration.jsonl"))
    parser.add_argument("--test", type=Path,
                        default=Path("data/questions_test_50.jsonl"))
    parser.add_argument("--report", type=Path,
                        default=Path("data/screening_selection_report.json"))
    args = parser.parse_args()
    screening = json.loads(args.input.read_text(encoding="utf-8"))
    selected = select(screening, args.seed)
    if len(selected) < 60:
        args.report.write_text(json.dumps({
            "eligible": len(selected),
            "required": 60,
            "status": "stopped: fewer than 60 eligible questions",
        }, indent=2) + "\n", encoding="utf-8")
        print(f"stopped: only {len(selected)} eligible questions")
        return 2
    write_jsonl(args.calibration, selected[:10])
    write_jsonl(args.test, selected[10:60])
    print(f"selected {len(selected)} questions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())