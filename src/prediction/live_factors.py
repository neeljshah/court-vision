"""live_factors.py — single source of truth for live in-game adjustment factors.

Cycle 89b (loop 5) unification.

Prior to this module, three independent copies of ``foul_trouble_factor`` lived
in ``scripts/predict_in_game.py``, ``scripts/foul_trouble_adjust.py``, and
``scripts/live_player.py`` (under the wrapper name ``foul_factor_for``). All
three disagreed on the same input — e.g. Q3 with pf=4 returned 0.70, 0.55, and
0.55 respectively — which silently corrupted every downstream MAE / EV / alert
computation depending on which entry point fired.

This module is now the SINGLE SOURCE OF TRUTH. All consumers MUST import
``foul_trouble_factor`` from here. The canonical table is the most conservative
of the three (``foul_trouble_adjust.py``'s) because the underlying factors are
heuristic and not yet empirically calibrated.

Factor table
------------
    pf >= 5 (any period)                       -> 0.40
    pf == 4 and period <= 2                     -> 0.55
    pf == 4 and period == 3                     -> 0.55
    pf == 4 and period == 4 and clock > 6.0     -> 0.65
    pf == 4 (late Q4 OR OT)                     -> 0.90
    pf == 3 and period == 2                     -> 0.80
    otherwise                                   -> 1.00

Inputs are coerced defensively — ``None``, strings, NaNs, and negative values
all fall through to 1.00 (no adjustment) rather than raising. This matches the
"safe for live dashboards" contract: a malformed snapshot must never crash the
prediction loop.
"""
from __future__ import annotations

from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int; return ``default`` on any failure (None, str, NaN, ...)."""
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        try:
            v = int(float(value))
        except (TypeError, ValueError):
            return default
    return v


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float; return ``default`` on any failure."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    # Reject NaN (NaN != NaN).
    if v != v:
        return default
    return v


def foul_trouble_factor(pf: Any, period: Any,
                        clock_minutes_remaining: Any = 12.0) -> float:
    """Penalty multiplier for remaining-minutes when a player is in foul trouble.

    Parameters
    ----------
    pf : int-like
        Current personal-foul count. ``None`` / garbage -> treated as 0.
    period : int-like
        Current period (1-4 regulation, 5+ for OT). Garbage -> treated as 0
        (returns 1.00, no adjustment).
    clock_minutes_remaining : float-like, default 12.0
        Decimal minutes left on the current period's game clock (e.g. 5.7 when
        the clock shows 5:42). Only consulted for the Q4 split. Garbage -> 12.0.

    Returns
    -------
    float
        Multiplicative penalty in [0.0, 1.0]. 1.00 means "no foul trouble"; a
        smaller value means "coach is likely to bench — scale remaining-minutes
        accordingly".

    Notes
    -----
    See module docstring for the canonical table. This is the MOST CONSERVATIVE
    of the three legacy tables (was ``foul_trouble_adjust.foul_trouble_factor``).
    """
    pf_i = _safe_int(pf, default=0)
    period_i = _safe_int(period, default=0)
    clock_f = _safe_float(clock_minutes_remaining, default=12.0)

    # Negative pf is nonsensical — treat as "no fouls".
    if pf_i < 0:
        pf_i = 0

    # Rule 1: 5+ fouls anywhere — one away from foul-out, aggressive bench.
    if pf_i >= 5:
        return 0.40

    # Rule 2: 4 fouls — period-dependent leash.
    if pf_i == 4:
        if period_i <= 2:
            return 0.55
        if period_i == 3:
            return 0.55
        # Q4: split on clock; OT (period >= 5) acts like late Q4.
        if period_i == 4 and clock_f > 6.0:
            return 0.65
        return 0.90

    # Rule 3: 3 fouls in Q2 — common "save him for the half" bench.
    if pf_i == 3 and period_i == 2:
        return 0.80

    # No trouble.
    return 1.00


__all__ = ["foul_trouble_factor"]
