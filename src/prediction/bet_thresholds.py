"""src/prediction/bet_thresholds.py — central per-stat edge-threshold config.

Iter-15 threshold ship:
  STL: 0.5 → 0.10  (Iter 14a sweep: 192 bets, +20.9% ROI, 9/11 folds pos)
  BLK: 0.5 → 0.40  (Iter 14a sweep: 220 bets, +26.0% ROI, 8/11 folds pos)
  All others: 0.5 (unchanged)

Usage:
    from src.prediction.bet_thresholds import edge_threshold_for

    thr = edge_threshold_for("stl")   # 0.10
    thr = edge_threshold_for("blk")   # 0.40
    thr = edge_threshold_for("pts")   # 0.5 (default)
    thr = edge_threshold_for("unknown")  # 0.5 (safe fallback)
"""
from __future__ import annotations

_STAT_THRESHOLDS: dict[str, float] = {
    "pts":  0.5,
    "ast":  0.5,
    "reb":  0.5,
    "fg3m": 0.5,
    "stl":  0.10,
    "blk":  0.40,
    "tov":  0.5,
}

_DEFAULT_THRESHOLD: float = 0.5


def edge_threshold_for(stat: str) -> float:
    """Return the edge threshold for *stat* (case-insensitive).

    Falls back to ``_DEFAULT_THRESHOLD`` for unknown stat strings so
    existing callers that don't specify a stat remain unaffected.
    """
    return _STAT_THRESHOLDS.get(stat.lower(), _DEFAULT_THRESHOLD)
