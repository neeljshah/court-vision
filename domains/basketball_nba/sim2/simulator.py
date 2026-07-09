"""domains.basketball_nba.sim2.simulator -- vectorized Monte-Carlo possession
simulator for NBA v2.

From ANY game state (period, seconds-remaining-in-period, scores) plus the two
teams' as-of strength/pace terciles, alternate possessions to the final buzzer
N times and return the distribution of final margins + P(home win). Possessions
strictly alternate (home, away, home, ...) because the possession unit is
team-continuity (see possession_model). Each possession:
  * points ~ empirical PMF for the current cell (time_b, margin_b, off_t, def_t, pace_t)
  * duration ~ empirical PMF for (time_b, margin_b), truncated to the period clock
Overtime: if regulation ends tied, play 5-minute OT periods until untied.

FULLY VECTORIZED over the N sims with numpy (no per-sim Python loop): each step is
a handful of array ops, so a full-game replay of N=2000 is milliseconds. DETERMINISTIC
under `seed` (np.random.default_rng(seed)); no bare nondeterminism.

The point model accepts an optional conditioning dict SEAM (`cond`) for future
lineup/attribute conditioning; v2 ignores it (the cell is the whole state).

INVARIANTS: domains-only; <=300 LOC; ASCII; numpy only; no src/kernel imports.
Tests: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/sim2/test_simulator.py -q
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from domains.basketball_nba.sim2.possession_model import N_MARGIN, _MARGIN_EDGES
from domains.basketball_nba.sim2.pace_model import DMAX

_MARGIN_EDGES_ARR = np.array(_MARGIN_EDGES)
_MAX_STEPS = 1200          # guard: worst-case possessions from a full game (+OT)


@dataclass
class GameTerciles:
    """Per-game fixed as-of terciles (0..2). off/def are per SIDE."""
    home_off_t: int
    home_def_t: int
    away_off_t: int
    away_def_t: int
    pace_t: int


def _time_bucket_vec(period: np.ndarray, clock: np.ndarray) -> np.ndarray:
    tb = np.minimum(period - 1, 3)                      # Q1..Q3 -> 0..2, Q4 -> 3
    tb = np.where((period == 4) & (clock <= 180.0), 4, tb)
    tb = np.where(period >= 5, 5, tb)
    return tb.astype(np.intp)


def _margin_bucket_vec(off_margin: np.ndarray) -> np.ndarray:
    return np.searchsorted(_MARGIN_EDGES_ARR, off_margin, side="right").astype(np.intp)


def simulate(period: int, clock_s: float, home_score: int, away_score: int,
             ter: GameTerciles, point_cdf: np.ndarray, dur_cdf: np.ndarray,
             n: int = 2000, seed: int = 0,
             cond: Optional[dict] = None) -> np.ndarray:
    """Return an array (len n) of simulated FINAL home-minus-away margins.

    `cond` is the v3 conditioning seam (ignored in v2). `point_cdf` is
    [N_CELLS, PMAX+1], `dur_cdf` is [42, DMAX], both inclusive CDFs.
    """
    rng = np.random.default_rng(seed)
    hs = np.full(n, float(home_score))
    as_ = np.full(n, float(away_score))
    per = np.full(n, int(period), dtype=np.intp)
    clk = np.full(n, float(clock_s))
    done = np.zeros(n, dtype=bool)
    pvals = np.arange(point_cdf.shape[1])            # 0..PMAX (contribution lookup)

    for _ in range(_MAX_STEPS):
        if done.all():
            break
        for off_home in (True, False):
            act = ~done
            home_margin = hs - as_
            off_margin = home_margin if off_home else -home_margin
            tb = _time_bucket_vec(per, clk)
            mb = _margin_bucket_vec(off_margin)
            off_t = ter.home_off_t if off_home else ter.away_off_t
            def_t = ter.away_def_t if off_home else ter.home_def_t
            cell = ((((tb * N_MARGIN + mb) * 3 + off_t) * 3 + def_t) * 3 + ter.pace_t)
            dcell = tb * N_MARGIN + mb
            # points: inverse-CDF (count thresholds u meets/exceeds)
            u = rng.random(n)
            pts = (u[:, None] >= point_cdf[cell]).sum(axis=1)
            pts = np.minimum(pts, pvals[-1])
            # duration: 1 + count(u >= cdf)
            ud = rng.random(n)
            dur = 1.0 + (ud[:, None] >= dur_cdf[dcell]).sum(axis=1)
            dur = np.minimum(dur, np.maximum(clk, 1.0))
            # apply only to active sims
            add_h = np.where(act & off_home, pts, 0.0)
            add_a = np.where(act & (~off_home), pts, 0.0)
            hs += add_h
            as_ += add_a
            clk = np.where(act, clk - dur, clk)
            # period / game-end accounting
            ended = act & (clk <= 0.0)
            reg_over = ended & (per >= 4) & (hs != as_)
            done |= reg_over
            cont = ended & (~reg_over)
            per = np.where(cont, per + 1, per)
            clk = np.where(cont, np.where(per <= 4, 720.0, 300.0), clk)
    return hs - as_


def p_home_win(final_margins: np.ndarray) -> float:
    """P(home win) from simulated final margins (ties broken by OT -> ~none left)."""
    fm = final_margins
    wins = (fm > 0).sum() + 0.5 * (fm == 0).sum()
    return float(wins / len(fm))


def build_cdfs(pmodel, pacemodel):
    """Convenience: (point_cdf, dur_cdf) matrices from fitted models."""
    return pmodel.point_cdf_matrix(), pacemodel.dur_cdf_matrix()


# ---------------------------------------------------------------------------
# Scoring helpers for validation (kept here so simulator is self-contained)
# ---------------------------------------------------------------------------


def crps_ensemble(samples: np.ndarray, y: float) -> float:
    """CRPS of an empirical (ensemble) forecast vs observed y.
    CRPS = E|X-y| - 0.5 E|X-X'|; second term via the sorted-sample identity
    E|X-X'| = 2/n^2 * sum_i (2i - n + 1) * x_(i)  (i=0..n-1, x sorted)."""
    x = np.sort(samples.astype(float))
    n = len(x)
    term1 = np.mean(np.abs(x - y))
    i = np.arange(n)
    term2 = (2.0 / (n * n)) * np.sum((2 * i - n + 1) * x)
    return float(term1 - 0.5 * term2)


def crps_gaussian(mu: float, sigma: float, y: float) -> float:
    """Closed-form CRPS of N(mu,sigma) vs observed y (Gneiting & Raftery)."""
    sigma = max(float(sigma), 1e-9)
    z = (y - mu) / sigma
    cdf = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    pdf = math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return float(sigma * (z * (2.0 * cdf - 1.0) + 2.0 * pdf - 1.0 / math.sqrt(math.pi)))


def pit_value(samples: np.ndarray, y: float) -> float:
    """Probability-integral-transform: fraction of samples < y (mid-rank for ties).
    Uniform over held-out games in a bucket == honest distributional calibration."""
    s = samples.astype(float)
    below = (s < y).sum()
    equal = (s == y).sum()
    return float((below + 0.5 * equal) / len(s))


__all__ = ["GameTerciles", "simulate", "p_home_win", "build_cdfs",
           "crps_ensemble", "crps_gaussian", "pit_value"]
