"""FIXTURE-ANCHOR PREDICTOR -- a tiny within-window calibrated forecaster for the
SYNTHETIC golden set; NOT the production model. The real --corpus path swaps in
proof_nba.ml_accuracy via run_gate._load_model_predictor().

Self-contained (numpy + stdlib, ASCII only). This is THE deterministic, leak-free,
within-window predictor the --golden path uses end-to-end with NO real data and NO
proof_nba import.

LEAK-FREE + WITHIN-WINDOW design:
  - The walk_forward harness hands ONLY the leak-free train set (expanding window,
    purge/embargo applied). We use train freely; we NEVER read test_state["outcome"],
    test_state["devig_close_prob"], or test_state["truth_wp"]. We MAY read
    test_state["features"] (vintage-guaranteed available < state_ts by schema).
  - PRIMARY ESTIMATOR: a SHRUNK in-window ridge logistic (Newton/IRLS) on the 3
    numeric features, fit on train ONLY. Pure linear algebra -> identical output every
    run (no np.random anywhere here; any RNG lives ONLY in the golden builder).
  - FALLBACK: a Beta(1,1)-shrunk running base rate when train is too small / one-class.
  - The fitted p is SHRUNK toward the running base rate by a fixed factor so the
    predictor is well-calibrated-ish but CANNOT beat the near-oracle synthetic close
    -> the HONEST MATCHES_CLOSE / BEHIND verdict + BSS <= 0. Deliberate, not a failure.
"""
from __future__ import annotations
from typing import Callable, Dict, List
import numpy as np

FEATURES = ("strength", "rest", "home_edge")
MIN_FIT = 15            # below this, fall back to the shrunk running base rate
RIDGE_LAMBDA = 1.0      # in-window regularization (deterministic; no RNG)
MAX_ITERS = 25
SHRINK = 0.85           # p = SHRINK * p_fit + (1 - SHRINK) * base
CLIP_LO, CLIP_HI = 0.02, 0.98


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + np.exp(-z))
    e = np.exp(z)
    return e / (1.0 + e)


def _running_base(y_tr: List[int]) -> float:
    """Beta(1,1)-style shrink to 0.5; empty train -> 0.5."""
    n = len(y_tr)
    return (float(sum(y_tr)) + 2.0 * 0.5) / (n + 2.0)


def _fit_ridge_logistic(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Tiny deterministic Newton/IRLS logistic with ridge (lambda on non-intercept).

    Design matrix already carries an intercept column at index 0. Returns weight
    vector w. Pure linear algebra -> reproducible for the frozen fixture.
    """
    n, d = X.shape
    w = np.zeros(d, dtype=float)
    reg = RIDGE_LAMBDA * np.eye(d)
    reg[0, 0] = 0.0                                   # do not penalize the intercept
    for _ in range(MAX_ITERS):
        z = X @ w
        p = 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))
        Wd = p * (1.0 - p) + 1e-9                     # IRLS weights (stabilized)
        grad = X.T @ (p - y) + reg @ w
        H = (X * Wd[:, None]).T @ X + reg
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w_new = w - step
        if not np.all(np.isfinite(w_new)):
            break
        if np.max(np.abs(w_new - w)) < 1e-8:
            w = w_new
            break
        w = w_new
    return w


def _x_row(state: dict) -> List[float]:
    f = state["features"]
    return [1.0] + [float(f[k]) for k in FEATURES]   # intercept + 3 features


def offline_predict_fn(train_states: List[dict], test_state: dict,
                       select_inside: bool) -> float:
    """Signature matches walk_forward: -> float in [0,1].

    select_inside MUST be True (the predictor selects/fits ONLY inside the window).
    If a caller passes False the predictor still runs, but run_gate flags the run as
    failed per the feature-selection-inside-window invariant.
    """
    assert select_inside is True, "offline_predict_fn selects/fits ONLY inside the window"
    y_tr = [int(s["outcome"]) for s in train_states]
    base = _running_base(y_tr)
    n = len(train_states)
    single_class = (sum(y_tr) == 0 or sum(y_tr) == n) if n else True
    if n < MIN_FIT or single_class:
        p = base                                      # shrunk running base rate
    else:
        X = np.array([_x_row(s) for s in train_states], dtype=float)
        y = np.array(y_tr, dtype=float)
        w = _fit_ridge_logistic(X, y)
        p_fit = _sigmoid(float(np.dot(w, np.array(_x_row(test_state), dtype=float))))
        p = SHRINK * p_fit + (1.0 - SHRINK) * base    # shrink toward base rate
    p = min(CLIP_HI, max(CLIP_LO, float(p)))
    return p


def degraded_predict_fn(bias: float = 0.25) -> Callable[[List[dict], dict, bool], float]:
    """Factory used by test_gate's regression test. Adds a deterministic pull toward
    0.5 (worsening Brier vs the honest predictor) so the gate's regression rule fires.
    """
    def _fn(train_states: List[dict], test_state: dict, select_inside: bool) -> float:
        p = offline_predict_fn(train_states, test_state, select_inside)
        p_deg = (1.0 - bias) * p + bias * 0.5         # deterministic pull toward 0.5
        return min(CLIP_HI, max(CLIP_LO, float(p_deg)))
    return _fn
