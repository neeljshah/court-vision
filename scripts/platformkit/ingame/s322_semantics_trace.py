"""S322 cached-state semantics tracing; no simulator rollout is performed."""
from __future__ import annotations

import csv
import argparse
from pathlib import Path
from typing import Iterable, Mapping, Sequence


TRACE_FIELDS = (
    "state_key", "game_id", "elapsed_s", "home_polarity", "score_semantics",
    "clock", "overtime", "conservation", "status", "error_field",
)

# Sealed criteria order (prereg): earliest, latest, tied, |margin|>=15, overtime, both venues.
CRITERIA = ("earliest", "latest", "tied", "margin15", "overtime", "venue")


def _value(row: Mapping[str, object], *names: str) -> object | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _number(row: Mapping[str, object], *names: str) -> float | None:
    value = _value(row, *names)
    return float(value) if value is not None else None


def _flag(ok: bool, field: str, errors: list[str]) -> str:
    if not ok:
        errors.append(field)
    return "PASS" if ok else "FAIL"


def trace_state(row: Mapping[str, object]) -> dict[str, object]:
    """Trace one cached adapter state against declared home-win semantics."""
    errors: list[str] = []
    home = _number(row, "home_score", "score_home")
    away = _number(row, "away_score", "score_away")
    final_home = _number(row, "final_home_score")
    final_away = _number(row, "final_away_score")
    remaining = _number(row, "seconds_remaining", "clock_remaining_s")
    elapsed = _number(row, "elapsed_s", "elapsed")
    period = _number(row, "period", "quarter")
    home_probability = _number(row, "p_home", "p_simulator", "home_win_probability")
    away_probability = _number(row, "p_away", "away_win_probability")
    expected_home = _value(row, "output_side", "probability_side") in (None, "home", "HOME")
    polarity = _flag(expected_home and home_probability is not None, "home_polarity", errors)
    scores_known = home is not None and away is not None
    not_final = (final_home is None or home != final_home) and (final_away is None or away != final_away)
    score_semantics = _flag(scores_known and not_final, "score_semantics", errors)
    clock = _flag(remaining is not None and remaining >= 0 and elapsed is not None and elapsed >= 0,
                  "clock", errors)
    overtime_expected = bool(period is not None and period > 4)
    overtime_value = _value(row, "is_overtime", "overtime")
    overtime = _flag(overtime_value is not None and bool(int(overtime_value)) == overtime_expected,
                     "overtime", errors)
    probability_sum = (None if home_probability is None else
                       (1.0 if away_probability is None else home_probability + away_probability))
    conservation = _flag(probability_sum is not None and abs(probability_sum - 1.0) <= 1e-12,
                         "conservation", errors)
    return {
        "state_key": str(_value(row, "state_key", "timestamp") or ""),
        "game_id": str(_value(row, "game_id", "game") or ""),
        "elapsed_s": int(elapsed or 0), "home_polarity": polarity,
        "score_semantics": score_semantics, "clock": clock, "overtime": overtime,
        "conservation": conservation, "status": "PASS" if not errors else "FAIL",
        "error_field": ";".join(errors),
    }


def _sort_key(row: Mapping[str, object]) -> tuple[str, str, int]:
    return (str(_value(row, "timestamp_utc", "timestamp", "ts") or ""),
            str(_value(row, "game_id", "game") or ""),
            int(_number(row, "elapsed_s", "elapsed") or 0))


def _key(row: Mapping[str, object]) -> str:
    return str(_value(row, "state_key", "timestamp"))


