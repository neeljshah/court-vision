"""src/prediction/bet_thresholds.py — central per-stat edge-threshold config.

Iter-25 recalibration on Iter-22 model (commit 5fb964f1).
  Approach: thresholds  |  lift vs baseline: +3.83pp
  Baseline 2025-26 ROI: +15.67%

  Iter-15 thresholds (prior values):
    STL: 0.5 -> 0.10  (Iter 14a sweep)
    BLK: 0.5 -> 0.40  (Iter 14a sweep)

Iter-33: Kelly-B stake sizing enabled.
  kelly_b_stake() in betting_portfolio.py.
  lift vs flat: +2.52pp aggregate ROI (1,016 OOS bets, 2025-26).
  pts regression: -2.54pp (1 stat; ship criterion allows <=1 regression).
  Decision: SHIP.

Usage:
    from src.prediction.bet_thresholds import edge_threshold_for, KELLY_B_ENABLED

    thr = edge_threshold_for("stl")
    thr = edge_threshold_for("pts")
    thr = edge_threshold_for("unknown")  # 0.5 (safe fallback)
"""
from __future__ import annotations

_STAT_THRESHOLDS: dict[str, float] = {
    "pts":  0.7,
    "reb":  1.5,
    "ast":  1.0,
    "fg3m":  0.7,
    "stl":  0.4,
    "blk":  0.4,
    "tov":  0.5,
}

_DEFAULT_THRESHOLD: float = 0.5

# ── Iter-33: Kelly-B sizing feature flag ─────────────────────────────────────
# When True, bet_selector should call betting_portfolio.kelly_b_stake() instead
# of flat-1u sizing for all above-threshold bets.
KELLY_B_ENABLED: bool = True

# Calibrated hit-rate anchors for Kelly-B p_win interpolation (training obs).
# Updated via iter33_fractional_kelly_backtest.py.
KELLY_B_HIT_RATES: dict[str, float] = {
    "pts":  0.5847,
    "reb":  0.5982,
    "ast":  0.6716,
    "fg3m": 0.7183,
    "stl":  0.6183,
    "blk":  0.6654,
    "tov":  0.5200,
}

# Max stake multiplier per bet (in units) — iter-33 blowup guard.
KELLY_B_MAX_UNITS: float = 3.0


def edge_threshold_for(stat: str) -> float:
    """Return the edge threshold for *stat* (case-insensitive).

    Falls back to ``_DEFAULT_THRESHOLD`` for unknown stat strings so
    existing callers that don't specify a stat remain unaffected.
    """
    return _STAT_THRESHOLDS.get(stat.lower(), _DEFAULT_THRESHOLD)


def kelly_b_hit_rate_for(stat: str) -> float:
    """Return the Kelly-B calibrated hit-rate anchor for *stat*."""
    return KELLY_B_HIT_RATES.get(stat.lower(), 0.52)
