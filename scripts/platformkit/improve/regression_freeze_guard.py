"""scripts.platformkit.improve.regression_freeze_guard -- advisory regression freeze.

ADVISORY ONLY: reads the per-market improvement trend (via improvement_trend.compute_trend)
and returns a per-market freeze recommendation.  It NEVER mutates ratchet_state, never edits
the daemon, never flips a flag, and never writes any ledger.

CONTRACT
--------
  * freeze=True is returned only when a market shows SUSTAINED regression: at least K
    consecutive Brier increases each exceeding REGRESSION_TOL (mirroring frozen_families
    semantics from prioritizer.py -- if the improvement loop itself looks like it is
    consistently making things WORSE, flag it for a human to review before the next cycle).
  * Default freeze=False.  Unknown markets, INSUFFICIENT_DATA markets, and one-off
    regressions that are followed by a recovery all return freeze=False.
  * Never auto-unfreezes: once freeze=True the caller decides what to do; this module only
    re-evaluates on the CURRENT data each call (stateless).
  * The returned dict NEVER contains a key matching /(dollar|roi|pnl|profit)/. ASCII only.
  * Never raises: malformed/empty input returns freeze=False with an honest reason.

TYPICAL CALL
------------
  from scripts.platformkit.improve.regression_freeze_guard import check_freeze, check_all

  rec = check_freeze("nba:moneyline")
  # rec["freeze"] -> bool
  # rec["reason"] -> str
  # rec["status"] -> "ok" | "INSUFFICIENT_DATA"
  # rec["consecutive_regressions"] -> int (only when status=="ok")

  all_recs = check_all()  # one recommendation per market in the ledger

PARAMETERS
----------
  MIN_K : int = 3
      Minimum consecutive Brier-increasing steps (each > REGRESSION_TOL) before
      freeze=True.  Matches the spirit of prioritizer.frozen_families: a family is
      not frozen on a single null_ship -- there must be a pattern.

The REGRESSION_TOL constant is imported from improvement_trend (never duplicated here).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.improve.improvement_trend import (
    REGRESSION_TOL,
    compute_trend,
    compute_trends,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_K: int = 3
"""Minimum CONSECUTIVE Brier-increasing steps (each > REGRESSION_TOL) -> freeze=True."""

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

_CALIBRATION_NOTE = (
    "calibration != edge: a regression in Brier does NOT imply a profitable "
    "market-edge, nor does improvement; this is a calibration-only guard"
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_no_banned_keys(obj: Any) -> None:
    """Raise ValueError if any key (recursively) matches a banned pattern."""
    for k in _all_keys(obj):
        if _BANNED_KEY_RE.search(k):
            raise ValueError("Banned key '%s' in output (no $/roi/pnl/profit allowed)." % k)


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


def _max_consecutive_regressions(deltas: List[float], tol: float) -> int:
    """Return the length of the longest run of consecutive Brier increases > tol.

    Each delta is brier[i+1] - brier[i].  A positive delta (Brier WENT UP = WORSE)
    beyond tol counts as a regression step.  We want the longest unbroken streak.
    """
    max_run = 0
    current_run = 0
    for d in deltas:
        if d > tol:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    return max_run


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_freeze(
    market: str,
    ledger_path: Optional[Path] = None,
    min_k: int = MIN_K,
    regression_tol: float = REGRESSION_TOL,
) -> Dict[str, Any]:
    """Return an advisory freeze recommendation for a single market.

    Parameters
    ----------
    market:
        Ledger market key, e.g. "nba:moneyline".
    ledger_path:
        Override for the ledger path (forwarded to compute_trend).
    min_k:
        Number of CONSECUTIVE regression steps required to recommend freeze=True.
    regression_tol:
        Per-step Brier-increase tolerance threshold (forwarded to compute_trend).

    Returns
    -------
    dict with keys:
        market               str -- lower-cased market key
        freeze               bool -- True iff sustained regression detected
        status               "ok" | "INSUFFICIENT_DATA"
        reason               str -- human-readable honest explanation
        note                 str -- calibration disclaimer
        # only when status=="ok":
        consecutive_regressions  int -- longest run of consecutive regression steps
        n_data_cycles            int -- number of Brier-bearing cycles
        min_k                    int -- the K threshold in effect
    """
    try:
        trend = compute_trend(
            market,
            ledger_path=ledger_path,
            regression_tol=regression_tol,
        )
    except Exception as exc:  # purity: never raise
        result: Dict[str, Any] = {
            "market": str(market).lower(),
            "freeze": False,
            "status": "INSUFFICIENT_DATA",
            "reason": (
                "compute_trend raised %s: %s -- defaulting to freeze=False (do-no-harm)"
                % (type(exc).__name__, exc)
            ),
            "note": _CALIBRATION_NOTE,
        }
        _assert_no_banned_keys(result)
        return result

    mkt = trend.get("market", str(market).lower())

    # ---- INSUFFICIENT_DATA path --------------------------------------------
    if trend.get("status") != "ok":
        result = {
            "market": mkt,
            "freeze": False,
            "status": "INSUFFICIENT_DATA",
            "reason": (
                "INSUFFICIENT_DATA: %s -- need >= 2 data-bearing Brier cycles to "
                "evaluate a regression pattern; defaulting freeze=False"
                % trend.get("reason", "too few cycles")
            ),
            "note": _CALIBRATION_NOTE,
        }
        _assert_no_banned_keys(result)
        return result

    # ---- ok path -----------------------------------------------------------
    deltas: List[float] = trend.get("deltas", [])
    n_data: int = trend.get("n_data_cycles", 0)

    # Guard: need at least K+1 briers to form K consecutive deltas.
    # deltas has len == n_briers - 1; so K consecutive deltas needs len(deltas) >= K.
    if len(deltas) < min_k:
        result = {
            "market": mkt,
            "freeze": False,
            "status": "INSUFFICIENT_DATA",
            "reason": (
                "only %d delta(s) available for market '%s'; need >= %d consecutive "
                "to evaluate sustained regression; defaulting freeze=False"
                % (len(deltas), mkt, min_k)
            ),
            "n_data_cycles": n_data,
            "min_k": min_k,
            "consecutive_regressions": 0,
            "note": _CALIBRATION_NOTE,
        }
        _assert_no_banned_keys(result)
        return result

    consecutive = _max_consecutive_regressions(deltas, regression_tol)
    freeze = consecutive >= min_k

    if freeze:
        reason = (
            "ADVISORY FREEZE: market '%s' shows %d consecutive Brier-increasing "
            "steps (each > %.4f tol), meeting the K=%d sustained-regression threshold. "
            "A human should review before the next recalibration cycle ships for this "
            "market. This is advisory only -- the daemon is NOT mutated."
            % (mkt, consecutive, regression_tol, min_k)
        )
    elif trend.get("regression_flag"):
        reason = (
            "one-off or non-consecutive regression detected (max consecutive run = %d, "
            "threshold K=%d not reached); freeze=False"
            % (consecutive, min_k)
        )
    else:
        reason = (
            "no regression beyond tol=%.4f detected across %d cycle(s); freeze=False"
            % (regression_tol, n_data)
        )

    result = {
        "market": mkt,
        "freeze": freeze,
        "status": "ok",
        "reason": reason,
        "n_data_cycles": n_data,
        "min_k": min_k,
        "consecutive_regressions": consecutive,
        "note": _CALIBRATION_NOTE,
    }
    _assert_no_banned_keys(result)
    return result


def check_all(
    ledger_path: Optional[Path] = None,
    min_k: int = MIN_K,
    regression_tol: float = REGRESSION_TOL,
) -> Dict[str, Dict[str, Any]]:
    """Return advisory freeze recommendations for ALL markets in the ledger.

    Returns a dict keyed by market with the same per-market result dict as
    check_freeze().  Markets with INSUFFICIENT_DATA are included with freeze=False --
    never silently dropped.  Never raises.
    """
    try:
        all_trends = compute_trends(
            ledger_path=ledger_path,
            regression_tol=regression_tol,
        )
    except Exception:  # purity: never raise
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for mkt in all_trends:
        out[mkt] = check_freeze(
            mkt,
            ledger_path=ledger_path,
            min_k=min_k,
            regression_tol=regression_tol,
        )
    return out


__all__ = [
    "check_freeze",
    "check_all",
    "MIN_K",
    "REGRESSION_TOL",
]
