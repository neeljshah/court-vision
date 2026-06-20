"""scripts.platformkit.improve.improvement_trend -- delta series over the per-market
recalibration ledger to answer: is the self-improve loop actually sharpening?

Reads the SI-01 PerMarketLedger (improve_ledger_segmented.jsonl) and computes an
ordered delta series per market so callers can answer:

  * Is each successive cycle's Brier LOWER than the previous? (monotone_improving)
  * Did any cycle regress beyond a tolerance? (regression_flag)
  * Are there fewer than 2 data cycles?  -> status INSUFFICIENT_DATA

CONTRACT:
  - Rows with status INSUFFICIENT_DATA are EXCLUDED from the delta series (too few
    settled rows to compute a meaningful Brier; including them would fabricate noise).
  - A regression flag is set when at least one consecutive-pair Brier delta > TOL
    (i.e. Brier WENT UP, meaning the loop got WORSE on that step).
  - monotone_improving -> True only when every consecutive pair is non-regressing.
  - The output dict never contains a key matching /(\$|roi|pnl|profit)/.
  - <= 300 LOC; stdlib + numpy; ASCII only.

Usage:
  from scripts.platformkit.improve.improvement_trend import compute_trend

  result = compute_trend("nba:moneyline", ledger_path=None)
  # result["status"] in {"ok", "INSUFFICIENT_DATA"}
  # result["monotone_improving"] -> bool (present when status=="ok")
  # result["regression_flag"]   -> bool (present when status=="ok")
  # result["deltas"]            -> list of float (brier[i+1] - brier[i])
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_CYCLES: int = 2
"""Minimum data-bearing cycles (non-INSUFFICIENT_DATA rows) to compute a trend."""

REGRESSION_TOL: float = 0.001
"""A single-step Brier increase beyond this tolerance sets regression_flag."""

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_HERE = Path(__file__).resolve().parent
_DEFAULT_LEDGER = _HERE.parents[2] / "data" / "frontend" / "improve_ledger_segmented.jsonl"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _assert_no_banned_keys(obj: Any) -> None:
    """Raise ValueError if any key in obj (recursively) matches a banned pattern."""
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.search(k):
            raise ValueError(
                "Banned key '%s' violates no-dollar-field contract." % k
            )


def _all_keys(obj: Any) -> List[str]:
    keys: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.append(k)
            keys.extend(_all_keys(v))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            keys.extend(_all_keys(item))
    return keys


def _extract_brier(row: Dict[str, Any]) -> Optional[float]:
    """Return raw_brier from a ledger row's readout, or None if absent."""
    readout = row.get("readout")
    if not isinstance(readout, dict):
        return None
    v = readout.get("raw_brier")
    if v is None:
        return None
    try:
        f = float(v)
        if f != f:  # NaN guard
            return None
        return f
    except (TypeError, ValueError):
        return None


