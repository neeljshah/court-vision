"""q4_foul_forecast_v3.py -- cycle 98a (loop 5). Fractional band blend.

WHY: cycle 97e v2 had a CLEAN NNLS fit (CV Q4-PF MAE 0.67, bias -0.01)
but was bimodal-no-op when round-down truncation was applied: 0 of 254
gated rows crossed an integer foul band because mean forecast addition
was 0.66 PF and int(spf + 0.66) == spf for every gated row. The forecast
encoded real information that the integerization layer threw away.

v3 keeps EVERYTHING from v2 -- the NNLS coefficients, the gate, the
feature row -- and replaces ONLY the integerization step. Instead of
binarizing ``spf + forecast`` into a single foul band, we BLEND the
adjacent integer bands by the FRACTIONAL part of the forecast::

    factor = (1 - frac) * band(spf) + frac * band(spf + 1)

with ``frac = forecast_add - int(forecast_add)``. Borderline cases get
proportional shrinkage instead of the integer-cliff over-correction (v1)
or no-op (v2). The two end-points are clean:

    - frac == 0.0 -> factor == band(spf) exactly (no-op for low forecast).
    - frac == 1.0 -> factor == band(spf + 1) exactly (full band shift).

Wiring (after v3 ships)
-----------------------
``predict_in_game.project_snapshot`` calls
``fractional_band_factor(spf, forecast_add, period, clock)`` at endQ3
INSTEAD of ``foul_trouble_factor(spf, period, clock)``. v1 and v2 stay
in-tree as helpers but are marked DEPRECATED in their docstrings.

Strictly read-only at import time. Coefficient cache delegated to v2's
``fit_default_coefficients``.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Sequence

from src.prediction.live_factors import foul_trouble_factor
from src.prediction.q4_foul_forecast_v2 import (
    FEATURE_NAMES,
    GATE_MIN_PF,
    GATE_MIN_Q3,
    build_feature_row,
    fit_default_coefficients,
    forecast_q4_pf_addition_v2,
    passes_gate,
)

# Hard ceiling for the spf+1 lookup so we never query above pf=6 (foul-out).
_MAX_PF = 6


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return v


def fractional_band_factor(
    spf: int,
    forecast_pf_add: float,
    period: int,
    clock_min: float,
) -> float:
    """Blend foul_trouble_factor between adjacent integer bands by frac.

    Returns
    -------
    float
        ``(1 - frac) * band(spf) + frac * band(spf + 1)`` where
        ``frac = forecast_pf_add - int(forecast_pf_add)``.

    Properties (test-locked)
    ------------------------
    - frac == 0.0           -> band(spf) exactly
    - frac == 1.0           -> band(spf + 1) exactly
    - frac == 0.5           -> 0.5 * (band(spf) + band(spf + 1))
    - spf >= _MAX_PF        -> band(spf) (no spf+1 to blend toward)
    - forecast_pf_add < 0   -> treated as 0 (no-op)

    Parameters
    ----------
    spf : int
        Snapshot pf at end of Q3.
    forecast_pf_add : float
        Expected Q4 PF addition (from
        ``forecast_q4_pf_addition_v2``).
    period : int
        Current period (forwarded to ``foul_trouble_factor``).
    clock_min : float
        Decimal minutes remaining (forwarded to ``foul_trouble_factor``).

    Notes
    -----
    Integer-walk semantics: if ``forecast_pf_add`` is, say, 1.66, then
    ``int(1.66) = 1`` whole foul gets added to spf first, and we blend
    between band(spf+1) and band(spf+2) using frac=0.66. The whole-foul
    portion is non-negotiable (forecast crossed a full band), the
    fractional portion shrinks proportionally.
    """
    spf_i = max(0, _safe_int(spf))
    add = _safe_float(forecast_pf_add, default=0.0)
    if add < 0.0:
        add = 0.0
    period_i = _safe_int(period)
    clock_f = _safe_float(clock_min, default=12.0)

    whole = int(add)  # truncate toward zero (add >= 0 guaranteed)
    frac = add - whole

    base_pf = min(_MAX_PF, spf_i + whole)
    next_pf = min(_MAX_PF, base_pf + 1)

    band_lo = foul_trouble_factor(base_pf, period_i, clock_f)
    band_hi = foul_trouble_factor(next_pf, period_i, clock_f)

    # Edge case: base_pf and next_pf are the same (hit the ceiling) ->
    # blend collapses to a single point regardless of frac, which is what
    # we want (no extra shrinkage past foul-out).
    if base_pf == next_pf:
        return float(band_lo)

    return float((1.0 - frac) * band_lo + frac * band_hi)


def fractional_factor_for_snapshot(
    pf_through_q3: Any,
    q3_pf: Any,
    min_q3: Any,
    position_proxy: Optional[str],
    period: Any,
    clock_min: Any,
    opp_foul_rate_l5: Optional[float] = None,
    coefficients: Optional[Sequence[float]] = None,
) -> float:
    """End-to-end factor: forecast + gate + fractional blend.

    Returns ``foul_trouble_factor(spf, period, clock_min)`` (i.e. v2's
    baseline behavior) when the gate doesn't clear. Otherwise blends per
    ``fractional_band_factor``.

    This is the canonical entry point that ``project_snapshot`` will call.
    """
    spf = max(0, _safe_int(pf_through_q3))
    period_i = _safe_int(period)
    clock_f = _safe_float(clock_min, default=12.0)

    # Gate: if not foul-troubled enough, fall back to plain band lookup.
    if not passes_gate(spf, min_q3):
        return float(foul_trouble_factor(spf, period_i, clock_f))

    # v2 forecast (clamped + gated). Coefficients fit once + cached.
    add = forecast_q4_pf_addition_v2(
        pf_through_q3=spf,
        q3_pf=q3_pf,
        min_q3=min_q3,
        position_proxy=position_proxy,
        opp_foul_rate_l5=opp_foul_rate_l5,
        coefficients=coefficients,
    )
    return fractional_band_factor(spf, add, period_i, clock_f)


__all__ = [
    "FEATURE_NAMES",
    "GATE_MIN_PF",
    "GATE_MIN_Q3",
    "fractional_band_factor",
    "fractional_factor_for_snapshot",
    "passes_gate",
    "build_feature_row",
    "fit_default_coefficients",
    "forecast_q4_pf_addition_v2",
]
