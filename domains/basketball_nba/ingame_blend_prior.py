"""N3 in-game blend -- P0 black-box pregame prior wrapper.

Derives P0 = P(home_margin > 0) from the EXISTING pregame Monte Carlo sim's
simulated margin distribution. The sim is consumed as a BLACK BOX: we read its
already-produced per-sim team-total arrays EXACTLY as pbp_replay.pregame_anchor
does (res.home_total, res.away_total) and never edit src/ or the sim itself.

This is the only "model" input to the blend; everything downstream conditions on
realized game state, which is NEW information the pregame close never had. The
claim is CALIBRATION, never a dollar edge. ASCII only, numpy + stdlib only.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

EDGE_CLAIMED = False  # this module makes no $-edge claim, ever


def margins_from_sim(home_total: Sequence[float], away_total: Sequence[float]) -> np.ndarray:
    """Per-sim home margin array = home_total - away_total.

    home_total / away_total are the sim's simulated per-game team totals (the
    same `res.home_total` / `res.away_total` arrays pbp_replay reads). We do not
    rerun or modify the sim; we only post-process its output distribution.
    """
    h = np.asarray(home_total, dtype=float).ravel()
    a = np.asarray(away_total, dtype=float).ravel()
    if h.shape != a.shape:
        raise ValueError("home_total and away_total must have the same shape")
    if h.size == 0:
        raise ValueError("empty sim margin distribution")
    return h - a


def derive_p0(sim_result=None, home_total: Sequence[float] = None,
              away_total: Sequence[float] = None) -> float:
    """P0 = P(home_margin > 0) from the black-box sim margin distribution.

    Accepts either a sim-result object exposing .home_total / .away_total (as
    simulate_game_fast returns and pbp_replay consumes) OR the two arrays
    directly (used by tests / replay tables). Ties (margin == 0) count as half,
    so P0 is a proper probability and is monotone in the margin distribution.
    """
    if sim_result is not None:
        home_total = getattr(sim_result, "home_total")
        away_total = getattr(sim_result, "away_total")
    if home_total is None or away_total is None:
        raise ValueError("provide sim_result or both home_total and away_total")
    margins = margins_from_sim(home_total, away_total)
    wins = float(np.count_nonzero(margins > 0))
    ties = float(np.count_nonzero(margins == 0))
    p0 = (wins + 0.5 * ties) / float(margins.size)
    return float(min(1.0, max(0.0, p0)))


def proj_margin(home_total: Sequence[float], away_total: Sequence[float]) -> float:
    """Median projected home margin (the rate anchor pbp_replay reports)."""
    return float(np.median(margins_from_sim(home_total, away_total)))
