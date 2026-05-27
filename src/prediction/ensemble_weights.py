"""ensemble_weights.py — Iter-28: per-stat OLD+NEW model ensemble weights.

Iter-28 sweep result: ensembling the OLD model (cutoff 2024-04-21,
backup_iter22_promoted_20260527_165457) with the NEW model (cutoff
2025-04-21, oos_pre_playoffs) lifted aggregate 2025-26 ROI by +1.44pp
(7.91% -> 9.35%) across 1,134->1,147 bets.

Gains by stat:
  AST: +4.77pp ROI  (w_new=0.6, +17.01% vs +12.24%)
  STL: +5.78pp ROI  (w_new=0.5, +15.70% vs +9.92%)
  REB: +0.17pp ROI  (w_new=0.9, +23.14% vs +22.97%)
  PTS: flat  (w_new=1.0 — old model same quality)
  FG3M: flat (w_new=1.0 — old model slightly worse)
  BLK: flat  (w_new=1.0 — new model clearly better)

Public API
----------
  CUTOFF_NEW_DIR  : str — path to new model directory
  CUTOFF_OLD_DIR  : str — path to old model directory
  W_NEW : dict     — per-stat weight for new model (0.0-1.0)
  W_OLD : dict     — per-stat weight for old model (1 - W_NEW)
  apply_ensemble_weight(stat, pred_new, pred_old) -> float
"""
from __future__ import annotations

import os

# ─────────────────────────── model directories ───────────────────────────────

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CUTOFF_NEW_DIR: str = os.path.join(_PROJECT_DIR, "data", "models", "oos_pre_playoffs")
CUTOFF_OLD_DIR: str = os.path.join(_PROJECT_DIR, "data", "models",
                                   "_backup_iter22_promoted_20260527_165457")

# ─────────────────────────── per-stat weights ────────────────────────────────
# w_new + w_old = 1.0 per stat.
# Decision: SHIP — aggregate ROI +1.44pp on 2025-26 OOS eval (1,147 bets).
# Iter-28 generated_at: 2026-05-27T22:43:22Z

W_NEW: dict[str, float] = {
    "pts":  1.0,   # no ensemble lift — old PTS model same quality
    "reb":  0.9,   # slight lift with 10% old blend
    "ast":  0.6,   # +4.77pp ROI from old model; old model captures stable AST patterns
    "fg3m": 1.0,   # no ensemble lift — new model clearly better
    "stl":  0.5,   # +5.78pp ROI from equal-weight blend
    "blk":  1.0,   # no ensemble lift — new model clearly better
    "tov":  1.0,   # not in eval set; default to new only
}

W_OLD: dict[str, float] = {stat: round(1.0 - w, 2) for stat, w in W_NEW.items()}


def apply_ensemble_weight(stat: str, pred_new: float, pred_old: float | None) -> float:
    """Apply per-stat ensemble weight to combine NEW and OLD model predictions.

    Args:
        stat:      Stat name (pts, reb, ast, fg3m, stl, blk, tov).
        pred_new:  Prediction from the new model (cutoff 2025-04-21).
        pred_old:  Prediction from the old model (cutoff 2024-04-21).
                   May be None if old model is unavailable — falls back to new only.

    Returns:
        Ensembled prediction (float).
    """
    w_new = W_NEW.get(stat, 1.0)
    w_old = W_OLD.get(stat, 0.0)

    if pred_old is None or w_old == 0.0:
        return pred_new

    return w_new * pred_new + w_old * pred_old
