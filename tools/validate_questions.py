"""Validate A-E multiple-choice JSONL questions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


LETTERS = set("ABCDE")


def validate(path: Path) -> list[str]:
    errors = []
    seen = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"line {line_number}: invalid JSON ({error.msg})")
            continue
        text = str(item.get("text", ""))
        answer = str(item.get("answer", "")).upper()
        wrong = str(item.get("wrong", "")).upper()
        if text in seen:
            errors.append(f"line {line_number}: duplicate question text")
        seen.add(text)
        if not all(f"{letter})" in text or f"{letter}." in text for letter in LETTERS):
            errors.append(f"line {line_number}: text must contain options A-E")
        if answer not in LETTERS or len(answer) != 1:
            errors.append(f"line {line_number}: answer must be one letter A-E")
        if wrong not in LETTERS or len(wrong) != 1:
            errors.append(f"line {line_number}: wrong must be one letter A-E")
        if answer == wrong:
            errors.append(f"line {line_number}: answer and wrong must differ")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    args = parser.parse_args()
    errors = validate(args.questions)
    if errors:
        print("\n".join(errors))
        return 1
    print(f"valid questions: {args.questions}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())