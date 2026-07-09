"""scripts.platformkit.ingame.mlb_winprob_v4_blend -- per-phase logit-blend + game-level
Brier helpers for mlb_winprob_v4.py (LOC-cap split, zero behavior change; see
mlb_winprob_v4.py's docstring for the full rung-4 design/leak-audit).

PHASES/W_GRID: blend weight w_phase in {0, .1, ..., 1.0} (coarse grid), one per
early/mid/late (sb.phase_bucket convention) -- the regularization v3's unconstrained
per-tick 2-coefficient logistic fit lacked.

Per-file test: covered by test_mlb_winprob_v4.py (imports this module directly).
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from scripts.platformkit.ingame.mlb_winprob_v3_prior import _logit

PHASES: Tuple[str, ...] = ("early", "mid", "late")
W_GRID: Tuple[float, ...] = tuple(round(i * 0.1, 1) for i in range(11))


def game_level_brier(probs: Any, y: Any, game_ids: Any) -> float:
    """Mean-of-per-game-mean squared error (each game weighted equally, not each tick)."""
    if len(probs) == 0:
        return float("nan")
    by_game: Dict[str, List[float]] = {}
    for p, yy, g in zip(probs, y, game_ids):
        by_game.setdefault(str(g), []).append((float(p) - float(yy)) ** 2)
    per_game = [sum(v) / len(v) for v in by_game.values()]
    return sum(per_game) / len(per_game)


def blend(p_state: Any, prior_home: Any, has_prior: Any, w_by_phase: Dict[str, float],
         phase: Any) -> np.ndarray:
    """sigmoid(w*logit(prior) + (1-w)*logit(p_state)) per row's own phase weight; rows with
    has_prior=False pass p_state through UNCHANGED (never blended toward a fabricated 0.5)."""
    p_state = np.asarray(p_state, dtype=float)
    if len(p_state) == 0:
        return np.zeros(0)
    hp = np.asarray(has_prior, dtype=bool)
    out = p_state.copy()
    if hp.any():
        w = np.array([w_by_phase.get(ph, 0.0) for ph in phase], dtype=float)
        z = w * _logit(prior_home) + (1.0 - w) * _logit(p_state)
        out = np.where(hp, 1.0 / (1.0 + np.exp(-z)), out)
    return out


def select_phase_weights(p_state_val: np.ndarray, y: np.ndarray, game_id: np.ndarray,
                         phase: np.ndarray, prior_home: np.ndarray,
                         has_prior: np.ndarray) -> Dict[str, float]:
    """Per-phase grid search (coarse, game-level objective) for the blend weight."""
    w_by_phase: Dict[str, float] = {}
    for ph in PHASES:
        mask = phase == ph
        if not mask.any():
            w_by_phase[ph] = 0.0
            continue
        best_w, best_b = 0.0, float("inf")
        for w in W_GRID:
            probs = blend(p_state_val[mask], prior_home[mask], has_prior[mask],
                         {ph: w}, phase[mask])
            b = game_level_brier(probs, y[mask], game_id[mask])
            if b < best_b:
                best_b, best_w = b, w
        w_by_phase[ph] = best_w
    return w_by_phase


__all__ = ["PHASES", "W_GRID", "game_level_brier", "blend", "select_phase_weights"]
