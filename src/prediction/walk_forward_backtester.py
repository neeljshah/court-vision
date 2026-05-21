"""
walk_forward_backtester.py — Walk-forward cross-validation harness.

Given a model factory and a time-ordered dataset, repeatedly trains on an
expanding window and evaluates on the next fold, then reports per-fold and
aggregate holdout metrics (R², MAE).  No leakage: each train window strictly
precedes its test fold.

Public API
----------
    run_walk_forward(model_factory, X, y, dates, n_folds) -> dict
    platt_calibration_check(probs, outcomes)               -> dict
"""
from __future__ import annotations

import math
from typing import Any, Callable, List, Sequence

import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, mean_absolute_error, r2_score


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _chronological_folds(
    n: int,
    n_folds: int,
) -> List[tuple[np.ndarray, np.ndarray]]:
    """Return list of (train_indices, test_indices) in chronological order.

    Uses an expanding window: fold k trains on rows 0..split_k-1 and tests on
    rows split_k..split_{k+1}-1.  The initial train window is at least 1 row,
    and every test fold is at least 1 row.

    Args:
        n:       Total number of samples (already time-sorted).
        n_folds: Number of test folds to produce.

    Returns:
        List of (train_idx, test_idx) numpy arrays, length == n_folds.
    """
    if n_folds < 1:
        raise ValueError(f"n_folds must be >= 1, got {n_folds}")
    if n < n_folds + 1:
        raise ValueError(
            f"Dataset too small: need at least n_folds+1={n_folds+1} rows, got {n}"
        )

    # Divide the dataset into (n_folds + 1) segments; the first segment is the
    # initial training seed, and each subsequent segment is a test fold.
    segment_size = n / (n_folds + 1)
    splits: List[int] = [round(segment_size * k) for k in range(1, n_folds + 2)]
    # Ensure last split == n
    splits[-1] = n

    folds = []
    for i in range(n_folds):
        train_end = splits[i]           # exclusive upper bound for train
        test_start = splits[i]
        test_end = splits[i + 1]        # exclusive upper bound for test
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        folds.append((train_idx, test_idx))

    return folds


def _finite(val: float) -> bool:
    """Return True if val is a finite float (not nan/inf)."""
    return math.isfinite(float(val))


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def run_walk_forward(
    model_factory: Callable[[], Any],
    X: np.ndarray,
    y: np.ndarray,
    dates: Sequence,
    n_folds: int = 5,
) -> dict:
    """Walk-forward cross-validation with an expanding training window.

    For each fold k:
      - Train window: all rows with index < fold_k_start  (strictly earlier dates)
      - Test  window: the next chronological block of rows

    No future leakage: max(train_dates) < min(test_dates) is enforced for
    every fold.

    Args:
        model_factory: Zero-argument callable that returns a fresh, unfitted
                       sklearn-compatible estimator (must expose fit/predict).
        X:             Feature matrix, shape (n_samples, n_features).
                       Must be sorted chronologically before calling.
        y:             Target vector, shape (n_samples,).
        dates:         Sequence of date-like objects aligned with X rows.
                       Used only for leakage verification.
        n_folds:       Number of test folds (default 5).

    Returns:
        dict with keys:
          ``folds``     – list of per-fold dicts each containing
                         {fold, train_size, test_size, r2, mae,
                          max_train_date, min_test_date}
          ``aggregate`` – {r2, mae} computed over all held-out predictions

    Raises:
        ValueError: if dataset is too small for the requested number of folds.
        AssertionError: if chronological ordering is violated.
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    dates_arr = np.asarray(dates)

    n = len(y)
    fold_specs = _chronological_folds(n, n_folds)

    fold_results: List[dict] = []
    all_y_true: List[np.ndarray] = []
    all_y_pred: List[np.ndarray] = []

    for fold_idx, (train_idx, test_idx) in enumerate(fold_specs):
        # --- leakage guard ------------------------------------------------
        max_train_date = dates_arr[train_idx[-1]]
        min_test_date = dates_arr[test_idx[0]]
        assert max_train_date < min_test_date, (
            f"Fold {fold_idx}: leakage detected — "
            f"max train date {max_train_date} >= min test date {min_test_date}"
        )

        # --- fit + predict ------------------------------------------------
        model = model_factory()
        model.fit(X[train_idx], y[train_idx])
        y_pred = model.predict(X[test_idx])
        y_true = y[test_idx]

        fold_r2 = float(r2_score(y_true, y_pred))
        fold_mae = float(mean_absolute_error(y_true, y_pred))

        fold_results.append({
            "fold": fold_idx,
            "train_size": int(len(train_idx)),
            "test_size": int(len(test_idx)),
            "r2": fold_r2,
            "mae": fold_mae,
            "max_train_date": max_train_date,
            "min_test_date": min_test_date,
        })

        all_y_true.append(y_true)
        all_y_pred.append(y_pred)

    # --- aggregate metrics ------------------------------------------------
    y_true_all = np.concatenate(all_y_true)
    y_pred_all = np.concatenate(all_y_pred)
    agg_r2 = float(r2_score(y_true_all, y_pred_all))
    agg_mae = float(mean_absolute_error(y_true_all, y_pred_all))

    return {
        "folds": fold_results,
        "aggregate": {"r2": agg_r2, "mae": agg_mae},
    }


def platt_calibration_check(
    probs: Sequence[float],
    outcomes: Sequence[int],
) -> dict:
    """Fit Platt scaling and compare Brier score before and after calibration.

    Platt scaling fits a logistic regression on the raw model probabilities
    to produce calibrated probabilities.  Brier score is reported before and
    after calibration.  On well-behaved data the post-calibration Brier score
    should be <= the pre-calibration Brier score.

    Args:
        probs:    Raw model output probabilities in [0, 1], shape (n,).
        outcomes: Binary ground-truth labels (0 or 1), shape (n,).

    Returns:
        dict with keys:
          ``brier_before``  – Brier score of raw probs
          ``brier_after``   – Brier score of Platt-scaled probs
          ``calibrated_probs`` – numpy array of calibrated probabilities
          ``improved``         – True if brier_after <= brier_before
    """
    probs_arr = np.asarray(probs, dtype=float).reshape(-1, 1)
    outcomes_arr = np.asarray(outcomes, dtype=int)

    brier_before = float(brier_score_loss(outcomes_arr, probs_arr.ravel()))

    # Fit logistic regression on the raw probabilities (Platt scaling)
    platt = LogisticRegression(solver="lbfgs", max_iter=1000, C=1e6)
    platt.fit(probs_arr, outcomes_arr)
    calibrated = platt.predict_proba(probs_arr)[:, 1]

    brier_after = float(brier_score_loss(outcomes_arr, calibrated))

    return {
        "brier_before": brier_before,
        "brier_after": brier_after,
        "calibrated_probs": calibrated,
        "improved": brier_after <= brier_before,
    }
