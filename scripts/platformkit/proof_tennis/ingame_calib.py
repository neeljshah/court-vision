"""scripts.platformkit.proof_tennis.ingame_calib -- compact leak-free in-game recalibrator.

Companion to ingame_accuracy.py: ECE/reliability measurement + a leak-free TRAIN/EVAL
recalibrator (temperature OR Platt-on-logit, pure numpy) for the COMBINED in-game tennis
forecaster. The held-out preds are split chronologically into a TRAIN half (fit) and an
EVAL half (score); the recalibrator is fit on TRAIN ONLY and applied to EVAL -- it is NEVER
refit on the eval split. Method is chosen by TRAIN log-loss (no EVAL labels touched).

CALIBRATION != EDGE: better-calibrated probabilities do NOT imply beating a market close.
Brier/ECE-graded; markets efficient; no $ edge. <=300 LOC.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

_EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    pc = np.clip(p, _EPS, 1 - _EPS)
    return np.log(pc / (1 - pc))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return np.where(z >= 0, 1.0 / (1.0 + np.exp(-z)), np.exp(z) / (1.0 + np.exp(z)))


def _brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def ece10(p: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    """10-bin expected calibration error."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    n = len(p)
    if n == 0:
        return 0.0
    e = 0.0
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        m = (p >= lo) & (p < hi) if i < bins - 1 else (p >= lo) & (p <= hi)
        k = int(m.sum())
        if k:
            e += (k / n) * abs(float(y[m].mean()) - float(p[m].mean()))
    return float(e)


def reliability_slope(p: np.ndarray, y: np.ndarray) -> float:
    """OLS slope of outcome on logit(p); 1.0 = calibrated, <1 = over-confident."""
    x = _logit(p)
    if np.ptp(x) < 1e-9:
        return float("nan")
    A = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return float(coef[1])


def _fit_temperature(p: np.ndarray, y: np.ndarray) -> float:
    """Scalar T minimizing train log-loss on logit(p)/T (grid + golden section)."""
    z = _logit(p)

    def loss(t: float) -> float:
        if t <= 0:
            return float("inf")
        c = np.clip(_sigmoid(z / t), _EPS, 1 - _EPS)
        return float(np.mean(-(y * np.log(c) + (1 - y) * np.log(1 - c))))

    grid = np.linspace(0.2, 5.0, 40)
    bi = int(np.argmin([loss(t) for t in grid]))
    lo, hi = grid[max(0, bi - 1)], grid[min(len(grid) - 1, bi + 1)]
    phi = (np.sqrt(5.0) - 1.0) / 2.0
    for _ in range(40):
        if hi - lo < 1e-7:
            break
        t1, t2 = hi - phi * (hi - lo), lo + phi * (hi - lo)
        if loss(t1) < loss(t2):
            hi = t2
        else:
            lo = t1
    return 0.5 * (lo + hi)


def _fit_platt(p: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """Platt on logit: y ~ sigmoid(a*logit(p)+b) via Newton-IRLS. Returns (a, b)."""
    z = _logit(p)
    X = np.column_stack([z, np.ones_like(z)])
    w = np.array([1.0, 0.0])
    for _ in range(25):
        mu = np.clip(_sigmoid(X @ w), _EPS, 1 - _EPS)
        grad = X.T @ (mu - y)
        H = (X.T * (mu * (1 - mu))) @ X + 1e-6 * np.eye(2)
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w -= step
        if np.linalg.norm(step) < 1e-9:
            break
    return float(w[0]), float(w[1])


def recalibrate_holdout(p: np.ndarray, y: np.ndarray) -> Dict:
    """Leak-free recal: split the chronological held-out preds into TRAIN/EVAL halves.

    Fit temperature AND Platt on the TRAIN half ONLY; pick the lower-TRAIN-log-loss method
    (selection never touches EVAL labels). Apply to EVAL; report ECE_raw -> ECE_recal +
    reliability slope + Brier on EVAL. The recalibrator is NEVER refit on the eval split.
    """
    n = len(p)
    cut = n // 2
    p_tr, y_tr = p[:cut], y[:cut]
    p_ev, y_ev = p[cut:], y[cut:]

    def _ll(probs: np.ndarray, yy: np.ndarray) -> float:
        c = np.clip(probs, _EPS, 1 - _EPS)
        return float(np.mean(-(yy * np.log(c) + (1 - yy) * np.log(1 - c))))

    T = _fit_temperature(p_tr, y_tr)
    a, b = _fit_platt(p_tr, y_tr)
    temp_tr = _sigmoid(_logit(p_tr) / T)
    platt_tr = _sigmoid(a * _logit(p_tr) + b)
    method = "temperature" if _ll(temp_tr, y_tr) <= _ll(platt_tr, y_tr) else "platt"

    if method == "temperature":
        p_ev_recal = _sigmoid(_logit(p_ev) / T)
        params: Dict = {"T": round(T, 4)}
    else:
        p_ev_recal = _sigmoid(a * _logit(p_ev) + b)
        params = {"a": round(a, 4), "b": round(b, 4)}

    return {
        "n_eval": int(len(p_ev)),
        "recal_method": method,
        "recal_params": params,
        "ece_raw": round(ece10(p_ev, y_ev), 5),
        "ece_recal": round(ece10(p_ev_recal, y_ev), 5),
        "reliability_slope": round(reliability_slope(p_ev, y_ev), 4),
        "brier_raw": round(_brier(p_ev, y_ev), 5),
        "brier_recal": round(_brier(p_ev_recal, y_ev), 5),
    }
