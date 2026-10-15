"""Build an A-E pool from the existing authored hard-question YAML set.

This preserves the source question, answer, and intended wrong answer. The three
additional choices are explicit distractors, not screening results.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

import yaml


LETTERS = "ABCDE"
DISTRACTORS = ("cannot be determined", "both options", "neither option")


def category(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("empire", "country", "university", "war", "pyramid")):
        return "history_geography"
    if any(word in lowered for word in ("percent", "speed", "price", "number", "probability", "dice")):
        return "quantitative"
    if any(word in lowered for word in ("https", "authentication", "checksum", "classifier")):
        return "security_and_reasoning"
    return "science_and_reasoning"


def _extra_values(answer: str, wrong: str) -> list[str]:
    values = []
    if {answer.lower(), wrong.lower()} == {"yes", "no"}:
        values.extend(("uncertain", "both", "neither"))
    else:
        values.extend(DISTRACTORS)
    return [value for value in values if value.lower() not in {answer.lower(), wrong.lower()}]


def _records(source: Path) -> list[dict]:
    return yaml.safe_load(source.read_text(encoding="utf-8")) or []


def build(source: Path, historical_commit: str | None = None,
          root: Path | None = None) -> list[dict]:
    records = _records(source)
    if historical_commit:
        try:
            raw = subprocess.check_output(
                ["git", "show", f"{historical_commit}:data/tricky_questions_100.yaml"],
                cwd=root or source.parent.parent, text=True,
            )
            records.extend(yaml.safe_load(raw) or [])
        except (OSError, subprocess.CalledProcessError) as error:
            raise SystemExit(f"cannot recover historical question source: {error}")
    unique = []
    seen = set()
    for record in records:
        text = str(record["text"]).strip()
        if text not in seen:
            seen.add(text)
            unique.append(record)
    records = unique
    output = []
    for index, record in enumerate(records, start=1):
        text = str(record["text"]).strip()
        answer = str(record["answer"]).strip()
        wrong = str(record["wrong"]).strip()
        values = [answer, wrong, *_extra_values(answer, wrong)]
        values = list(dict.fromkeys(values))[:5]
        if len(values) != 5:
            raise ValueError(f"question {index} does not have five distinct options")
        shift = index % 5
        rotated = values[shift:] + values[:shift]
        answer_letter = LETTERS[rotated.index(answer)]
        wrong_letter = LETTERS[rotated.index(wrong)]
        options = " ".join(f"{letter}) {value}" for letter, value in zip(LETTERS, rotated))
        output.append({
            "id": f"hard-{index:03d}",
            "category": category(text),
            "text": f"{text}\nOptions: {options}",
            "answer": answer_letter,
            "wrong": wrong_letter,
            "wrong_text": wrong,
        })
    return output


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--source", type=Path,
                        default=root / "data" / "questions_hard_50.yaml")
    parser.add_argument("--output", type=Path,
                        default=root / "data" / "questions_candidate_pool.jsonl")
    parser.add_argument("--test-output", type=Path,
                        default=root / "data" / "questions_test_50.jsonl")
    parser.add_argument("--historical-commit", default="d02099c",
                        help="recover the authored historical 100-question source")
    args = parser.parse_args()
    records = build(args.source.resolve(), args.historical_commit, root)
    write_jsonl(args.output.resolve(), records)
    write_jsonl(args.test_output.resolve(), records[:50])
    print(f"wrote {len(records)} authored questions to {args.output}")
    print(f"wrote {min(50, len(records))} test questions to {args.test_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())