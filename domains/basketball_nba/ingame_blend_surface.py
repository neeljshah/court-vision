"""N3 in-game blend -- 2D empirical weight surface w(t, margin) + garbage clamp.

Thin extension over the VERIFIED eval-gate core
(scripts/platformkit/eval_gate/ingame_blend.py): we REUSE its WeightSurface,
fit_weight_surface, blend, blended_predictions, and exp_smooth verbatim (fit on
ONE season, evaluate on a DIFFERENT one -- the documented overfitting trap) and
add only:
  * garbage_clamp -- the late-game blowout hard clamp a linear blend cannot give,
  * the coarse TIME/MARGIN grid edges the blueprint specifies (kept deliberately
    under-resolved with a min-cell floor to resist over-resolution),
  * fit_surface_on_season -- a labeled convenience wrapper around the core fit.

No src/ edit; the sim P0 is a black box. ASCII only, numpy + stdlib only.
"""
from __future__ import annotations

from typing import List, Sequence

import numpy as np

# Reuse the VERIFIED reference cores -- do NOT reimplement these here.
from scripts.platformkit.eval_gate.ingame_blend import (  # noqa: E402
    WeightSurface,
    blend,
    blended_predictions,
    exp_smooth,
    fit_weight_surface,
    margin_bucket,
    time_bucket,
)

EDGE_CLAIMED = False

# Coarse grid edges (blueprint): deliberately under-resolved to resist the
# Statsurge over-resolution trap. sec_remaining descends; |margin| ascends.
TIME_EDGES = np.array([2880.0, 2160.0, 1440.0, 720.0, 360.0, 120.0, 0.0])
MARGIN_EDGES = np.array([0.0, 3.0, 6.0, 10.0, 16.0, 25.0, 1e9])

# garbage-time defaults; tune on the FIT season only.
GT_MARGIN = 18.0
GT_SECONDS = 120.0
GT_LO, GT_HI = 0.02, 0.98

__all__ = [
    "WeightSurface", "blend", "blended_predictions", "exp_smooth",
    "fit_weight_surface", "margin_bucket", "time_bucket",
    "TIME_EDGES", "MARGIN_EDGES", "garbage_clamp", "fit_surface_on_season",
    "EDGE_CLAIMED",
]


def garbage_clamp(p: float, margin_abs: float, sec_remaining: float,
                  t_gt: float = GT_MARGIN, s_gt: float = GT_SECONDS,
                  lo: float = GT_LO, hi: float = GT_HI,
                  leader_is_home: bool = True) -> float:
    """Late-game blowout: a score/time model stays over-confident in the trailing
    team -> hard clamp to the near-deterministic outcome. Triggers ONLY when
    |margin| >= t_gt AND sec_remaining < s_gt; otherwise returns p unchanged."""
    if margin_abs >= t_gt and sec_remaining < s_gt:
        return hi if leader_is_home else lo
    return min(1.0, max(0.0, p))


def fit_surface_on_season(states: List[dict], min_cell: int = 20) -> WeightSurface:
    """Fit the weight surface on ONE season's states only (fit_season).

    states: dicts with keys p0, p_live, seconds_remaining, score_diff, outcome.
    Delegates to the verified eval_gate fit (per-cell Brier-minimizing w, sparse
    cells fall back to the default = trust P0). Kept as a named wrapper so the
    leak-free harness reads as fit-on-A / eval-on-B.
    """
    return fit_weight_surface(states, min_cell=min_cell)


def grid_monotone_score(surf: WeightSurface) -> float:
    """Fraction of adjacent grid steps that are non-decreasing toward late/large
    margin (a coarse sanity check, NOT a fitted target). Higher is more monotone.
    Returns 1.0 when too few cells are populated to judge."""
    keys = surf.grid
    if len(keys) < 2:
        return 1.0
    ok = total = 0
    for (t, m), w in keys.items():
        for nt, nm in ((t + 1, m), (t, m + 1)):
            if (nt, nm) in keys:
                total += 1
                if keys[(nt, nm)] >= w - 1e-9:
                    ok += 1
    return 1.0 if total == 0 else ok / total
