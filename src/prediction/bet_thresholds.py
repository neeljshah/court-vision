"""src/prediction/bet_thresholds.py — central per-stat edge-threshold config.

Iter-25 recalibration on Iter-22 model (commit 5fb964f1).
  Approach: thresholds  |  lift vs baseline: +3.83pp
  Baseline 2025-26 ROI: +15.67%

  Iter-15 thresholds (prior values):
    STL: 0.5 → 0.10  (Iter 14a sweep)
    BLK: 0.5 → 0.40  (Iter 14a sweep)

Usage:
    from src.prediction.bet_thresholds import edge_threshold_for

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


def edge_threshold_for(stat: str) -> float:
    """Return the edge threshold for *stat* (case-insensitive).

    Falls back to ``_DEFAULT_THRESHOLD`` for unknown stat strings so
    existing callers that don't specify a stat remain unaffected.
    """
    return _STAT_THRESHOLDS.get(stat.lower(), _DEFAULT_THRESHOLD)
