"""scripts.platformkit.live_edge.joint_dist.joint_v2 -- JOINT-EXTEND lane:
does a fatter-tailed (Student-t) copula close the realized-vs-predicted SGP
joint-tail gap that joint.py's Gaussian copula only partially captures
(JOINT_REPORT.md: realized 0.113 vs Gaussian-predicted 0.050 at q_leg=0.75)?

Reuses joint.py's marginals + per-entity correlation fit VERBATIM (same
tier-1 empirical-quantile marginals, same James-Stein-shrunk correlation).
This module ONLY adds: (1) a global Student-t copula degrees-of-freedom fit
via GPU log-likelihood grid-search (cholesky/cholesky_solve/gammaln on cuda),
(2) a correlated normal+chi2 (Student-t mixture) sample_cloud on cuda, same
contract as joint.sample_cloud. Only the scalar t.ppf/t.cdf marginal lookup
(13-point-anchor-scale, like joint.py's erf/interp step) is CPU -- the
correlated draw and the dof likelihood itself are torch/cuda.

Imports joint.py read-only (marginals/correlation/energy-score plumbing;
never edited). INVARIANTS: pandas/numpy/scipy/torch only. <=300 LOC. ASCII
stdout. Never writes data/registry/. No $/edge claims -- calibration
language only.
"""
from __future__ import annotations

import numpy as np
import torch
from scipy import stats as sps

from scripts.platformkit.live_edge.joint_dist import joint as jt

NU_GRID = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0, 20.0, 30.0, 50.0)
EPS = jt.EPS
MAX_FIT_ROWS = 20000  # ponytail: cap dof-fit likelihood sum, a subsample suffices


def _pit_matrix(discovery, entity_col: str, stat_cols: list[str], marginals: dict) -> np.ndarray:
    """PIT matrix (n x k), reusing joint.py's own per-entity PIT column
    verbatim (never reimplemented). Rows with any NaN (insufficient-entity
    marginal) dropped."""
    cols = [jt._pit_column(discovery, entity_col, s, marginals[s]) for s in stat_cols]
    U = np.column_stack(cols)
    return U[~np.isnan(U).any(axis=1)]


def _t_copula_loglik(U: np.ndarray, corr: torch.Tensor, nu: float, device: str) -> float:
    """Sum log Student-t copula density over PIT rows U, given correlation
    corr (k x k tensor) and scalar dof nu. c(u) = f_T(x;corr,nu) /
    prod_i f_t(x_i;nu), x_i = t.ppf(u_i,nu). Cholesky/cholesky_solve/gammaln
    run on cuda; only the univariate t.ppf transform is CPU (scipy)."""
    k = corr.shape[0]
    Uc = np.clip(U, EPS, 1 - EPS)
    X = torch.tensor(sps.t.ppf(Uc, df=nu), dtype=torch.float64, device=device)
    L = torch.linalg.cholesky(corr.double())
    solve = torch.cholesky_solve(X.unsqueeze(-1), L).squeeze(-1)
    quad = (X * solve).sum(dim=1)
    logdet = 2.0 * torch.log(torch.diagonal(L)).sum()
    gl = torch.special.gammaln
    nu_t = torch.tensor(float(nu), dtype=torch.float64, device=device)
    k_t = torch.tensor(float(k), dtype=torch.float64, device=device)
    log_num = (gl((nu_t + k_t) / 2) - gl(nu_t / 2) - 0.5 * k_t * torch.log(nu_t * np.pi)
               - 0.5 * logdet - 0.5 * (nu_t + k_t) * torch.log1p(quad / nu_t))
    log_den = (gl((nu_t + 1) / 2) - gl(nu_t / 2) - 0.5 * torch.log(nu_t * np.pi)
               - 0.5 * (nu_t + 1) * torch.log1p(X ** 2 / nu_t)).sum(dim=1)
    return float((log_num - log_den).sum().item())


def fit_dof(discovery, entity_col: str, stat_cols: list[str], marginals: dict,
            pooled_corr: np.ndarray, device: str, seed: int = 0) -> float:
    """Grid-search the single GLOBAL t-copula degrees-of-freedom that
    maximizes discovery log-likelihood, using joint.py's pooled correlation
    matrix as the fixed shape parameter (a single global dof, not
    per-entity -- documented simplification, see JOINT_V2_REPORT.md)."""
    U = _pit_matrix(discovery, entity_col, stat_cols, marginals)
    if len(U) > MAX_FIT_ROWS:
        rng = np.random.default_rng(seed)
        U = U[rng.choice(len(U), MAX_FIT_ROWS, replace=False)]
    corr_t = torch.tensor(pooled_corr, dtype=torch.float32, device=device)
    scores = {nu: _t_copula_loglik(U, corr_t, nu, device) for nu in NU_GRID}
    return max(scores, key=scores.get)


def sample_cloud_t(entity_id, dep: dict, marginals: dict[str, dict], stat_cols: list[str],
                    n_samples: int, device: str, seed: int, nu: float, independence: bool) -> np.ndarray:
    """Same shape/contract as joint.sample_cloud, but a correlated Student-t
    (nu dof) mixture instead of a pure Gaussian copula: correlated normal
    draw + Cholesky on cuda, scaled by an independent chi2(nu)/nu mixing
    variable, then each stat's own inverse-marginal quantile function
    (fatter joint tails than the Gaussian copula at the same correlation)."""
    k = len(stat_cols)
    corr = np.eye(k) if independence else dep.get(entity_id, {}).get("corr", np.eye(k))
    gen = torch.Generator(device=device).manual_seed(seed)
    C = torch.tensor(corr, dtype=torch.float32, device=device) + 1e-6 * torch.eye(k, device=device)
    L = torch.linalg.cholesky(C)
    z = torch.randn(n_samples, k, generator=gen, device=device) @ L.T
    rng = np.random.default_rng(seed)
    chi2 = torch.tensor(rng.chisquare(nu, size=n_samples), dtype=torch.float32, device=device)
    t_raw = (z / torch.sqrt(chi2 / nu).unsqueeze(1)).cpu().numpy()
    u = np.clip(sps.t.cdf(t_raw, df=nu), EPS, 1 - EPS)
    samples = np.empty((n_samples, k))
    for i, s in enumerate(stat_cols):
        m = marginals[s][entity_id]
        qs = sorted(float(q) for q in m["quantiles"])
        vs = [m["quantiles"][str(q)] for q in qs]
        samples[:, i] = np.interp(u[:, i], qs, vs)
    return samples
