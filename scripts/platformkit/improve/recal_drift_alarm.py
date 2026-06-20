"""scripts.platformkit.improve.recal_drift_alarm -- recalibration drift alarm.

ADVISORY ONLY: reads the per-market improvement ledger (via
improvement_trend.compute_trend) and emits a per-market alarm dict that
signals whether the self-improve ratchet is drifting WORSE on Brier/ECE
across recent cycles.

This is a DO-NO-HARM tripwire. It NEVER:
  - flips any feature flag
  - auto-promotes a market to SHIP
  - mutates the ledger or ratchet state
  - raises (malformed / empty input -> INSUFFICIENT_DATA with honest reason)

CONTRACT
--------
  * regression=True emitted when Brier is monotonically worsening over the
    LAST `window` data cycles AND at least one step exceeds REGRESSION_TOL.
    "Monotonically worsening" means EVERY delta in the window is > 0 (each
    step made calibration WORSE). A single bad step that recovers does NOT
    set regression=True (use regression_freeze_guard for sustained patterns).
  * monotone_improving=True only when EVERY delta in the full series is <=0
    AND n_data_cycles >= MIN_CYCLES (mirrors improvement_trend semantics).
  * < MIN_CYCLES data-bearing cycles -> status="INSUFFICIENT_DATA",
    regression=False, monotone_improving=False.
  * No key matching /(\\$|roi|pnl|profit)/ in any output (no dollar fields).
  * calibration != edge: alarm is purely about calibration accuracy, NOT
    market-beating ability or expected value.

TYPICAL CALL
------------
  from scripts.platformkit.improve.recal_drift_alarm import check_alarm, check_all_alarms

  alarm = check_alarm("nba:moneyline")
  # alarm["status"]             -> "ok" | "INSUFFICIENT_DATA"
  # alarm["regression"]         -> bool  (True => recent cycles monotone-worsening)
  # alarm["monotone_improving"] -> bool  (True => ALL cycles monotone-improving)
  # alarm["n_data_cycles"]      -> int
  # alarm["window"]             -> int   (cycles checked for drift)
  # alarm["note"]               -> str   (calibration disclaimer)

  all_alarms = check_all_alarms()  # keyed by market

PARAMETERS
----------
  DEFAULT_WINDOW : int = 3
      Number of recent data cycles examined for monotone-worsening drift.
      All consecutive deltas in this window must be > 0 (AND at least one
      must exceed REGRESSION_TOL) to set regression=True.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.platformkit.improve.improvement_trend import (
    MIN_CYCLES,
    REGRESSION_TOL,
    compute_trend,
    compute_trends,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_WINDOW: int = 3
"""Number of recent data cycles examined for monotone-worsening drift."""

_CALIBRATION_NOTE = (
    "calibration != edge: a Brier regression does NOT imply a profitable "
    "market, nor does improvement; this alarm is calibration-only and advisory"
)

_BANNED_KEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _assert_no_banned_keys(obj: Any) -> None:
    """Raise ValueError if any key (recursively) matches a banned pattern."""
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


def _is_monotone_worsening(deltas: List[float], tol: float) -> bool:
    """Return True iff all deltas are > 0 AND at least one exceeds tol.

    A window where every step increased Brier (each delta > 0) AND at least
    one step exceeded the noise floor (tol) is a monotone-worsening run.
    An empty window returns False (not enough data).
    """
    if not deltas:
        return False
    all_positive = all(d > 0.0 for d in deltas)
    any_above_tol = any(d > tol for d in deltas)
    return all_positive and any_above_tol


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_alarm(
    market: str,
    ledger_path: Optional[Path] = None,
    window: int = DEFAULT_WINDOW,
    regression_tol: float = REGRESSION_TOL,
    min_cycles: int = MIN_CYCLES,
) -> Dict[str, Any]:
    """Emit a recal-drift alarm for a single market.

    Parameters
    ----------
    market:
        Ledger market key, e.g. "nba:moneyline".
    ledger_path:
        Override ledger path (forwarded to compute_trend).
    window:
        Number of recent data cycles to examine for monotone-worsening drift.
        Clamped to the available number of deltas (no IndexError).
    regression_tol:
        Per-step Brier-increase tolerance (forwarded to compute_trend).
    min_cycles:
        Minimum data-bearing cycles; below this -> INSUFFICIENT_DATA.

    Returns
    -------
    dict with keys:
        status               "ok" | "INSUFFICIENT_DATA"
        market               str (lower-cased)
        regression           bool -- True iff recent cycles monotone-worsening
        monotone_improving   bool -- True iff ALL cycles non-regressing
        n_data_cycles        int  -- number of usable Brier-bearing cycles
        window               int  -- number of recent cycles examined
        window_deltas        list[float] -- deltas in the examined window
        note                 str  -- calibration disclaimer
        # only when status == "INSUFFICIENT_DATA":
        reason               str  -- human-readable explanation
    """
    try:
        trend = compute_trend(
            market,
            ledger_path=ledger_path,
            min_cycles=min_cycles,
            regression_tol=regression_tol,
        )
    except Exception as exc:  # purity: never raise
        result: Dict[str, Any] = {
            "status": "INSUFFICIENT_DATA",
            "market": str(market).lower(),
            "regression": False,
            "monotone_improving": False,
            "n_data_cycles": 0,
            "window": window,
            "window_deltas": [],
            "note": _CALIBRATION_NOTE,
            "reason": (
                "compute_trend raised %s: %s -- defaulting regression=False (do-no-harm)"
                % (type(exc).__name__, exc)
            ),
        }
        _assert_no_banned_keys(result)
        return result

    mkt = trend.get("market", str(market).lower())

    # ---- INSUFFICIENT_DATA path -------------------------------------------
    if trend.get("status") != "ok":
        result = {
            "status": "INSUFFICIENT_DATA",
            "market": mkt,
            "regression": False,
            "monotone_improving": False,
            "n_data_cycles": trend.get("n_data_cycles", 0),
            "window": window,
            "window_deltas": [],
            "note": _CALIBRATION_NOTE,
            "reason": trend.get("reason", "INSUFFICIENT_DATA from compute_trend"),
        }
        _assert_no_banned_keys(result)
        return result

    # ---- ok path -----------------------------------------------------------
    all_deltas: List[float] = trend.get("deltas", [])
    n_data: int = trend.get("n_data_cycles", 0)
    monotone_improving: bool = bool(trend.get("monotone_improving", False))

    # Clamp window to available deltas so we never IndexError on a short series.
    effective_window = min(window, len(all_deltas))
    window_deltas = all_deltas[-effective_window:] if effective_window > 0 else []

    regression = _is_monotone_worsening(window_deltas, regression_tol)

    if regression:
        reason = (
            "ADVISORY ALARM: market '%s' shows monotone Brier worsening across "
            "the last %d cycle(s) (all deltas > 0, at least one > tol=%.4f). "
            "This is advisory only -- no flag is flipped, no promotion made."
            % (mkt, effective_window, regression_tol)
        )
    elif not monotone_improving:
        reason = (
            "non-monotone series (at least one improvement step exists or series "
            "is mixed); regression=False -- not a sustained worsening pattern"
        )
    else:
        reason = (
            "all %d cycle(s) show non-regressing Brier (monotone_improving=True); "
            "regression=False" % n_data
        )

    result = {
        "status": "ok",
        "market": mkt,
        "regression": regression,
        "monotone_improving": monotone_improving,
        "n_data_cycles": n_data,
        "window": effective_window,
        "window_deltas": window_deltas,
        "note": _CALIBRATION_NOTE,
        "reason": reason,
    }
    _assert_no_banned_keys(result)
    return result


def check_all_alarms(
    ledger_path: Optional[Path] = None,
    window: int = DEFAULT_WINDOW,
    regression_tol: float = REGRESSION_TOL,
    min_cycles: int = MIN_CYCLES,
) -> Dict[str, Dict[str, Any]]:
    """Emit recal-drift alarms for ALL markets found in the ledger.

    Returns a dict keyed by market.  Markets with INSUFFICIENT_DATA are
    included with regression=False -- never silently dropped.  Never raises.
    """
    try:
        all_trends = compute_trends(
            ledger_path=ledger_path,
            regression_tol=regression_tol,
            min_cycles=min_cycles,
        )
    except Exception:  # purity: never raise
        return {}

    out: Dict[str, Dict[str, Any]] = {}
    for mkt in all_trends:
        out[mkt] = check_alarm(
            mkt,
            ledger_path=ledger_path,
            window=window,
            regression_tol=regression_tol,
            min_cycles=min_cycles,
        )
    return out


__all__ = [
    "check_alarm",
    "check_all_alarms",
    "DEFAULT_WINDOW",
]
