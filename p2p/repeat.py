"""Run the same experiment several times and report the average.

WHY THIS FILE EXISTS.

One run of one setup is not a result. With 3 honest agents, one agent changing
its mind moves a score by 33 percentage points. So a run that scores 25% and a
run that scores 33% may be the SAME setup behaving the same way, and the gap is
only luck. Reporting a single run as if it were a finding is the most common
mistake in this kind of work.

The fix is simple: run the same setup several times with a different seed each
time, then report the average and how far apart the runs were.

The maths here is only two things:

  mean    add the values up, divide by how many there are
  spread  the usual sample standard deviation, which is
          square root of ( sum of (value - mean) squared, divided by n - 1 )

We use n - 1 and not n because we are estimating the spread of all possible
runs from the few runs we did. That is the standard choice and it makes the
estimate honest rather than slightly too small.
"""

from __future__ import annotations

import math

from .metrics import AVERAGED


# Two-sided 95% Student-t critical values. A t interval is more honest than a
# normal interval for the small repeat counts used by model experiments.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}


def mean(values: list[float]) -> float | None:
    """The plain average. None when there is nothing to average."""
    return sum(values) / len(values) if values else None


def spread(values: list[float]) -> float | None:
    """Sample standard deviation: how far the runs sat from their average.

    Needs at least 2 runs. A spread of 0 means every run gave the same number.
    A big spread means the runs disagreed, so the average cannot be trusted
    on its own.
    """
    if len(values) < 2:
        return None
    average = sum(values) / len(values)
    total = sum((v - average) ** 2 for v in values)
    return math.sqrt(total / (len(values) - 1))


def confidence_interval_95(values: list[float]) -> tuple[float, float] | None:
    """Student-t 95% confidence interval for a repeated-run mean."""
    deviation = spread(values)
    if deviation is None:
        return None
    center = mean(values)
    df = len(values) - 1
    critical = _T95.get(df, 1.96 if df > 120 else 2.0)
    margin = critical * deviation / math.sqrt(len(values))
    return center - margin, center + margin


def combine(runs: list[dict]) -> dict:
    """Turn several run summaries into one summary of average and spread.

    `runs` is a list of the dictionaries `metrics.average_runs` gives back,
    one per repeat. For every measure we report:

      mean     the average over the repeats
      lowest   the worst repeat
      highest  the best repeat
      spread   how far apart the repeats were
      runs     how many repeats actually had a value for this measure
    """
    out = {}
    for key in AVERAGED:
        values = [r[key] for r in runs if r.get(key) is not None]
        if not values:
            out[key] = None
            continue
        out[key] = {
            "mean": round(mean(values), 4),
            "lowest": round(min(values), 4),
            "highest": round(max(values), 4),
            "spread": (round(spread(values), 4)
                       if spread(values) is not None else None),
            "ci95_low": (round(confidence_interval_95(values)[0], 4)
                         if confidence_interval_95(values) is not None else None),
            "ci95_high": (round(confidence_interval_95(values)[1], 4)
                          if confidence_interval_95(values) is not None else None),
            "runs": len(values),
        }
    return out


def means_only(combined: dict) -> dict:
    """Just the averages, in the plain shape the rest of the code expects.

    The comparison table and the JSON summary both want one number per
    measure, not a small dictionary. This gives them that.
    """
    return {key: (value["mean"] if isinstance(value, dict) else None)
            for key, value in combined.items()}


def overlaps(left: dict | None, right: dict | None) -> bool:
    """Do the two sets of repeats overlap, so the difference may be luck?

    We compare the lowest-to-highest range of each side. If the ranges touch
    at all, then at least one run of the worse setup did as well as at least
    one run of the better setup, so we cannot claim a real difference from
    these repeats alone. We report this rather than hide it.
    """
    if not isinstance(left, dict) or not isinstance(right, dict):
        return True
    return (left["lowest"] <= right["highest"]
            and right["lowest"] <= left["highest"])
