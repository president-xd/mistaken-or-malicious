"""Run the real program across many setups and look for problems on OUR side.

This is not a unit test. It runs `python -m p2p` exactly as a person would,
against a real model, and then reads back what happened. Unit tests prove the
maths; this proves the whole thing behaves when a real model is on the end of
it.

What we are hunting for is OUR mistakes, not the model's:

  * a measure that comes out impossible (a share above 100%, a negative rate)
  * the liar being trusted MORE than the honest agents
  * an honest agent punished for no reason (a false alarm)
  * trust still swinging about when the run ends, meaning too few rounds
  * the code and the maths disagreeing
  * a topology where nobody can hear anybody
  * answers that never got parsed, so an agent was frozen

Usage:
    set DEEPSEEK_API_KEY first, then

    python dynamic-tests/deep_test.py                 # the whole campaign
    python dynamic-tests/deep_test.py --only star     # one setup
    python dynamic-tests/deep_test.py --repeats 1     # quicker
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LOGS = ROOT / "dynamic-tests" / "logs"

# Colour codes in the captured log get in the way of reading it.
ANSI = re.compile(r"\x1b\[[0-9;]*m")

# Every setup shares these. Only the differences are listed per setup below.
BASE = {
    "provider": "deepseek",
    "model": "deepseek-v4-pro",
    "questions_file": "data/hard_questions.yaml",
    "max_questions": 4,
    "agents": 4,
    "rounds": 5,
    "topology": "mesh",
    "seed": 1,
    "trust": True,
    "scoring": "answer",
    "trust_memory": 0.8,
    "weight_agree": 0.5,
    "weight_consist": 0.0,
    "weight_anomaly": 0.5,
    "attackers": 1,
    "attacker_places": "random",
    "compare_baseline": True,
    "parallel": True,
}

# The campaign. Each one asks a different question of the method.
SETUPS = {
    "one_liar": {
        "why": "the ordinary case: one liar among four, everyone hears everyone",
    },
    "two_liars": {
        "why": "does it still work when the liar has help?",
        "agents": 5, "attackers": 2,
    },
    "half_liars": {
        "why": "KNOWN HARD: half the network lies, so 'agree' cannot tell "
               "which half is honest",
        "agents": 4, "attackers": 2,
    },
    "star_hub": {
        "why": "the strongest attack: the liar is the hub, so every honest "
               "agent hears ONLY the liar",
        "topology": "star", "attacker_places": "center",
    },
    "ring": {
        "why": "each agent hears only its two neighbours",
        "topology": "ring",
    },
    "line": {
        "why": "a chain: the two ends hear one neighbour each",
        "topology": "line",
    },
    "sleeper": {
        "why": "HARDEST: the liar behaves well first to earn trust, then lies",
        "sleeper": True, "warmup": 1, "max_questions": 6,
        "weight_agree": 0.33, "weight_consist": 0.34, "weight_anomaly": 0.33,
    },
}


def build_config(name: str, repeats: int) -> Path:
    """Write the YAML for one setup and give back its path."""
    settings = dict(BASE)
    settings.update({k: v for k, v in SETUPS[name].items() if k != "why"})
    settings["repeats"] = repeats
    settings["run_name"] = f"deep_{name}"
    path = ROOT / "dynamic-tests" / f"_deep_{name}.yaml"
    path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")
    return path


def run_one(name: str, repeats: int) -> dict:
    """Run one setup all the way through and read back what happened."""
    config = build_config(name, repeats)
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{name}.log"

    print(f"\n{'=' * 74}\n{name}\n  {SETUPS[name]['why']}\n{'=' * 74}")
    started = time.time()
    finished = subprocess.run(
        [sys.executable, "-m", "p2p", str(config), "--result", "json"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace")
    took = time.time() - started

    log = ANSI.sub("", finished.stdout + finished.stderr)
    log_path.write_text(log, encoding="utf-8")

    if finished.returncode != 0:
        print(f"  RUN FAILED after {took:.0f}s. Last lines:")
        print("\n".join(f"    {ln}" for ln in log.strip().splitlines()[-8:]))
        return {"name": name, "ok": False, "seconds": took, "log": log}

    result_file = RESULTS / f"deep_{name}.json"
    data = json.loads(result_file.read_text(encoding="utf-8"))
    print(f"  finished in {took:.0f}s   ->  {result_file.name}")
    return {"name": name, "ok": True, "seconds": took, "log": log, "data": data}


# ------------------------------------------------------- looking for problems

def find_problems(run: dict) -> list[str]:
    """Read one finished run and list anything that looks like OUR bug."""
    if not run.get("ok"):
        return ["the run did not finish"]

    found, data = [], run["data"]
    log = run["log"]

    # -- impossible numbers. These can only come from a mistake in our code.
    for question in data.get("questions", []):
        scores = question.get("scores", {})
        for key in ("honest_accuracy", "attack_success_rate",
                    "attacker_influence", "equal_share"):
            value = scores.get(key)
            if value is not None and not 0.0 <= value <= 1.0:
                found.append(f"{key} is {value}, which is outside 0 to 1")
        separation = scores.get("trust_separation")
        if separation is not None and not -1.0 <= separation <= 1.0:
            found.append(f"trust_separation is {separation}, outside -1 to 1")

        # -- the defence working backwards: the liar trusted MORE than honest.
        if separation is not None and separation < 0:
            found.append(f"the liar ended up MORE trusted than the honest "
                         f"agents (separation {separation:+.3f})")

        # -- an honest agent punished for no reason.
        alarm = scores.get("false_alarm")
        if alarm is not None and alarm > 0.25:
            found.append(f"false alarm {alarm:.3f}: honest agents were treated "
                         f"very differently from each other")

        # -- trust never settled, so the run was too short.
        moving = scores.get("still_moving")
        if moving is not None and moving > 0.10:
            found.append(f"trust was still moving ({moving:.3f}) when the run "
                         f"ended - needs more rounds")

        # -- the code and the formula disagree.
        theory = scores.get("matches_theory")
        if theory is not None and theory > 0.10:
            found.append(f"code and maths disagree by {theory:.4f}")

    # -- an agent whose reply could never be read, so it was frozen.
    stuck = log.count("no ANSWER line after retry")
    if stuck:
        found.append(f"{stuck} reply(s) could not be read even after a retry")

    # -- a topology that left somebody with no neighbours.
    if "--> (nobody)" in log:
        found.append("at least one agent could hear nobody at all")

    # -- influence shares that do not add up.
    for question in data.get("questions", []):
        for rnd in question.get("rounds", []):
            for listener, row in (rnd.get("influence") or {}).items():
                total = sum(row.values())
                if row and abs(total - 1.0) > 0.01:
                    found.append(f"{listener}'s attention shares add up to "
                                 f"{total:.3f}, not 1")
                    break

    return sorted(set(found))


def headline(run: dict) -> dict:
    """The numbers worth putting in a table."""
    if not run.get("ok"):
        return {}
    data = run["data"]
    repeats = data.get("repeats", {})
    if repeats:
        left = (repeats.get("compared_against") or {}).get("average", {})
        right = repeats.get("average", {})
        pick = lambda block, key: (block.get(key) or {}).get("mean")
    else:
        comparison = data.get("comparison", {})
        left = comparison.get("without_trust", {})
        right = comparison.get("with_trust", {})
        pick = lambda block, key: block.get(key)
    return {
        "acc_off": pick(left, "honest_accuracy"),
        "acc_on": pick(right, "honest_accuracy"),
        "asr_off": pick(left, "attack_success_rate"),
        "asr_on": pick(right, "attack_success_rate"),
        "sep_on": pick(right, "trust_separation"),
        "inf_off": pick(left, "attacker_influence"),
        "inf_on": pick(right, "attacker_influence"),
    }


def show_table(runs: list[dict]) -> None:
    def cell(value, percent=True):
        if value is None:
            return "   n/a"
        return f"{value:6.1%}" if percent else f"{value:+6.3f}"

    print(f"\n{'=' * 96}\nALL SETUPS - without trust  ->  with trust\n{'=' * 96}")
    print(f"  {'setup':12} {'accuracy':>17} {'attack success':>17} "
          f"{'attacker share':>17} {'separation':>11}")
    for run in runs:
        h = headline(run)
        if not h:
            print(f"  {run['name']:12}   DID NOT FINISH")
            continue
        print(f"  {run['name']:12} "
              f"{cell(h['acc_off'])} ->{cell(h['acc_on'])} "
              f"{cell(h['asr_off'])} ->{cell(h['asr_on'])} "
              f"{cell(h['inf_off'])} ->{cell(h['inf_on'])} "
              f"{cell(h['sep_on'], False):>11}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default=None, help="run just one setup")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()

    names = [args.only] if args.only else list(SETUPS)
    for name in names:
        if name not in SETUPS:
            raise SystemExit(f"unknown setup {name!r}. "
                             f"choose from: {', '.join(SETUPS)}")

    runs = [run_one(name, args.repeats) for name in names]
    show_table(runs)

    print(f"\n{'=' * 96}\nPROBLEMS FOUND ON OUR SIDE\n{'=' * 96}")
    total = 0
    for run in runs:
        problems = find_problems(run)
        total += len(problems)
        if problems:
            print(f"\n  {run['name']}:")
            for problem in problems:
                print(f"    - {problem}")
    if not total:
        print("\n  None. Every number was inside its allowed range, the trust\n"
              "  values settled, and the code agreed with the formula.")
    print(f"\n  Logs are in {LOGS}")


if __name__ == "__main__":
    main()
