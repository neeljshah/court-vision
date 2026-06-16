"""In-game blend core -- the #1 leverage lever (blueprint N3), as tested reference code.

final = w(time, margin) * P_live + (1 - w) * P0

  P0      = the existing calibrated pregame prior (treated as a black box input here).
  P_live  = a lightweight live estimate from realized state (score_diff, seconds_remaining).
  w       = an empirical 2D weight surface, FIT on one set and EVALUATED on a DIFFERENT one
            (the documented overfitting trap -- never fit and evaluate w on the same season).

This is new information by construction (realized game state the pregame close never had), so a
gain here is an honest CALIBRATION improvement, not a re-pricing of priced facts. No dollar edge is
computed or implied. numpy + stdlib only; reuse dm_test.diebold_mariano (clustered by game_id) to
test "blend beats pregame-only".
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple
import numpy as np


def blend(p0: float, p_live: float, w: float) -> float:
    """w=0 -> trust pregame; w=1 -> trust live. Clamped to [0,1]."""
    w = min(1.0, max(0.0, w))
    return float(min(1.0, max(0.0, w * p_live + (1.0 - w) * p0)))


def exp_smooth(seq: Sequence[float], alpha: float = 0.5) -> float:
    """Exponential smoothing over the last few possessions for temporal stability."""
    s = None
    for x in seq:
        s = float(x) if s is None else alpha * float(x) + (1.0 - alpha) * s
    return 0.0 if s is None else s


def time_bucket(seconds_remaining: float, total: float = 2880.0, n: int = 4) -> int:
    """Coarse progress bucket (0 = early, n-1 = late). NBA default 48 min = 2880s."""
    frac_elapsed = 1.0 - max(0.0, min(1.0, seconds_remaining / total))
    return min(n - 1, int(frac_elapsed * n))


def margin_bucket(score_diff: float, edges: Sequence[float] = (-12, -4, 4, 12)) -> int:
    """Bucket by absolute closeness/blowout via signed-margin edges."""
    b = 0
    for e in edges:
        if score_diff >= e:
            b += 1
    return b  # 0..len(edges)


@dataclass
class WeightSurface:
    """2D grid of blend weights over (time_bucket, margin_bucket)."""
    n_time: int = 4
    n_margin: int = 5
    grid: Dict[Tuple[int, int], float] = field(default_factory=dict)
    default: float = 0.0  # empty cell -> trust the pregame prior

    def weight(self, seconds_remaining: float, score_diff: float) -> float:
        key = (time_bucket(seconds_remaining, n=self.n_time), margin_bucket(score_diff))
        return self.grid.get(key, self.default)


def fit_weight_surface(states: List[dict], w_grid: Sequence[float] = None,
                       min_cell: int = 20) -> WeightSurface:
    """Fit w per (time,margin) cell by minimizing Brier of the blend on `states`.

    states: dicts with keys p0, p_live, seconds_remaining, score_diff, outcome.
    Cells with < min_cell samples fall back to the default (0.0 -> trust pregame),
    so a sparse cell cannot overfit.
    """
    if w_grid is None:
        w_grid = np.linspace(0.0, 1.0, 21)
    surf = WeightSurface()
    cells: Dict[Tuple[int, int], List[dict]] = {}
    for s in states:
        key = (time_bucket(s["seconds_remaining"], n=surf.n_time),
               margin_bucket(s["score_diff"]))
        cells.setdefault(key, []).append(s)
    for key, rows in cells.items():
        if len(rows) < min_cell:
            continue
        p0 = np.array([r["p0"] for r in rows])
        pl = np.array([r["p_live"] for r in rows])
        y = np.array([r["outcome"] for r in rows], dtype=float)
        best_w, best_b = 0.0, np.mean((p0 - y) ** 2)
        for w in w_grid:
            b = np.mean((w * pl + (1 - w) * p0 - y) ** 2)
            if b < best_b:
                best_b, best_w = float(b), float(w)
        surf.grid[key] = best_w
    return surf


def blended_predictions(states: List[dict], surf: WeightSurface) -> np.ndarray:
    """Apply a fitted surface to states -> blended probabilities."""
    out = []
    for s in states:
        w = surf.weight(s["seconds_remaining"], s["score_diff"])
        out.append(blend(s["p0"], s["p_live"], w))
    return np.asarray(out)
