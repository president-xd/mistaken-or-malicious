"""Screen multiple-choice questions with repeated solo model answers."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p2p import letters, providers
from p2p.agent import PeerAgent


def stratified(records: list[dict], limit: int | None) -> list[dict]:
    if not limit or limit >= len(records):
        return records
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[str(record.get("category", "uncategorized"))].append(record)
    selected = []
    while len(selected) < limit:
        progressed = False
        for group in groups.values():
            if group and len(selected) < limit:
                selected.append(group.pop(0))
                progressed = True
        if not progressed:
            break
    return selected


def parsed_answer(raw: str) -> str:
    matches = re.findall(r"^\W{0,4}ANSWER\W{0,4}:\s*(.+?)\s*$",
                         raw, flags=re.IGNORECASE | re.MULTILINE)
    return letters.canonical_letter(matches[-1]) if matches else ""


async def screen(path: Path, provider: str, model: str, seed: int,
                 samples: int = 5, concurrency: int = 20,
                 limit: int | None = None, temperature: float = 0.7) -> list[dict]:
    records = [json.loads(line) for line in
               path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    records = stratified(records, limit)
    limiter = asyncio.Semaphore(concurrency)

    async def run_sample(record: dict, sample_index: int) -> tuple[str, str]:
        async with limiter:
            client = providers.make_client(
                provider, model, seed + sample_index, temperature)
            agent = PeerAgent("Screen", client, answer_format="letter")
            try:
                raw = await agent.solve(record["text"])
                return parsed_answer(raw) or agent.answer.upper(), raw
            finally:
                await client.close()

    async def screen_one(record: dict) -> dict:
        samples_out = await asyncio.gather(
            *(run_sample(record, sample_index) for sample_index in range(samples)))
        answers = [answer for answer, _ in samples_out]
        correct = str(record["answer"]).upper()
        wrong = Counter(answer for answer in answers if answer != correct)
        return {
            **record,
            "samples": answers,
            "raw_samples": [raw for _, raw in samples_out],
            "correct_count": sum(answer == correct for answer in answers),
            "solo_accuracy": sum(answer == correct for answer in answers) / samples,
            "most_frequent_wrong": wrong.most_common(1)[0][0]
            if wrong else str(record.get("wrong", "")).upper(),
        }

    return await asyncio.gather(*(screen_one(record) for record in records))


def print_histogram(rows: list[dict], samples: int, title: str) -> None:
    print(title)
    counts = Counter(row["correct_count"] for row in rows)
    for correct in range(samples + 1):
        print(f"  {correct}/{samples}: {counts.get(correct, 0)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--pool", "--input", dest="pool",
                        type=Path, default=Path("data/questions_candidate_pool.jsonl"))
    parser.add_argument("--output", type=Path,
                        default=Path("data/questions_screened.jsonl"))
    parser.add_argument("--report", type=Path,
                        default=Path("data/screening_report.json"))
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-chat")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=20)
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Refusing model calls. Re-run with --yes after confirming.")
    if args.samples < 2 or args.concurrency < 1:
        raise SystemExit("--samples must be at least 2 and --concurrency at least 1")
    providers.check_ready(args.provider)
    result = asyncio.run(screen(
        args.pool, args.provider, args.model, args.seed, args.samples,
        args.concurrency, args.limit, args.temperature))

    print_histogram(result, args.samples, "overall correct-count histogram")
    categories = sorted({str(row.get("category", "uncategorized"))
                         for row in result})
    for category in categories:
        print_histogram(
            [row for row in result
             if str(row.get("category", "uncategorized")) == category],
            args.samples, f"category: {category}")

    zero_rows = [row for row in result if row["correct_count"] == 0]
    for row in zero_rows[:1]:
        print(f"raw outputs for zero-score question {row.get('id', '')}:")
        for raw in row["raw_samples"][:2]:
            print("---")
            print(raw)

    intermediate = [row for row in result
                    if 0 < row["correct_count"] < args.samples]
    if len(intermediate) < 60:
        print(f"screening stopped: only {len(intermediate)} intermediate questions "
              "remain; at least 60 are required")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in intermediate:
            stream.write(json.dumps({
                **{key: value for key, value in row.items()
                   if key != "raw_samples"},
                "wrong": row["most_frequent_wrong"],
            }) + "\n")
    args.report.write_text(json.dumps({
        "pool": str(args.pool), "model": args.model,
        "temperature": args.temperature, "samples": args.samples,
        "questions_screened": len(result),
        "intermediate_questions": len(intermediate),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"screened {len(intermediate)} questions -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
