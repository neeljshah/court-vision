"""domains.soccer.rho_fit — Leak-free Dixon-Coles rho (low-score correction) fitter.

Fits the DC correlation parameter rho in [-0.2, 0.0] walk-forward (strictly prior-only).
Core logic only: tau, NLL, fit_rho, walk_forward_rho.

Evaluation / CLI harness lives in domains.soccer.rho_fit_eval.

HONEST: rho redistributes probability mass within the low-score zone (0-0, 0-1, 1-0, 1-1).
Expected win: better 1X2 / draw / correct-score calibration. NO edge claimed.

INVARIANTS:
- Does NOT modify src/, kernel/, api/, or any existing domains/soccer/*.py.
- <=300 LOC.
"""
from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
from scipy.optimize import minimize_scalar

# ---------------------------------------------------------------------------
# Dixon-Coles tau correction and log-likelihood
# ---------------------------------------------------------------------------

def tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """DC low-score correction factor for the four cells (0,0),(0,1),(1,0),(1,1).

    tau(0,0) = 1 - lam*mu*rho
    tau(0,1) = 1 + lam*rho
    tau(1,0) = 1 + mu*rho
    tau(1,1) = 1 - rho
    All other cells: 1.0

    At rho=0 all taus=1 (pure independence). rho<0 inflates 0-0 and 1-1.
    """
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    elif x == 0 and y == 1:
        return 1.0 + lam * rho
    elif x == 1 and y == 0:
        return 1.0 + mu * rho
    elif x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _poisson_log_pmf(k: int, lam: float) -> float:
    """log P(X=k) for X~Poisson(lam)."""
    return k * math.log(lam) - lam - sum(math.log(j) for j in range(1, k + 1))


def dc_neg_log_likelihood(
    rho: float,
    history: List[Tuple[float, float, int, int]],
) -> float:
    """Negative DC log-likelihood over a history of (lam_home, lam_away, fthg, ftag).

    Minimizing this (negated) maximises the DC likelihood.
    Returns +inf if any tau factor is non-positive (invalid rho for that data).
    """
    nll = 0.0
    for lam_h, lam_a, h, a in history:
        t = tau(h, a, lam_h, lam_a, rho)
        if t <= 0.0:
            return float("inf")
        nll -= math.log(t) + _poisson_log_pmf(h, lam_h) + _poisson_log_pmf(a, lam_a)
    return nll


def fit_rho(
    history: List[Tuple[float, float, int, int]],
    bounds: Tuple[float, float] = (-0.2, 0.0),
) -> float:
    """Fit rho in bounds by minimising the DC negative log-likelihood.

    Parameters
    ----------
    history : list of (lam_home, lam_away, fthg, ftag)
        Strictly prior-only matches.
    bounds : (lo, hi)
        Search interval for rho; typically (-0.2, 0.0).

    Returns
    -------
    float
        Optimal rho, or 0.0 if history is empty or optimisation fails.
    """
    if not history:
        return 0.0
    result = minimize_scalar(
        dc_neg_log_likelihood,
        args=(history,),
        bounds=bounds,
        method="bounded",
    )
    return float(result.x) if result.success else 0.0


# ---------------------------------------------------------------------------
# Walk-forward rho array (leak-free)
# ---------------------------------------------------------------------------

def walk_forward_rho(
    lam_home_arr: np.ndarray,
    lam_away_arr: np.ndarray,
    fthg_arr: np.ndarray,
    ftag_arr: np.ndarray,
    *,
    refit_every: int = 300,
    bounds: Tuple[float, float] = (-0.2, 0.0),
) -> np.ndarray:
    """Compute a per-match rho using ONLY prior matches (strictly leak-free).

    For match i: rho[i] is fit on history[0..i-1]. Warmup (i < refit_every) uses rho=0.
    Rho is re-computed only every `refit_every` steps for speed; held constant between
    refits (still prior-only — the history at the refit point contains no future data).

    Parameters
    ----------
    lam_home_arr, lam_away_arr : shape (N,) pre-match Poisson lambdas
    fthg_arr, ftag_arr         : shape (N,) observed full-time goals (int)
    refit_every                : refit interval (200..500 recommended)

    Returns
    -------
    np.ndarray shape (N,) of per-match rho values
    """
    n = len(lam_home_arr)
    rho_arr = np.zeros(n, dtype=float)
    current_rho = 0.0

    for i in range(n):
        # Warmup: use rho=0
        if i < refit_every:
            rho_arr[i] = 0.0
            continue

        # Refit only at multiples of refit_every
        if i % refit_every == 0:
            history = [
                (float(lam_home_arr[j]), float(lam_away_arr[j]),
                 int(fthg_arr[j]), int(ftag_arr[j]))
                for j in range(i)  # strictly prior: 0..i-1
                if math.isfinite(float(fthg_arr[j])) and math.isfinite(float(ftag_arr[j]))
            ]
            current_rho = fit_rho(history, bounds=bounds)

        rho_arr[i] = current_rho

    return rho_arr
