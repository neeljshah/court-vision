"""q4_foul_forecast.py -- cycle 96c (loop 5). Forecast Q4 PF additions.

WHY: cycle 95b's endQ3 decomposition surfaced FOUL_CHANGE as the dominant
residual failure mode (+0.50 PTS MAE excess, bias -1.25 -> projector
UNDER-counts the foul-out hit). The cycle-89b unified ``foul_trouble_factor``
sees only the SNAPSHOT pf at end-of-Q3; it cannot anticipate the Q4
foul-burst that benches a player who's at pf=3 but trending hot on fouls.

This module bakes the expected Q4 PF additions onto the snapshot pf BEFORE
passing it into ``foul_trouble_factor``. The forecast is intentionally a
tiny, transparent heuristic (no model fit, no parquet write) so it stays
auditable and unit-testable. Calibration is done empirically by
``scripts/probe_q4_foul_forecast.py`` against the 50-game retro corpus.

Forecast model
--------------
Inputs:
    pf_through_q3    -- cumulative PF coming into Q4 (int, 0-6+)
    q3_pf            -- PF picked up specifically in Q3 (int)
    position_proxy   -- 'C', 'F', 'G' or None (bigs draw more help-D fouls)
    opp_foul_drawn_rate -- opponent's per-poss FT rate (optional, 0.0-1.0)

Output:
    expected Q4 PF addition, clamped to [0.0, 3.0]

Base rate: 0.8 fouls/Q for any rotation player.
Foul-trouble lift: +0.4 when pf_through_q3 >= 3 (already in danger zone).
Q3 burst signal: +0.5 when q3_pf >= 2 (foul-burst tends to continue).
Position lift: +0.3 for centers / bigs (help-D + box-out fouls).
Foul-out protection: when pf_through_q3 >= 5, rate DROPS to 0.4 (player
plays cautiously, coach sits at any whistle).

Cycle 96c probe (``probe_q4_foul_forecast.py``) validates these constants
against the parquet and ships only if endQ3 PTS MAE on the foul_change
stratum improves by >= 0.10.
"""
from __future__ import annotations

from typing import Any, Optional


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int; return ``default`` on any failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def _normalize_position(position_proxy: Optional[str]) -> str:
    """Map free-text position strings to one of {'C', 'F', 'G', ''}.

    The ``data/player_positions.parquet`` rows look like 'Guard',
    'Forward-Center', 'Center', etc. We treat anything containing
    'Center' as a big, anything containing 'Forward' as a forward,
    anything containing 'Guard' as a guard, else unknown.
    """
    if not position_proxy:
        return ""
    s = str(position_proxy).strip().lower()
    if not s:
        return ""
    if "center" in s:
        return "C"
    if "forward" in s:
        return "F"
    if "guard" in s:
        return "G"
    # Already-normalized single-char inputs ('C', 'PF', 'SF', 'PG', 'SG').
    u = s.upper()
    if u in {"C"}:
        return "C"
    if u in {"PF", "SF", "F"}:
        return "F"
    if u in {"PG", "SG", "G"}:
        return "G"
    return ""


def forecast_q4_pf_addition(
    pf_through_q3: Any,
    q3_pf: Any = 0,
    position_proxy: Optional[str] = None,
    opp_foul_drawn_rate: Optional[float] = None,
) -> float:
    """Forecast additional fouls a player will pick up in Q4.

    Parameters
    ----------
    pf_through_q3 : int-like
        Cumulative personal fouls coming OUT of Q3 (snapshot pf at endQ3).
    q3_pf : int-like, default 0
        PF specifically picked up in Q3 (for foul-burst detection).
    position_proxy : str, optional
        Player position string ('Center', 'Guard', 'PF', etc).
    opp_foul_drawn_rate : float, optional
        Opponent's free-throw-drawn rate (currently unused -- reserved for
        future calibration; including the slot keeps the call-site stable).

    Returns
    -------
    float
        Expected Q4 PF addition in [0.0, 3.0].
    """
    pf = max(0, _safe_int(pf_through_q3, default=0))
    q3 = max(0, _safe_int(q3_pf, default=0))
    pos = _normalize_position(position_proxy)

    # Foul-out protection: at pf>=5 the player is one whistle from foul-out,
    # the coach pulls early on contact, and the player plays cautiously.
    if pf >= 5:
        forecast = 0.4
    elif pf >= 3:
        # Foul-trouble zone: rate elevated vs baseline rotation player.
        forecast = 0.8 + 0.4
    else:
        forecast = 0.8

    # Q3 foul-burst (>=2 fouls in one quarter) tends to continue.
    if q3 >= 2 and pf < 5:
        forecast += 0.5

    # Bigs draw more help-D + box-out fouls.
    if pos == "C" and pf < 5:
        forecast += 0.3

    # opp_foul_drawn_rate currently unused -- reserved hook.
    _ = opp_foul_drawn_rate

    if forecast < 0.0:
        forecast = 0.0
    if forecast > 3.0:
        forecast = 3.0
    return float(forecast)


def forecasted_endgame_pf(
    pf_through_q3: Any,
    q3_pf: Any = 0,
    position_proxy: Optional[str] = None,
    opp_foul_drawn_rate: Optional[float] = None,
) -> int:
    """Convenience: snapshot pf + forecasted Q4 addition, rounded to int.

    Returned as int so it slots directly into ``foul_trouble_factor`` which
    branches on integer pf bands. Clamped at 6 to avoid silly values.
    """
    pf = max(0, _safe_int(pf_through_q3, default=0))
    add = forecast_q4_pf_addition(pf, q3_pf, position_proxy, opp_foul_drawn_rate)
    end = pf + add
    out = int(round(end))
    if out > 6:
        out = 6
    return out


__all__ = ["forecast_q4_pf_addition", "forecasted_endgame_pf"]
