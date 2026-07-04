"""Situation-weighted blend: naive composite vs shooter_quality_v1.

LANE composition (mission spine 3). Pre-registered hypothesis: descriptive
intelligence (shooter_quality_v1) adds predictive value over the canonical
naive composite CONDITIONALLY, where the naive index is noisy = low
forward-visible sample. Wave-29 foundation fact: naive rho .4044 vs quality
.2680 forecasting future-30d TS% OVERALL -- naive is canonical overall; this
module builds a SITUATION-WEIGHTED blend, not a rematch of that result.

DESIGN (frozen, do not change post-hoc):
    blend = w(s) * naive_z + (1 - w(s)) * quality_z
    z-scored PER CUTOFF (mean 0 / std 1 within that cutoff's qualifying pool).
    situation feature s = log1p(FGA_to_date at cutoff)  -- ONE feature only,
        a hard cap on flexibility (this is the whole point of the gate: does
        ONE extra situational feature buy anything over the naive rematch).
    w(s) = sigmoid(c0 + c1 * s)
    c0/c1 fit on TRAIN folds ONLY, maximizing mean Spearman rho of the blend
        vs future-30d realized TS% across the TRAIN folds (leave-one-fold-out:
        for each fold left out as TEST, c0/c1 are fit on the OTHER folds only
        -- never on the fold being scored).

FIX ROUND (post Opus review): the sigmoid objective is nearly flat around
c0=c1=0 (its own midpoint), so Nelder-Mead started there with the default
tiny initial simplex terminated at the origin every time -- a no-op fit
that silently collapsed w(s) to a constant 0.5 for all s, making the
situation feature `s` inert. Fix: a coarse grid pre-search over a wide
c0/c1 range picks the best-scoring grid point as the Nelder-Mead start,
so the local optimizer is seeded off the flat plateau. A degeneracy check
logs/flags any fit that still lands on the untuned init.

Reuses domains/basketball_nba/quality_validity_gate.rank_at_cutoff for the
per-cutoff leak-free tables (naive_pctile, shooter_pctile, fga, realized_ts_pct
already computed there) -- no re-implementation of the data plumbing.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import spearmanr

logger = logging.getLogger(__name__)

# Frozen design constants -- pre-registered, do not tune post-hoc.
SITUATION_FEATURE = "fga"  # pre-T cumulative FGA already in rank_at_cutoff's table
C0_INIT, C1_INIT = 0.0, 0.0
LOW_SAMPLE_TERCILE = 0  # bottom tercile (0=bottom,1=mid,2=top) of situation feature s

# Coarse pre-search grid to escape the flat plateau around c0=c1=0 (the
# sigmoid's own midpoint) before handing off to Nelder-Mead. Range chosen
# wide enough to reach near-saturated w(s) (sigmoid(+-5) ~= 0.007/0.993)
# for the observed log1p(FGA) range (~5-8), without being unbounded.
_GRID_C0 = (-5.0, -2.0, -1.0, 0.0, 1.0, 2.0, 5.0)
_GRID_C1 = (-3.0, -1.0, -0.3, 0.0, 0.3, 1.0, 3.0)


def zscore(s: pd.Series) -> pd.Series:
    """Per-cutoff z-score; std=0 (degenerate) maps to all-zero (no info)."""
    s = s.astype(float)
    mu, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - mu) / sd


def situation_feature(table: pd.DataFrame) -> pd.Series:
    """s = log1p(FGA_to_date at cutoff); ONE feature only, per spec."""
    return np.log1p(table[SITUATION_FEATURE].astype(float))


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def blend_scores(table: pd.DataFrame, c0: float, c1: float) -> pd.Series:
    """blend = w(s)*naive_z + (1-w(s))*quality_z, all inputs from `table`
    (must carry naive_pctile, shooter_pctile, and SITUATION_FEATURE columns)."""
    naive_z = zscore(table["naive_pctile"])
    quality_z = zscore(table["shooter_pctile"])
    s = situation_feature(table)
    w = sigmoid(c0 + c1 * s.values)
    return pd.Series(w * naive_z.values + (1 - w) * quality_z.values, index=table.index)


def _neg_mean_rho(params: np.ndarray, tables: list[pd.DataFrame]) -> float:
    c0, c1 = params
    rhos = []
    for t in tables:
        blend = blend_scores(t, c0, c1)
        rho, _ = spearmanr(blend, t["realized_ts_pct"])
        if np.isfinite(rho):
            rhos.append(rho)
    if not rhos:
        return 0.0
    return -float(np.mean(rhos))


@dataclass
class FitResult:
    c0: float
    c1: float
    train_mean_rho: float


def _grid_prescan_best(train_tables: list[pd.DataFrame]) -> np.ndarray:
    """Coarse grid search over (c0, c1) to find a start point off the flat
    plateau surrounding the sigmoid's own midpoint (c0=c1=0). Returns the
    best-scoring grid point (includes the origin, so it never does worse
    than the un-seeded fit)."""
    best_x, best_val = np.array([C0_INIT, C1_INIT]), _neg_mean_rho(
        np.array([C0_INIT, C1_INIT]), train_tables
    )
    for c0, c1 in product(_GRID_C0, _GRID_C1):
        val = _neg_mean_rho(np.array([c0, c1]), train_tables)
        if val < best_val:
            best_val, best_x = val, np.array([c0, c1])
    return best_x


def fit_weight_params(train_tables: list[pd.DataFrame]) -> FitResult:
    """Fit c0, c1 on TRAIN folds ONLY by maximizing mean Spearman rho of the
    blend vs future-30d realized TS% across those folds.

    The objective (mean Spearman rho of a sigmoid-weighted blend) is nearly
    flat right at c0=c1=0 -- the sigmoid's own midpoint -- so Nelder-Mead
    seeded there with a default (tiny) initial simplex has no local signal
    to move on and terminates at the origin. A coarse grid pre-search picks
    the best-scoring (c0, c1) over a wide range as the Nelder-Mead start,
    so the local optimizer is seeded off the plateau before refining."""
    if not train_tables:
        return FitResult(c0=0.0, c1=0.0, train_mean_rho=float("nan"))
    x0 = _grid_prescan_best(train_tables)
    res = minimize(
        _neg_mean_rho, x0=x0, args=(train_tables,),
        method="Nelder-Mead",
        options={"xatol": 1e-4, "fatol": 1e-6, "maxiter": 500},
    )
    c0, c1 = float(res.x[0]), float(res.x[1])
    if np.isclose(c0, C0_INIT, atol=1e-6) and np.isclose(c1, C1_INIT, atol=1e-6):
        logger.warning(
            "fit_weight_params: fit returned the untuned init (c0=%.6f, c1=%.6f) "
            "-- degenerate no-op fit; w(s) will be a constant 0.5 for all s.",
            c0, c1,
        )
    return FitResult(c0=c0, c1=c1, train_mean_rho=float(-res.fun))


def low_sample_mask(table: pd.DataFrame, tercile: int = LOW_SAMPLE_TERCILE) -> pd.Series:
    """Pre-registered low-sample subpopulation = bottom tercile of
    FGA_to_date at each cutoff (tercile=0). Ties broken by pandas qcut
    (duplicates='drop' degrades gracefully on tiny/degenerate pools)."""
    s = table[SITUATION_FEATURE].astype(float)
    try:
        bins = pd.qcut(s, 3, labels=False, duplicates="drop")
    except ValueError:
        # not enough distinct values to form 3 bins -- no low-sample subset definable
        return pd.Series(np.zeros(len(s), dtype=bool), index=table.index)
    n_bins = int(bins.max()) + 1 if bins.notna().any() else 0
    if n_bins < 3:
        return pd.Series(np.zeros(len(s), dtype=bool), index=table.index)
    return (bins == tercile).fillna(False)


def shuffle_quality_within_cutoff(table: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """PLANTED NULL: shuffle shooter_pctile values across players WITHIN this
    cutoff (breaks the player<->quality-index link while preserving the
    marginal distribution of quality scores and every other column,
    including realized_ts_pct and the situation feature)."""
    out = table.copy()
    perm = rng.permutation(len(out))
    out["shooter_pctile"] = out["shooter_pctile"].to_numpy()[perm]
    return out
