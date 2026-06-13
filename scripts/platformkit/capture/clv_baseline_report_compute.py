"""clv_baseline_report_compute.py — Pure-compute helpers for clv_baseline_report (N-CLV-006).

Provides pair matching and descriptive statistics.  Split from
clv_baseline_report.py to stay within the 300 LOC/file rule.  Logic is
identical — this is a verbatim move, not a rewrite.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

PairKey = Tuple[str, str, str, str, str]  # (sport, event_id, market, book, side)


# ---------------------------------------------------------------------------
# Pair matching
# ---------------------------------------------------------------------------

def build_pairs(rows: List[dict]) -> List[Tuple[dict, dict]]:
    """Match opener rows to closer rows by (sport, event_id, market, book, side).

    Args:
        rows: All ledger rows loaded for the window.

    Returns:
        List of (open_row, close_row) 2-tuples, one per complete pair.
    """
    opens: Dict[PairKey, dict] = {}
    closes: Dict[PairKey, dict] = {}

    for row in rows:
        k = row.get("kind")
        if k not in ("open", "close"):
            continue
        pk: PairKey = (
            str(row.get("sport", "")),
            str(row.get("event_id", "")),
            str(row.get("market", "")),
            str(row.get("book", "")),
            str(row.get("side", "")),
        )
        if k == "open" and pk not in opens:
            opens[pk] = row
        elif k == "close" and pk not in closes:
            closes[pk] = row

    return [(opens[pk], closes[pk]) for pk in opens if pk in closes]


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def percentile(sorted_vals: List[float], p: float) -> float:
    """Linear-interpolation percentile on a pre-sorted list.

    Args:
        sorted_vals: Ascending-sorted list of floats.
        p: Percentile in [0, 100].

    Returns:
        The p-th percentile value.
    """
    n = len(sorted_vals)
    if n == 0:
        return float("nan")
    if n == 1:
        return sorted_vals[0]
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])


def mean(vals: List[float]) -> float:
    """Return mean of *vals*, or NaN if empty."""
    return sum(vals) / len(vals) if vals else float("nan")


def stdev(vals: List[float]) -> float:
    """Return population std-dev of *vals*, or NaN if < 2 items."""
    if len(vals) < 2:
        return float("nan")
    mu = mean(vals)
    return math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