def _data_rows(market_rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter to rows with status != INSUFFICIENT_DATA (i.e. rows with a Brier readout)."""
    return [r for r in market_rows if r.get("status") != "INSUFFICIENT_DATA"]


# ---------------------------------------------------------------------------
# Core trend computation
# ---------------------------------------------------------------------------


def compute_trend(
    market: str,
    ledger_path: Optional[Path] = None,
    min_cycles: int = MIN_CYCLES,
    regression_tol: float = REGRESSION_TOL,
) -> Dict[str, Any]:
    """Compute the improvement delta series for a single market.

    Parameters
    ----------
    market:
        Ledger market key, e.g. "nba:moneyline".
    ledger_path:
        Path to improve_ledger_segmented.jsonl; defaults to the standard location.
    min_cycles:
        Minimum data-bearing cycles required; below this -> INSUFFICIENT_DATA.
    regression_tol:
        Tolerance for declaring a single-step regression (Brier increase).

    Returns
    -------
    dict with keys:
        status          "ok" or "INSUFFICIENT_DATA"
        market          the market key
        n_data_cycles   number of usable (non-INSUFFICIENT_DATA) rows
        n_excluded      number of INSUFFICIENT_DATA rows excluded
        note            calibration disclaimer
        # only when status == "ok":
        deltas          list[float]: brier[i+1] - brier[i]  (negative = improved)
        monotone_improving  bool: True iff every delta <= regression_tol
        regression_flag     bool: True iff any delta > regression_tol
        briers          list[float]: raw_brier per data cycle (chronological)
        cycle_statuses  list[str]: ledger status per data cycle
    """
    path = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    all_rows = _read_jsonl(path)
    mkt = market.lower()
    market_rows = [r for r in all_rows if str(r.get("market", "")).lower() == mkt]

    n_excluded = sum(1 for r in market_rows if r.get("status") == "INSUFFICIENT_DATA")
    data = _data_rows(market_rows)
    n_data = len(data)

    base: Dict[str, Any] = {
        "status": "INSUFFICIENT_DATA",
        "market": mkt,
        "n_data_cycles": n_data,
        "n_excluded": n_excluded,
        "note": (
            "calibration != edge: better-calibrated probabilities do NOT imply "
            "beating the market close or a positive expected value"
        ),
    }

    if n_data < min_cycles:
        base["reason"] = (
            "only %d data-bearing cycle(s) for market '%s'; need >= %d to compute "
            "a trend. INSUFFICIENT_DATA rows are excluded." % (n_data, mkt, min_cycles)
        )
        _assert_no_banned_keys(base)
        return base

    # Extract briers in chronological order (JSONL is append-only, so order is given).
    briers: List[float] = []
    cycle_statuses: List[str] = []
    for row in data:
        b = _extract_brier(row)
        if b is None:
            # Row has a readout but no numeric raw_brier -- skip it honestly.
            n_excluded += 1
            continue
        briers.append(b)
        cycle_statuses.append(str(row.get("status", "")))

    if len(briers) < min_cycles:
        base["n_data_cycles"] = len(briers)
        base["n_excluded"] = n_excluded
        base["reason"] = (
            "only %d cycles have a numeric raw_brier; need >= %d." % (len(briers), min_cycles)
        )
        _assert_no_banned_keys(base)
        return base

    # Compute consecutive deltas: positive = regression, negative = improvement.
    deltas = [briers[i + 1] - briers[i] for i in range(len(briers) - 1)]
    regression_flag = any(d > regression_tol for d in deltas)
    monotone_improving = not regression_flag

    result: Dict[str, Any] = {
        **base,
        "status": "ok",
        "n_data_cycles": len(briers),
        "n_excluded": n_excluded,
        "briers": briers,
        "deltas": deltas,
        "monotone_improving": monotone_improving,
        "regression_flag": regression_flag,
        "cycle_statuses": cycle_statuses,
    }
    _assert_no_banned_keys(result)
    return result


# ---------------------------------------------------------------------------
# Multi-market helper
# ---------------------------------------------------------------------------


def compute_trends(
    ledger_path: Optional[Path] = None,
    min_cycles: int = MIN_CYCLES,
    regression_tol: float = REGRESSION_TOL,
) -> Dict[str, Dict[str, Any]]:
    """Compute the improvement trend for EVERY market found in the ledger.

    Returns a dict keyed by market with the same per-market result dict as
    compute_trend().  Markets with < min_cycles data rows are included with
    status INSUFFICIENT_DATA -- never silently dropped.
    """
    path = Path(ledger_path) if ledger_path else _DEFAULT_LEDGER
    rows = _read_jsonl(path)
    markets = sorted({str(r.get("market", "")).lower() for r in rows if r.get("market")})
    return {
        mkt: compute_trend(mkt, ledger_path=path,
                           min_cycles=min_cycles, regression_tol=regression_tol)
        for mkt in markets
    }


__all__ = [
    "compute_trend",
    "compute_trends",
    "MIN_CYCLES",
    "REGRESSION_TOL",
]
