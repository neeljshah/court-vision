"""domains.basketball_nba.prop_quantile_pricer -- NBA prop empirical-quantile pricer.

Replaces the Gaussian-tail (erf) assumption with a recency-weighted empirical CDF
so that heavy-tailed and skewed stat distributions (BLK, STL, 3PM) are priced more
accurately.

P(stat >= line) is computed from a monotone, recency-weighted ECDF of a player's
recent game log:

  - weights decay exponentially with age: w_i = exp(-lambda * days_ago_i)
  - ECDF is built on the weighted sample; ties handled by averaging
  - line interpolated between adjacent ECDF values for a smooth, monotone output

HONEST: p_over is a calibrated probability, NOT a betting edge. No $ field.
INVARIANTS: <=300 LOC; ASCII only; no src/ imports; no network I/O; read-only.

Usage::
    from domains.basketball_nba.prop_quantile_pricer import price_empirical_over

    result = price_empirical_over(
        sample=player_game_log,           # list/array of observed stat values
        line=22.5,
        dates=game_dates,                 # parallel list of datetime/date objects
        as_of=today,                      # price date (all sample rows must be <)
        half_life_days=60,                # recency half-life
    )
    # result["p_over"] is float in [0,1] or None if UNAVAILABLE
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Union
import datetime

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_HALF_LIFE_DAYS = 60.0   # exponential recency half-life
_MIN_SAMPLE = 5                  # fewer games -> UNAVAILABLE (too thin to trust)
_UNAVAILABLE_STATUS = "UNAVAILABLE"
_OK_STATUS = "ok"

_HONEST_NOTE = (
    "Empirical recency-weighted P(over line). No Gaussian assumption; "
    "recency-decay weights recent games more. Calibration only -- no $ edge."
)


# ---------------------------------------------------------------------------
# Core math
# ---------------------------------------------------------------------------

def _decay_weights(
    days_ago: np.ndarray,
    half_life: float,
) -> np.ndarray:
    """Exponential recency weights from days-ago vector.

    w_i = exp(-ln(2) * days_ago_i / half_life).  Output is NOT normalised
    (caller normalises as needed).  All weights > 0.
    """
    lam = math.log(2.0) / max(half_life, 1e-3)
    return np.exp(-lam * days_ago)


def _weighted_ecdf_p_over(
    values: np.ndarray,
    weights: np.ndarray,
    line: float,
) -> float:
    """P(value >= line) from a recency-weighted empirical CDF.

    Monotone decreasing in line:
      - line <= min(values) -> 1.0
      - line >  max(values) -> 0.0
      - otherwise linear interpolation between adjacent sorted values

    Handles ties by grouping (each unique value contributes once in the CDF).
    """
    w = weights / weights.sum()  # normalise
    order = np.argsort(values)
    sv = values[order]
    sw = w[order]

    # Build CDF: cdf[i] = P(value <= sv[i]) using cumulative weights.
    cdf = np.cumsum(sw)

    # P(value >= line) = 1 - P(value < line)
    # P(value < line) = sum of weights for sv < line (strict less-than)
    idx = np.searchsorted(sv, line, side="left")  # first idx where sv >= line
    if idx == 0:
        return 1.0  # line is at or below the minimum -- all values exceed it
    if idx >= len(sv):
        return 0.0  # line exceeds all observed values

    # P(value < line) = sum of weights for values strictly less than line.
    # cdf[idx-1] gives P(value <= sv[idx-1]) where sv[idx-1] < line.
    # That equals P(value < line) because searchsorted(side="left") ensures
    # sv[idx-1] < line <= sv[idx].
    #
    # We do NOT interpolate further: P(value >= line) must include all mass
    # at exactly sv[idx] = line when line is an observed value.  Linear
    # interpolation would incorrectly smear the CDF mass and produce a value
    # that diverges from the realized fraction on discrete distributions.
    p_below = float(cdf[idx - 1])

    return max(0.0, min(1.0, 1.0 - p_below))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def price_empirical_over(
    sample: Sequence[float],
    line: float,
    dates: Optional[Sequence[Any]] = None,
    as_of: Optional[Any] = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
    min_sample: int = _MIN_SAMPLE,
) -> Dict[str, Any]:
    """Price P(stat >= line) from a recency-weighted empirical sample.

    Parameters
    ----------
    sample:
        Observed stat values (e.g. last N game pts totals).  Must correspond
        element-wise to *dates* when dates is provided.
    line:
        Prop line to price (e.g. 22.5).
    dates:
        Dates of each observation (datetime.date, datetime.datetime, or
        pandas Timestamp).  When provided, exponential recency weights are
        applied.  When None, all observations receive equal weight.
    as_of:
        Pricing date.  Observations on or after this date are EXCLUDED to
        prevent leaking same-day game data.  When None, no filtering is done.
    half_life_days:
        Exponential half-life for recency decay (default 60 days).
    min_sample:
        Minimum observations after filtering to return a valid price
        (fewer -> UNAVAILABLE).

    Returns
    -------
    dict with keys:
        status     : "ok" | "UNAVAILABLE"
        p_over     : float in [0,1] or None
        p_under    : float in [0,1] or None
        line       : float
        n_games    : int (number of games used)
        method     : "empirical_quantile"
        honest_note: str
    """
    arr = np.asarray(sample, dtype=float)

    # --- filter by as_of (leak-free) ----------------------------------------
    if dates is not None and as_of is not None:
        as_of_dt = _to_date(as_of)
        mask = np.array([_to_date(d) < as_of_dt for d in dates], dtype=bool)
        arr = arr[mask]
        dates_filtered = [d for d, m in zip(dates, mask) if m]
    else:
        dates_filtered = list(dates) if dates is not None else []

    # --- guard: too few observations -----------------------------------------
    if len(arr) < min_sample or len(arr) == 0:
        return _unavailable(line=line, n_games=len(arr),
                            reason="insufficient_sample")

    # --- recency weights -------------------------------------------------------
    if dates_filtered and as_of is not None:
        as_of_dt = _to_date(as_of)
        days_ago = np.array(
            [(as_of_dt - _to_date(d)).days for d in dates_filtered],
            dtype=float,
        )
        days_ago = np.clip(days_ago, 0.0, None)
        weights = _decay_weights(days_ago, half_life=half_life_days)
    else:
        weights = np.ones(len(arr), dtype=float)

    # --- price -----------------------------------------------------------------
    p_over = _weighted_ecdf_p_over(arr, weights, float(line))
    p_under = 1.0 - p_over

    return {
        "status": _OK_STATUS,
        "p_over": round(p_over, 4),
        "p_under": round(p_under, 4),
        "line": float(line),
        "n_games": int(len(arr)),
        "method": "empirical_quantile",
        "honest_note": _HONEST_NOTE,
    }


def compare_vs_gaussian(
    sample: Sequence[float],
    line: float,
    dates: Optional[Sequence[Any]] = None,
    as_of: Optional[Any] = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
    min_sample: int = _MIN_SAMPLE,
) -> Dict[str, Any]:
    """Return both empirical and Gaussian p_over for the same sample.

    Useful for diagnostics and OOF coverage comparison.  Gaussian uses the
    recency-weighted mean and standard deviation of the sample (same weights).

    Returns dict with:
        p_over_empirical, p_over_gaussian, p_over_delta (empirical - gaussian),
        n_games, line, plus all keys from price_empirical_over.
    """
    emp = price_empirical_over(
        sample=sample, line=line, dates=dates, as_of=as_of,
        half_life_days=half_life_days, min_sample=min_sample,
    )

    if emp["status"] == _UNAVAILABLE_STATUS:
        return dict(emp, p_over_gaussian=None, p_over_delta=None)

    # Build same filtered/weighted arrays for Gaussian
    arr = np.asarray(sample, dtype=float)
    if dates is not None and as_of is not None:
        as_of_dt = _to_date(as_of)
        mask = np.array([_to_date(d) < as_of_dt for d in dates], dtype=bool)
        arr = arr[mask]
        dates_filt = [d for d, m in zip(dates, mask) if m]
    else:
        dates_filt = list(dates) if dates is not None else []

    if dates_filt and as_of is not None:
        as_of_dt = _to_date(as_of)
        days_ago = np.clip(
            np.array([(as_of_dt - _to_date(d)).days for d in dates_filt], dtype=float),
            0.0, None,
        )
        w = _decay_weights(days_ago, half_life=half_life_days)
    else:
        w = np.ones(len(arr), dtype=float)

    w_norm = w / w.sum()
    mu = float(np.dot(w_norm, arr))
    var = float(np.dot(w_norm, (arr - mu) ** 2))
    sigma = math.sqrt(max(var, 1e-9))

    # Gaussian P(X >= line) = 1 - Phi((line - mu)/sigma)
    z = (float(line) - mu) / sigma
    p_gauss = 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))

    delta = round(float(emp["p_over"]) - p_gauss, 4)
    return dict(
        emp,
        p_over_empirical=emp["p_over"],
        p_over_gaussian=round(p_gauss, 4),
        p_over_delta=delta,
        proj_mean=round(mu, 3),
        proj_sigma=round(sigma, 3),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_date(d: Any) -> datetime.date:
    """Coerce datetime/date/Timestamp/str to datetime.date."""
    if isinstance(d, datetime.datetime):
        return d.date()
    if isinstance(d, datetime.date):
        return d
    # pandas Timestamp or anything with .date()
    if hasattr(d, "date"):
        return d.date()
    # ISO string fallback
    return datetime.date.fromisoformat(str(d)[:10])


def _unavailable(line: float, n_games: int, reason: str) -> Dict[str, Any]:
    return {
        "status": _UNAVAILABLE_STATUS,
        "p_over": None,
        "p_under": None,
        "line": float(line),
        "n_games": n_games,
        "method": "empirical_quantile",
        "reason": reason,
        "honest_note": _HONEST_NOTE,
    }
