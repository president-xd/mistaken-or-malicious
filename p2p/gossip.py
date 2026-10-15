"""Pure decentralized trust sharing functions."""

from __future__ import annotations


def aggregate_trust(adjacency: dict[str, list[str]], local: dict[str, dict[str, float]],
                    previous: dict[str, dict[str, float]],
                    start_trust: float = 0.5, alpha: float = 0.5,
                    trim: int = 1, liars: set[str] | None = None,
                    attacker_reports: str = "truthful") -> tuple[dict, dict, dict]:
    """Return published reports, aggregate G, and effective trust E."""
    liars = liars or set()
    names = sorted(adjacency)
    reports = {}
    for reporter in names:
        row = {}
        for target in sorted(adjacency.get(reporter, [])):
            if target == reporter:
                continue
            if reporter in liars and attacker_reports == "bad_mouth":
                row[target] = 1.0 if target in liars else 0.0
            else:
                row[target] = float(local.get(reporter, {}).get(target, start_trust))
        reports[reporter] = row

    aggregate = {x: {} for x in names}
    effective = {x: {} for x in names}
    for x in names:
        for target in names:
            if target == x:
                continue
            values = []
            for reporter in names:
                if reporter == target or reporter == x:
                    continue
                if target in reports.get(reporter, {}):
                    weight = max(previous.get(x, {}).get(reporter, start_trust), 0.05)
                    values.append((weight, reports[reporter][target]))
            if target in reports.get(x, {}):
                values.append((1.0, reports[x][target]))
            if not values:
                group = previous.get(x, {}).get(target, start_trust)
            else:
                ordered = sorted(values, key=lambda item: item[1])
                if len(ordered) >= 4 and trim:
                    count = min(trim, (len(ordered) - 1) // 2)
                    ordered = ordered[count:len(ordered) - count]
                total = sum(weight for weight, _ in ordered)
                group = sum(weight * value for weight, value in ordered) / total
            group = min(1.0, max(0.0, group))
            aggregate[x][target] = group
            if target in adjacency.get(x, []):
                value = alpha * local.get(x, {}).get(target, group) + (1 - alpha) * group
            else:
                value = group
            effective[x][target] = min(1.0, max(0.0, value))
    return reports, aggregate, effective


def aggregate_round(local: dict[str, dict[str, float]],
                    hears: dict[str, list[str]],
                    prev_effective: dict[str, dict[str, float]],
                    liars: set[str] | list[str] | None = None,
                    alpha: float = 0.5, trim: int = 1,
                    attacker_reports: str = "truthful") -> tuple[dict, dict, dict]:
    """Compatibility-facing name for one decentralized sharing round."""
    return aggregate_trust(
        hears, local, prev_effective,
        start_trust=0.5, alpha=alpha, trim=trim,
        liars=set(liars or ()), attacker_reports=attacker_reports)