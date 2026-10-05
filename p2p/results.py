"""Save a run to one JSON file.

Turned on with `--result json` on the command line. Everything the terminal
shows also goes in here, plus the performance numbers, so a run can be checked
or re-read long after it finished.

One file per run, written to the `results` folder.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import fields
from datetime import datetime
from pathlib import Path


class Results:
    """Collects everything during a run, then writes it out at the end."""

    def __init__(self, cfg, agents, liars):
        self.data = {
            "settings": {
                # EVERY setting, taken straight from the Config object rather
                # than listed by hand. A hand-written list went stale: 18 of
                # the 35 settings were missing, including ones that change the
                # result - sharpen, start_trust, warmup, trust_floor, parallel.
                # Anyone reading the file could not have reproduced the run.
                #
                # Reading the fields means a new setting is recorded the day it
                # is added, with nothing to remember.
                **{f.name: getattr(cfg, f.name)
                   for f in fields(cfg) if f.name != "questions"},
                # Kept for readers and for older tools: who actually lied, and
                # the three weights grouped together.
                "attacker_seats": list(liars),
                "weights": {
                    "agree": round(cfg.weight_agree, 4),
                    "consist": round(cfg.weight_consist, 4),
                    "anomaly": round(cfg.weight_anomaly, 4),
                },
            },
            "agents": [
                {"name": n, "role": "liar" if n in liars else "honest"}
                for n in agents
            ],
            "questions": [],
            "summary": {},
        }
        self._question = None
        self._trust_log = []
        self._trust_log_written = 0
        # Which repeat we are inside. Stays 1 when repeats is 1.
        self._repeat, self._seed = 1, cfg.seed

    # ---------------------------------------------------------- during a run

    def start_repeat(self, number, seed):
        """A new repeat of the whole experiment has begun.

        Every question recorded from now on is stamped with this number, so
        nothing from the earlier repeats is overwritten or lost.
        """
        self._repeat, self._seed = number, seed

    def start_question(self, text, correct):
        self._question = {
            "repeat": self._repeat,
            "seed": self._seed,
            "text": text,
            "correct_answer": correct,
            "rounds": [],
            "final_answers": {},
            "scores": {},
        }
        self.data["questions"].append(self._question)

    def discard_question(self):
        """Throw away the question being recorded right now.

        Used when a question failed part-way through and is about to be tried
        again. Without it the retry would append a second entry and the file
        would hold the same question twice, once truncated.
        """
        if self._question is not None and self.data["questions"]:
            if self.data["questions"][-1] is self._question:
                self.data["questions"].pop()
        self._question = None

    def record_failed_question(self, text, correct, error):
        """Keep a marker for a question that could not be completed.

        The entry carries no rounds and no scores, so it never reaches the
        metrics: `Network.rows` only gains a row when a question finishes.
        It exists so the file says plainly which questions are missing and
        why, instead of leaving a silent gap that looks like a shorter run.
        """
        self.data["questions"].append({
            "repeat": self._repeat,
            "seed": self._seed,
            "text": text,
            "correct_answer": correct,
            "failed": True,
            "error": str(error)[:500],
            "rounds": [],
            "final_answers": {},
            "scores": {},
        })
        self._question = None

    def add_round(self, number, agents, trust=None, signals=None, influence=None):
        """Record one round: what each agent said, and the trust maths behind it."""
        entry = {
            "round": number,
            "agents": {
                name: {
                    "answer": a.answer,
                    "confidence": round(a.belief.get(a.answer, 1.0), 4),
                    "belief": {k: round(v, 4) for k, v in a.belief.items()},
                }
                for name, a in agents.items()
            },
        }
        if signals:
            entry["signals"] = signals
        if trust:
            entry["trust"] = _round_nested(trust)
        if influence:
            entry["influence"] = _round_nested(influence)
        self._question["rounds"].append(entry)

    def add_trust_log(self, record):
        self._trust_log.append(dict(record))

    def finish_question(self, final_answers, scores, per_agent=None):
        self._question["final_answers"] = dict(final_answers)
        self._question["scores"] = _round_flat(scores)
        if per_agent:
            self._question["agents_summary"] = per_agent

    def set_summary(self, summary):
        self.data["summary"] = _round_flat(summary)

    def set_repeats(self, count, right_runs, right_combined,
                    left_runs=None, left_combined=None):
        """Save the result of every repeat, and the average over them.

        `each_run` holds one entry per repeat, so anybody can redo the average
        by hand. `average` holds the mean, the lowest and highest repeat, and
        the spread, which is what should be quoted as the result.
        """
        block = {
            "count": count,
            "each_run": [_round_flat(r) for r in right_runs],
            "average": right_combined,
        }
        if left_runs is not None:
            block["compared_against"] = {
                "each_run": [_round_flat(r) for r in left_runs],
                "average": left_combined,
            }
        self.data["repeats"] = block

    def set_comparison(self, without_trust, with_trust):
        """Used by compare_baseline: the same test run twice, side by side."""
        self.data["comparison"] = {
            "without_trust": _round_flat(without_trust),
            "with_trust": _round_flat(with_trust),
            "better_with_trust": _judge(without_trust, with_trust),
        }

    # ----------------------------------------------------------- checkpoints

    def mark_progress(self, questions_done, trust=None, rows=None, failed=()):
        """Record enough state to carry an interrupted run on from here.

        `trust` is stored UNROUNDED on purpose. Everywhere else in this file a
        trust table is a report and four decimals is plenty, but here it is
        experiment state: `trust_carry_over` means question N+1 begins from
        question N's table, so a resumed run that restored a rounded copy
        would not be the run it claims to be.
        """
        self.data["progress"] = {
            "complete": False,
            "questions_done": questions_done,
            "failed_questions": list(failed),
            "trust": ({a: dict(row) for a, row in trust.items()}
                      if trust is not None else None),
            "rows": list(rows) if rows is not None else None,
        }

    def mark_complete(self, failed=()):
        """The run reached the end.

        Drops the resume scaffolding - the trust table and the per-question
        rows are only there to restart from - and keeps the tally, so a reader
        can tell a finished run from an abandoned one.
        """
        done = self.data.get("progress", {}).get(
            "questions_done", len(self.data["questions"]))
        self.data["progress"] = {
            "complete": True,
            "questions_done": done,
            "failed_questions": list(failed),
        }

    def adopt(self, data):
        """Carry on from a checkpoint written by an earlier attempt.

        Only the finished questions and the progress block are taken.
        `settings` and `agents` stay as this run built them: the caller has
        already refused to resume when the two configs differ, so keeping the
        fresh copy means the file always describes the run that wrote it.
        """
        self.data["questions"] = list(data.get("questions", []))
        self.data["progress"] = dict(data.get("progress", {}))

    # ---------------------------------------------------------------- saving

    def save(self, folder="results", run_name="") -> str:
        Path(folder).mkdir(parents=True, exist_ok=True)
        trust_path = Path(folder) / "trust_log.jsonl"
        with trust_path.open("a", encoding="utf-8") as stream:
            for record in self._trust_log[self._trust_log_written:]:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._trust_log_written = len(self._trust_log)
        name = run_name or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = Path(folder) / f"{name}.json"
        # Write alongside the target and rename over it. Checkpointing happens
        # after every question now, so a crash lands mid-write sooner or later;
        # without this the next attempt would find a truncated file that is
        # neither a finished run nor something it can resume from.
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        # Windows can briefly lock the destination while another process reads
        # it or while the filesystem is settling after a prior checkpoint.
        # Retry a few times instead of losing the already-finished questions.
        last_error = None
        for delay in (0.05, 0.1, 0.2, 0.4, 0.8):
            try:
                tmp.replace(path)
                return str(path)
            except PermissionError as error:
                last_error = error
                time.sleep(delay)
        try:
            tmp.replace(path)
        except PermissionError as error:
            last_error = error
            raise last_error
        return str(path)

    def checkpoint(self, folder="results", run_name="") -> str:
        """Write what is known so far, part-way through a run.

        Does nothing without a stable `run_name`: an unnamed run saves under a
        fresh timestamp every time, so no later attempt could find the file
        again to carry on from it.
        """
        if not run_name:
            return ""
        return self.save(folder=folder, run_name=run_name)


class SweepResults:
    """One reproducible file containing a controlled topology sweep."""

    def __init__(self, cfg):
        self.data = {
            "settings": {
                **{f.name: getattr(cfg, f.name)
                   for f in fields(cfg) if f.name != "questions"},
            },
            "topologies": {},
            "comparison": {},
        }

    def add_topology(self, kind: str, result: Results) -> None:
        self.data["topologies"][kind] = result.data
        self.data["comparison"][kind] = result.data.get("summary", {})

    def save(self, folder="results", run_name="") -> str:
        Path(folder).mkdir(parents=True, exist_ok=True)
        name = run_name or f"topology_sweep_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = Path(folder) / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        return str(path)


def already_done(run_name: str, folder="results") -> str:
    """Has this run FINISHED before? Returns the file path, or "" if not.

    Only works when `run_name` is set. Without a name every run gets its own
    timestamped file and nothing is ever skipped.

    A checkpoint left by an interrupted run does not count as finished: it is
    the thing the next attempt carries on from, so saying "already done" here
    would strand the run one question short for ever. Files written before
    checkpointing existed have no `progress` block at all, and those were only
    ever written on success, so they still count as finished.
    """
    if not run_name:
        return ""
    path = Path(folder) / f"{run_name}.json"
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        # Unreadable means we cannot claim it is finished. Letting the run
        # start again is the safe answer; it will overwrite the bad file.
        return ""
    progress = data.get("progress")
    if isinstance(progress, dict) and not progress.get("complete"):
        return ""
    return str(path)


def load_checkpoint(run_name: str, folder="results"):
    """The saved state of an UNFINISHED run, or None.

    Returns None for a finished run, a missing file, or a file that cannot be
    read. In every one of those cases there is nothing safe to carry on from,
    and starting fresh is the right move.
    """
    if not run_name:
        return None
    path = Path(folder) / f"{run_name}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    progress = data.get("progress")
    if not isinstance(progress, dict) or progress.get("complete"):
        return None
    return data


# --------------------------------------------------------------- small tools

def _round_nested(table):
    return {a: {b: round(v, 4) for b, v in row.items()} for a, row in table.items()}


def _round_flat(values):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in values.items()}


def _judge(without, with_):
    """Did trust help on each of the six headline research measures?"""
    out = {}
    for key, higher_is_better in (("honest_accuracy", True),
                                  ("attack_success_rate", False),
                                  ("normalized_attacker_influence", False),
                                  ("diffusion_reach", False),
                                  ("liar_detection_auprc", True),
                                  ("detection_latency", False),
                                  # Retained for older result readers.
                                  ("trust_separation", True),
                                  ("attacker_influence", False)):
        a, b = without.get(key), with_.get(key)
        if a is None or b is None:
            out[key] = None
        else:
            out[key] = (b > a) if higher_is_better else (b < a)
    return out
