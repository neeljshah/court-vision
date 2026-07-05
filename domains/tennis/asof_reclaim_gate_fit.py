"""domains.tennis.asof_reclaim_gate_fit -- inlined logistic-fit helpers for the
ATP as-of reclaim gate (domains.tennis.asof_reclaim_gate).

Split out for LOC-discipline (<=300 LOC/file rule).  F5-clean: numpy/scipy only,
mirrors the identical inlined helpers in domains.tennis.asof_hold_wta_gate (no
cross-domain import; each domain gate keeps its own copy by design).

ACCURACY ONLY -- NO MARKET EDGE CLAIMED.
"""
from __future__ import annotations

from typing import Tuple

import numpy as np


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-7, 1 - 1e-7)
    return np.log(p / (1.0 - p))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def platt_fit(z: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """1-feature Platt scaling: p = sigmoid(w*z + b) via L-BFGS on the NLL."""
    from scipy.optimize import minimize

    def _nll(par: np.ndarray) -> float:
        w, b = par
        p = np.clip(sigmoid(w * z + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.0]), method="L-BFGS-B",
                    bounds=[(0.05, 10.0), (-3.0, 3.0)])
    return float(res.x[0]), float(res.x[1])


def fit_2feature(
    lz_tr: np.ndarray, fz_tr: np.ndarray, y_tr: np.ndarray,
    lz_te: np.ndarray, fz_te: np.ndarray,
) -> Tuple[np.ndarray, float]:
    """Fit p = sigmoid(w1*base_logit + w2*feat_z + b) on train; predict on test."""
    from scipy.optimize import minimize

    def _nll(par: np.ndarray) -> float:
        w1, w2, b = par
        p = np.clip(sigmoid(w1 * lz_tr + w2 * fz_tr + b), 1e-7, 1 - 1e-7)
        return float(-np.mean(y_tr * np.log(p) + (1 - y_tr) * np.log(1 - p)))

    res = minimize(_nll, x0=np.array([1.0, 0.1, 0.0]), method="L-BFGS-B",
                    bounds=[(0.05, 10), (-5, 5), (-3, 3)])
    w1, w2, b = res.x
    return sigmoid(w1 * lz_te + w2 * fz_te + b), float(w2)


__all__ = ["sigmoid", "logit", "brier", "platt_fit", "fit_2feature"]
