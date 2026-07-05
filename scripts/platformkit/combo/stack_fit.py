"""scripts.platformkit.combo.stack_fit -- N-feature pregame logistic stack fitter.

Generalizes the 2-feature Newton-Raphson pattern in
proof_mlb/fusion_mlb.py:_fit_logistic and domains/mlb/asof_sp_form_eval's L-BFGS-B
2-feature fit to an arbitrary feature COUNT, for the pregame stack-family harness
(PREREG_STACK_FAMILIES_2026-07-05.md). Reused by stack_gate_pregame.py; never
imported by anything in src/ or kernel/ (falsifier-F5-style isolation).

Discipline (binding, mirrors the fusion_mlb/asof_sp_form_eval leak contract):
  * `StandardizerParams` is fit on TRAIN rows ONLY (mean/std); `standardize()`
    applies those frozen params to any split -- an eval split NEVER refits it.
  * `fit_logistic` is pure Newton-Raphson (ridge-damped Hessian), no sklearn/scipy
    dependency -- matches fusion_mlb's numerics style exactly so results are
    reproducible without an extra dependency.
  * `FitDiagnostics` records n_iter and ||w - w_init|| so a caller can PROVE the
    fit moved off its zero-initialization (PREREG L1/L3 convergence requirement)
    -- a fit that silently no-ops (w stays at init) is NOT a genuine improvement.
  * `score_with_fallback` scores a row using the CANDIDATE weights when every
    added feature is finite for that row, else falls back to the BASE probability
    -- so base and candidate are compared on the IDENTICAL row set (the fusion_mlb
    "missing SP-form falls back to Elo-only" pattern, generalized to N features).
  * `expanding_window_splits` is a plain time-ordered walk-forward helper: fixed
    initial train window, then successive test folds -- no reselection at seams.
  * `bootstrap_refit_deltas` supports the L3 seed-stability check (>=5 refits;
    p10 of the stack-vs-base delta must be >= 0): each refit re-samples TRAIN rows
    with replacement (rows only, never re-splits train/test), refits, and returns
    the held-out delta so a caller can take the p10 across refits.

Calibration, not edge. NO $ / ROI anywhere. numpy + stdlib only. ASCII; <=300 LOC.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import numpy as np

_CLIP = 1e-6
_RIDGE = 1e-4


def sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))


def logit(p: np.ndarray, eps: float = 1e-7) -> np.ndarray:
    p = np.clip(p, eps, 1.0 - eps)
    return np.log(p / (1.0 - p))


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((np.clip(p, _CLIP, 1 - _CLIP) - y) ** 2))


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, _CLIP, 1 - _CLIP)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


# --------------------------------------------------------------------------- #
# Train-only standardizer
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class StandardizerParams:
    """Per-column (mean, std) fit on TRAIN rows only; frozen and reused on eval."""

    means: np.ndarray
    stds: np.ndarray  # never zero (floored) -- division is always safe


def fit_standardizer(train_cols: np.ndarray) -> StandardizerParams:
    """Fit mean/std per column of a (n_train, k) TRAIN-ONLY feature matrix.

    NaN rows are ignored per-column (nanmean/nanstd) so a partially-missing
    added feature does not corrupt the standardizer for fully-observed columns.
    """
    means = np.nanmean(train_cols, axis=0)
    means = np.where(np.isfinite(means), means, 0.0)
    stds = np.nanstd(train_cols, axis=0)
    stds = np.where(np.isfinite(stds) & (stds > 1e-8), stds, 1.0)
    return StandardizerParams(means=means, stds=stds)


def standardize(cols: np.ndarray, params: StandardizerParams) -> np.ndarray:
    """Apply FROZEN train-fit (mean, std) to any split; NaN -> 0 (neutral) after."""
    z = (cols - params.means) / params.stds
    return np.nan_to_num(z, nan=0.0)


# --------------------------------------------------------------------------- #
# Newton-Raphson N-feature logistic (fusion_mlb._fit_logistic generalized)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class FitDiagnostics:
    """Convergence proof the fit moved off its zero-initialization (PREREG L1/L3)."""

    n_iter: int
    w_move_from_init: float  # ||w - w_init||_2
    converged: bool


@dataclass(frozen=True)
class LogisticFit:
    weights: np.ndarray  # includes intercept as weights[0] (X's first column = 1)
    diagnostics: FitDiagnostics


def fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 50,
                  tol: float = 1e-8) -> LogisticFit:
    """Newton-Raphson logistic regression on X (intercept column included).

    Ridge-damped Hessian (matches fusion_mlb._fit_logistic exactly) so a
    near-singular Hessian from a highly-collinear added feature never crashes
    the fit; it just damps the step. Returns weights + convergence diagnostics.
    """
    w_init = np.zeros(X.shape[1])
    w = w_init.copy()
    ridge = _RIDGE * np.eye(X.shape[1])
    n_iter = 0
    converged = False
    for i in range(iters):
        n_iter = i + 1
        p = sigmoid(X @ w)
        grad = X.T @ (p - y)
        wgt = p * (1 - p)
        H = X.T @ (X * wgt[:, None]) + ridge
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        w_new = w - step
        if np.max(np.abs(w_new - w)) < tol:
            w = w_new
            converged = True
            break
        w = w_new
    move = float(np.linalg.norm(w - w_init))
    return LogisticFit(weights=w, diagnostics=FitDiagnostics(
        n_iter=n_iter, w_move_from_init=move, converged=converged))


def build_design(cols: Sequence[np.ndarray]) -> np.ndarray:
    """Stack an intercept column of 1s with each feature column -> (n, 1+k) matrix."""
    n = len(cols[0]) if cols else 0
    parts = [np.ones(n)] + [np.asarray(c, dtype=float) for c in cols]
    return np.column_stack(parts)


def predict_proba(X: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return sigmoid(X @ weights)


# --------------------------------------------------------------------------- #
# Missing-feature fallback (fusion_mlb "falls back to Elo-only" pattern, N-ary)
# --------------------------------------------------------------------------- #

def score_with_fallback(added_feature_cols_raw: Sequence[np.ndarray],
                        p_base: np.ndarray, p_candidate: np.ndarray) -> np.ndarray:
    """Row-wise: use p_candidate where EVERY raw added feature is finite, else p_base.

    Guarantees base and candidate are scored on the IDENTICAL row set (the
    prereg's "rows missing an added feature fall back to the base prob" rule).
    """
    if not added_feature_cols_raw:
        return np.asarray(p_base, dtype=float)
    has_all = np.ones(len(p_base), dtype=bool)
    for col in added_feature_cols_raw:
        has_all &= np.isfinite(np.asarray(col, dtype=float))
    return np.where(has_all, p_candidate, p_base)


# --------------------------------------------------------------------------- #
# Expanding-window walk-forward split helper
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class WFSplit:
    train_idx: np.ndarray
    test_idx: np.ndarray


def expanding_window_splits(n: int, initial_train_frac: float = 0.5,
                            n_folds: int = 1) -> List[WFSplit]:
    """Time-ordered expanding-window folds: fixed initial train, growing thereafter.

    Rows are assumed ALREADY chronologically sorted by the caller (this module
    is data-agnostic; it only slices by position). `n_folds=1` reproduces the
    simple mid-split fusion_mlb/pregame_gate protocol (first half train, second
    half test). `n_folds>1` yields successive test blocks of equal size after
    the initial train window, each fold's train window EXPANDING to include all
    prior folds (no reselection at seams -- each fold's spec-fit is independent
    of later folds by construction: later folds simply never influence earlier
    ones because the earlier test block is never revisited).
    """
    if n < 2:
        return [WFSplit(train_idx=np.arange(0), test_idx=np.arange(0))]
    start = max(1, int(n * initial_train_frac))
    remaining = max(0, n - start)
    fold_size = max(1, remaining // max(1, n_folds))
    splits: List[WFSplit] = []
    cursor = start
    for f in range(max(1, n_folds)):
        end = n if f == n_folds - 1 else min(n, cursor + fold_size)
        if cursor >= n:
            break
        splits.append(WFSplit(train_idx=np.arange(0, cursor),
                              test_idx=np.arange(cursor, end)))
        cursor = end
    return splits or [WFSplit(train_idx=np.arange(start), test_idx=np.arange(start, n))]


# --------------------------------------------------------------------------- #
# Bootstrap-refit seed-stability helper (PREREG L3: >=5 refits, p10 >= 0)
# --------------------------------------------------------------------------- #

def bootstrap_refit_deltas(fit_and_score_fn, n_refits: int = 5,
                           base_seed: int = 0) -> List[float]:
    """Run `fit_and_score_fn(rng) -> float` >=5 times; return the delta list.

    `fit_and_score_fn` receives a fresh numpy Generator per refit and must
    return ONE scalar: the held-out stack-vs-base delta for that refit (e.g.
    brier_base - brier_stack, positive = stack better). The CALLER owns how the
    rng is used to bootstrap-resample train rows (with replacement) or jitter a
    fold boundary -- this helper only orchestrates the >=5-refit loop and
    collects results; PREREG L3 requires p10(deltas) >= 0 to pass, computed by
    the caller (np.percentile(deltas, 10)).
    """
    n_refits = max(5, int(n_refits))
    deltas: List[float] = []
    for i in range(n_refits):
        rng = np.random.default_rng(base_seed + i * 9973)
        deltas.append(float(fit_and_score_fn(rng)))
    return deltas


def bootstrap_resample_rows(n_train: int, rng: np.random.Generator) -> np.ndarray:
    """Row indices (0..n_train-1) resampled WITH replacement -- train rows only."""
    return rng.integers(0, n_train, size=n_train)


__all__ = [
    "sigmoid", "logit", "brier", "logloss",
    "StandardizerParams", "fit_standardizer", "standardize",
    "FitDiagnostics", "LogisticFit", "fit_logistic", "build_design", "predict_proba",
    "score_with_fallback",
    "WFSplit", "expanding_window_splits",
    "bootstrap_refit_deltas", "bootstrap_resample_rows",
]
