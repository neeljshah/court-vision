"""scripts.platformkit.live_edge.joint_dist.joint -- JOINT-DIST lane: does a
GPU-fit JOINT predictive distribution over a player's correlated count stats
(pts/reb/ast) beat an INDEPENDENCE baseline (product of the tier-1 validated
per-stat empirical-quantile marginals) on the joint outcome, OOS?

Books price same-game-parlay (SGP) legs assuming independence. If a player's
stats are genuinely correlated (a big-minutes night lifts several at once),
independence over-multiplies away real joint mass -- an SGP calibration gap
(bet_map: sgp.player_legs, flagged uncovered).

Model: Gaussian copula. Marginals are the SAME validated empirical-quantile
fit tail_calib.calib already uses per stat (reuse, not reimplement). The
dependence structure is a per-entity correlation matrix over probit-
transformed marginal PIT values (league -> entity shrinkage, same James-Stein
pattern as tails.py), FIT ON GPU (torch.corrcoef on cuda tensors). Both the
copula (joint) and independence (corr=I) predictive distributions are sampled
via GPU Cholesky-correlated normals -> per-stat inverse-marginal transform,
then scored with the energy score (multivariate CRPS analog) and a concrete
SGP-shaped joint-threshold event.

Pure compute module. No ledger writes. Imports tails.py / tail_calib.calib
read-only (never edits).

INVARIANTS: pandas/numpy/scipy/torch only. <=300 LOC. ASCII stdout.
Never writes data/registry/. No $/edge claims -- calibration language only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from scipy import stats as sps

from scripts.platformkit.live_edge import tails as tl
from scripts.platformkit.live_edge.tail_calib import calib as tc

STAT_COLS_DEFAULT = ["pts", "reb", "ast"]
EPS = 1e-4
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def device_string() -> str:
    if torch.cuda.is_available():
        return f"cuda:{torch.cuda.get_device_name(0)}"
    return "cpu (no cuda visible -- fallback, not silent)"


def fit_marginals(discovery: pd.DataFrame, entity_col: str,
                   stat_cols: list[str]) -> dict[str, dict]:
    """Per-stat empirical-quantile marginals -- the tier-1 incumbent, reused
    verbatim (tc.fit_predictors == tl.compute_tail_metrics)."""
    return {s: tc.fit_predictors(discovery, entity_col, s) for s in stat_cols}


def _pit_column(df: pd.DataFrame, entity_col: str, stat_col: str,
                 metrics: dict) -> np.ndarray:
    """Per-row PIT under the entity's own fitted marginal (tc.tail_aware_cdf),
    vectorized per entity group (not row-by-row apply)."""
    out = np.full(len(df), np.nan)
    pos = pd.Series(np.arange(len(df)), index=df.index)
    for e, g in df.groupby(entity_col, observed=True):
        m = metrics.get(e)
        if m is None or m.get("insufficient"):
            continue
        vals = g[stat_col].to_numpy(dtype=float)
        pit = np.array([tc.tail_aware_cdf(x, m["quantiles"]) for x in vals])
        out[pos.loc[g.index].to_numpy()] = pit
    return out


def fit_dependence(discovery: pd.DataFrame, entity_col: str, stat_cols: list[str],
                    marginals: dict[str, dict], device: str = DEVICE
                    ) -> tuple[dict, np.ndarray]:
    """GPU step: probit-transform each stat's PIT to a normal score, then fit
    the correlation matrix on cuda tensors (torch.corrcoef). League-pooled
    correlation + per-entity correlation shrunk toward it (w = n/(n+K_SHRINK),
    same shrinkage constant tails.py uses for tail moments)."""
    z_cols = []
    for s in stat_cols:
        pit = _pit_column(discovery, entity_col, s, marginals[s])
        z_cols.append(sps.norm.ppf(np.clip(pit, EPS, 1 - EPS)))
    Z = np.column_stack(z_cols)
    valid = ~np.isnan(Z).any(axis=1)
    entities = discovery[entity_col].to_numpy()[valid]
    Zv = torch.tensor(Z[valid], dtype=torch.float32, device=device)

    pooled_corr = torch.corrcoef(Zv.T).cpu().numpy()
    pooled_corr = np.nan_to_num(pooled_corr, nan=0.0)
    np.fill_diagonal(pooled_corr, 1.0)

    out: dict = {}
    idx_by_entity = pd.Series(np.arange(len(entities))).groupby(entities, observed=True).groups
    for e, idx in idx_by_entity.items():
        rows = Zv[np.asarray(idx)]
        n = rows.shape[0]
        if n < 5:
            out[e] = {"corr": pooled_corr, "n": n}
            continue
        raw = torch.corrcoef(rows.T).cpu().numpy()
        raw = np.nan_to_num(raw, nan=0.0)
        np.fill_diagonal(raw, 1.0)
        w = n / (n + tl.K_SHRINK)
        shrunk = w * raw + (1 - w) * pooled_corr
        np.fill_diagonal(shrunk, 1.0)
        out[e] = {"corr": shrunk, "n": n}
    return out, pooled_corr


def sample_cloud(entity_id, dep: dict, marginals: dict[str, dict], stat_cols: list[str],
                  n_samples: int, device: str, seed: int, independence: bool) -> np.ndarray:
    """GPU step: n_samples draws from the joint (Cholesky-correlated) or
    independence (corr=I) predictive distribution, mapped back to physical
    units via each stat's own inverse-marginal quantile function. Returns a
    CPU numpy array (n_samples x len(stat_cols)) -- the interp step is a
    13-point lookup, not worth a GPU kernel."""
    k = len(stat_cols)
    corr = np.eye(k) if independence else dep.get(entity_id, {}).get("corr", np.eye(k))
    gen = torch.Generator(device=device).manual_seed(seed)
    C = torch.tensor(corr, dtype=torch.float32, device=device) + 1e-6 * torch.eye(k, device=device)
    L = torch.linalg.cholesky(C)
    z = torch.randn(n_samples, k, generator=gen, device=device) @ L.T
    u = (0.5 * (1 + torch.erf(z / np.sqrt(2)))).clamp(EPS, 1 - EPS).cpu().numpy()
    samples = np.empty((n_samples, k))
    for i, s in enumerate(stat_cols):
        m = marginals[s].get(entity_id)
        qs = sorted(float(q) for q in m["quantiles"])
        vs = [m["quantiles"][str(q)] for q in qs]
        samples[:, i] = np.interp(u[:, i], qs, vs)
    return samples


def energy_scores(samples: np.ndarray, actual: np.ndarray, device: str) -> np.ndarray:
    """GPU step: energy score ES(F,y) = E||X-y|| - 0.5*E||X-X'|| (multivariate
    CRPS analog). The spread term is fixed per sample cloud (computed once);
    the data term is vectorized over ALL actual rows for this entity at once
    via a single torch.cdist call -- O(n_samples^2 + n_samples*n_games), not
    O(n_games) separate resamples."""
    X = torch.tensor(samples, dtype=torch.float32, device=device)
    Y = torch.tensor(actual, dtype=torch.float32, device=device)
    spread = 0.5 * torch.cdist(X, X).mean()
    data_term = torch.cdist(X, Y).mean(dim=0)  # one value per actual row
    return (data_term - spread).cpu().numpy()


def independence_event_prob(q_leg: float, n_stats: int) -> float:
    """Exact independence prediction for P(all n_stats legs each >= their own
    q_leg marginal quantile): by construction each leg has marginal
    exceedance prob (1-q_leg); independence multiplies them."""
    return (1.0 - q_leg) ** n_stats


def copula_event_prob(samples: np.ndarray, thresholds: np.ndarray) -> float:
    """Joint-model prediction for the same event: MC fraction of the sample
    cloud exceeding ALL thresholds simultaneously."""
    return float(np.mean(np.all(samples >= thresholds[None, :], axis=1)))


def leg_thresholds(entity_id, marginals: dict[str, dict], stat_cols: list[str], q_leg: float) -> np.ndarray:
    return np.array([tc.tail_aware_ppf(q_leg, marginals[s][entity_id]["quantiles"]) for s in stat_cols])