def _stride_pick(pool: Sequence[Mapping[str, object]], k: int) -> list[Mapping[str, object]]:
    """Evenly-spaced deterministic picks across ``pool`` -- never a contiguous head."""
    if k <= 0 or not pool:
        return []
    if k >= len(pool):
        return list(pool)
    if k == 1:
        return [pool[len(pool) // 2]]
    return [pool[round(i * (len(pool) - 1) / (k - 1))] for i in range(k)]


def _field_source(sources: Sequence[tuple[str, list[Mapping[str, object]]]],
                  names: tuple[str, ...]) -> tuple[str, list[Mapping[str, object]]] | None:
    """First source (primary, then fallbacks in order) whose schema exposes any of ``names``."""
    for label, cand in sources:
        if cand and any(name in cand[0] for name in names):
            return label, cand
    return None


def _bucket_pool(kind: str, ordered: list[Mapping[str, object]],
                 sources: Sequence[tuple[str, list[Mapping[str, object]]]],
                 ) -> tuple[str, list[Mapping[str, object]]]:
    """Return (provenance, matching rows) for one sealed boundary criterion."""
    if kind == "earliest":
        return "primary:timestamp", [ordered[0]]
    if kind == "latest":
        return "primary:timestamp", [ordered[-1]]
    if kind in ("tied", "margin15"):
        found = _field_source(sources, ("home_score", "score_home"))
        if found is None:
            return "NO_FIELD_IN_ANY_SOURCE(home_score/away_score)", []
        label, cand = found
        matches = []
        for row in cand:
            home, away = _number(row, "home_score", "score_home"), _number(row, "away_score", "score_away")
            if home is None or away is None:
                continue
            if kind == "tied" and home == away:
                matches.append(row)
            if kind == "margin15" and abs(home - away) >= 15:
                matches.append(row)
        return f"{label}:home_score/away_score", matches
    if kind == "overtime":
        found = _field_source(sources, ("is_overtime", "overtime", "period", "quarter"))
        if found is None:
            return "NO_FIELD_IN_ANY_SOURCE(is_overtime/period)", []
        label, cand = found
        matches = [row for row in cand
                  if bool(int(_value(row, "is_overtime", "overtime") or 0))
                  or (_number(row, "period", "quarter") or 0) > 4]
        return f"{label}:is_overtime/period", matches
    if kind == "venue":
        found = _field_source(sources, ("venue", "home_venue"))
        if found is None:
            return "NO_FIELD_IN_ANY_SOURCE(venue)", []
        label, cand = found
        by_venue: dict[str, Mapping[str, object]] = {}
        for row in cand:
            by_venue.setdefault(str(_value(row, "venue", "home_venue")), row)
        return f"{label}:venue", list(by_venue.values())
    raise ValueError(kind)


def select_boundary_states(
    rows: Iterable[Mapping[str, object]], n: int = 30,
    extra_sources: Sequence[tuple[str, list[Mapping[str, object]]]] = (),
) -> tuple[list[dict[str, object]], list[int], dict[str, tuple[str, int]]]:
    """True round-robin select ``n`` states across the sealed criteria buckets (earliest,
    latest, tied, |margin|>=15, overtime, both venues): one state per non-empty bucket per
    pass, so a dense bucket can never exhaust the slot budget before a later bucket is ever
    drawn from. Remaining slots are stride-filled across the full ordered index so no bucket
    -- including the fill -- is a contiguous head. Returns (states, ordered-index ranks,
    {bucket: (field/source provenance, picked)})."""
    ordered = sorted((dict(row) for row in rows), key=_sort_key)
    if len(ordered) < n:
        raise ValueError("S322 requires at least 30 cached states")
    sources: list[tuple[str, list[Mapping[str, object]]]] = [("primary", ordered), *extra_sources]

    seen: set[str] = set()
    unique: list[dict[str, object]] = []
    bucket_pools = {kind: _bucket_pool(kind, ordered, sources) for kind in CRITERIA}
    report: dict[str, tuple[str, int]] = {kind: (bucket_pools[kind][0], 0) for kind in CRITERIA}
    exhausted = False
    while len(unique) < n and not exhausted:
        exhausted = True
        for kind in CRITERIA:
            if len(unique) >= n:
                break
            provenance, pool = bucket_pools[kind]
            available = [row for row in pool if _key(row) not in seen]
            if not available:
                continue
            exhausted = False
            pick = available[len(available) // 2]
            seen.add(_key(pick)); unique.append(dict(pick))
            report[kind] = (provenance, report[kind][1] + 1)
    remaining = [row for row in ordered if _key(row) not in seen]
    fill = _stride_pick(remaining, n - len(unique))
    for row in fill:
        seen.add(_key(row)); unique.append(dict(row))
    report["spread_fill"] = ("primary:stride-remainder", len(fill))
    if len(unique) != n:
        raise AssertionError("deterministic S322 selection did not produce n states")
    index_of = {_key(row): i for i, row in enumerate(ordered)}
    ranks = [index_of[_key(row)] for row in unique]
    return unique, ranks, report


def write_trace(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    """Write the sealed 30-state trace with LF endings."""
    traced = [trace_state(row) for row in rows]
    for row in traced:
        row["elapsed_s"] = f"{int(row['elapsed_s']):06d}"
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(traced)
    return len(traced)


def _load_csv(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    """Write the trace only after the separately sealed finisher reruns premise."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--series", type=Path, required=True)
    parser.add_argument("--fallback", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    primary = _load_csv(args.series)
    extra = [(str(path), _load_csv(path)) for path in args.fallback]
    states, ranks, report = select_boundary_states(primary, extra_sources=extra)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    count = write_trace(args.out, states)
    print("TRACE STATES %06d" % count)
    print("SELECTED RANKS " + ",".join(str(r) for r in sorted(ranks)))
    print("MAX RANK %d OF %d" % (max(ranks), len(primary)))
    for kind in (*CRITERIA, "spread_fill"):
        provenance, picked = report[kind]
        print("BUCKET %s picked=%d source=%s" % (kind, picked, provenance))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
