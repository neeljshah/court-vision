"""execution_quality_math -- pure stats helpers for execution_quality.py.

Split out purely to stay under the 300-LOC/file budget; no independent
purpose beyond backing execution_quality.py's aggregation. Percentile, CLV
distribution, and entry-timing bucket math only -- no I/O beyond a plain
JSONL reader, no ledger-specific dedup/measurability logic (that stays in
clv_scoreboard.py / execution_quality.py, never re-derived here).
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence

# entry-timing buckets, in hours before commence (negative = after commence started)
TIMING_BUCKETS = [
    (24.0, float("inf"), "24h+_before"),
    (6.0, 24.0, "6-24h_before"),
    (1.0, 6.0, "1-6h_before"),
    (0.0, 1.0, "0-1h_before"),
    (float("-inf"), 0.0, "at_or_after_commence"),
]


def percentile(values: Sequence[float], pct: float) -> Optional[float]:
    """Nearest-rank-interpolated percentile; None on empty input. pct in [0, 100]."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 4)
    k = (len(s) - 1) * (pct / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    frac = k - lo
    return round(s[lo] + (s[hi] - s[lo]) * frac, 4)


def clv_distribution(clvs: Sequence[float]) -> Dict[str, Optional[float]]:
    if not clvs:
        return {"n": 0, "mean": None, "median": None, "p10": None, "p90": None}
    return {
        "n": len(clvs),
        "mean": round(sum(clvs) / len(clvs), 4),
        "median": round(statistics.median(clvs), 4),
        "p10": percentile(clvs, 10.0),
        "p90": percentile(clvs, 90.0),
    }


def parse_iso_hours_before(logged_at: Any, commence_time: Any) -> Optional[float]:
    """Hours between logged_at and commence_time (positive = logged before commence)."""
    try:
        a = str(logged_at).replace("Z", "+00:00")
        b = str(commence_time).replace("Z", "+00:00")
        t_logged = datetime.fromisoformat(a)
        t_commence = datetime.fromisoformat(b)
        return (t_commence - t_logged).total_seconds() / 3600.0
    except (ValueError, TypeError):
        return None


def timing_bucket(hours_before: float) -> str:
    for lo, hi, name in TIMING_BUCKETS:
        if lo < hours_before <= hi:
            return name
    return "at_or_after_commence"


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def same_venue_bucket(row: Dict[str, Any]) -> str:
    """'same_venue' | 'cross_venue' | 'no_same_venue_close' for one settled row.

    A row's CLV is only a genuine same-venue measurement when the book that
    supplied the close (close_book_home/away, stamped by grade_paper.grade_one
    when resolved via line_store) matches the book the bet was actually taken
    at (taken_book). See docs/research/PROPOSED_same_venue_close_restriction.md
    for the traced root cause (line_store.get_close mixes books with zero venue
    awareness, so a fanduel-taken bet can silently settle against pinnacle's
    close). Most existing ledger rows predate close_book_* and are honestly
    unknown here, never guessed as either same- or cross-venue.
    """
    taken = str(row.get("taken_book") or "").strip().lower()
    if not taken:
        return "no_same_venue_close"
    side = str(row.get("side") or "").strip().lower()
    close_book = row.get("close_book_home") if side == "home" else (
        row.get("close_book_away") if side == "away" else None)
    if not close_book:
        return "no_same_venue_close"
    return "same_venue" if str(close_book).strip().lower() == taken else "cross_venue"


def same_venue_stats(measurable: Sequence[Dict[str, Any]], *,
                     mean_ci: Callable[[Sequence[float]], Dict[str, Optional[float]]]
                     ) -> Dict[str, Any]:
    """Split already-measurable rows by same_venue_bucket (see
    PROPOSED_same_venue_close_restriction.md): a row's CLV is only a genuine
    same-venue reading when close_book_{home,away} == taken_book. Cross-venue
    rows (bet at fanduel, settled vs pinnacle's close, etc.) and rows with no
    close-book provenance at all are NEVER silently folded into the headline
    mean -- each bucket is reported on its own, honestly, even when that means
    same_venue has 0 rows (close_book_* is a new field; no pre-existing ledger
    row was ever stamped with it). *mean_ci* is injected (clv_scoreboard's
    _mean_ci) so this module stays free of that ledger-specific dependency.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "same_venue": [], "cross_venue": [], "no_same_venue_close": []}
    for r in measurable:
        buckets[same_venue_bucket(r)].append(r)
    out: Dict[str, Any] = {}
    for name, rows in buckets.items():
        clvs = [float(r["clv_pct"]) for r in rows]
        ci = mean_ci(clvs)
        out[name] = {"n": len(rows), "clv_distribution_pct": clv_distribution(clvs),
                     "clv_ci95": [ci["lo95"], ci["hi95"]], "clv_significant": ci["significant"]}
    return out


def entry_timing_from_graded(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Entry-timing distribution from the ONE source with both logged_at and
    commence_time (paper_predictions_graded.jsonl). Bucket counts + honest note.
    """
    buckets: Dict[str, int] = {}
    n_parsed = 0
    for r in rows:
        hrs = parse_iso_hours_before(r.get("logged_at"), r.get("commence_time"))
        if hrs is None:
            continue
        n_parsed += 1
        b = timing_bucket(hrs)
        buckets[b] = buckets.get(b, 0) + 1
    return {
        "n_rows": len(rows),
        "n_timing_parsed": n_parsed,
        "buckets": buckets,
        "source": "paper_predictions_graded.jsonl (only ledger carrying both "
                  "logged_at and commence_time)",
    }


__all__ = [
    "percentile", "clv_distribution", "parse_iso_hours_before", "timing_bucket",
    "load_jsonl", "entry_timing_from_graded", "same_venue_bucket", "same_venue_stats",
]
