"""Save a run to one JSON file.

Turned on with `--result json` on the command line. Everything the terminal
shows also goes in here, plus the performance numbers, so a run can be checked
or re-read long after it finished.

One file per run, written to the `results` folder.
"""

from __future__ import annotations

import json
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

    # ---------------------------------------------------------------- saving

    def save(self, folder="results", run_name="") -> str:
        Path(folder).mkdir(parents=True, exist_ok=True)
        name = run_name or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        path = Path(folder) / f"{name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        return str(path)


def already_done(run_name: str, folder="results") -> str:
    """Has this run finished before? Returns the file path, or "" if not.

    Only works when `run_name` is set. Without a name every run gets its own
    timestamped file and nothing is ever skipped.
    """
    if not run_name:
        return ""
    path = Path(folder) / f"{run_name}.json"
    return str(path) if path.exists() else ""


# --------------------------------------------------------------- small tools

def _round_nested(table):
    return {a: {b: round(v, 4) for b, v in row.items()} for a, row in table.items()}


def _round_flat(values):
    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in values.items()}


def _judge(without, with_):
    """Did trust help? Higher is better for two measures, lower for two others."""
    out = {}
    for key, higher_is_better in (("honest_accuracy", True),
                                  ("attack_success_rate", False),
                                  ("trust_separation", True),
                                  ("attacker_influence", False)):
        a, b = without.get(key), with_.get(key)
        if a is None or b is None:
            out[key] = None
        else:
            out[key] = (b > a) if higher_is_better else (b < a)
    return out
