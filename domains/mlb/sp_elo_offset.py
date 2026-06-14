"""domains.mlb.sp_elo_offset — SP-aware Elo offset model for MLB win probability.

Model: p_home = sigmoid(elo_logit + w * z_sp)
  elo_logit = logit(p_home_elo)  (pre-game Elo win probability, already leak-free)
  z_sp      = standardised sp_first6_diff_ew (NaN → 0 = neutral)
  w         = single scalar fitted LEAK-FREE on the training window only

Interpretation: w scales how much the SP quality difference shifts the Elo-based
win probability. w > 0 means a bigger (positive) SP diff (home SP historically
allowed fewer runs) increases predicted home win probability.

Accuracy/calibration ONLY — no betting edge claimed.

LEAK CONTRACT: w is fitted on rows with date < split_date.
  Training stats (sp_std, sp_mean) also computed on train rows only.
  Test-set rows never touch the optimiser.

PURE pandas/numpy/scipy. No src.* / kernel.* imports.
PRIVATE: never tracked on the public repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EPS: float = 1e-7
_DEFAULT_TRAIN_FRAC: float = 0.50   # 50/50 time-split
_N_ECE_BINS: int = 10


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def evaluate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    n_ece_bins: int = _N_ECE_BINS,
) -> Dict[str, float]:
    """Return dict with keys 'brier', 'logloss', 'ece'.

    Parameters
    ----------
    y_true : 1-D array of 0/1 labels
    y_pred : 1-D array of predicted probabilities in (0, 1)
    n_ece_bins : number of equal-width bins for ECE
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    brier = float(np.mean((y_pred - y_true) ** 2))

    p = np.clip(y_pred, _EPS, 1.0 - _EPS)
    logloss = float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))

    bins = np.linspace(0.0, 1.0, n_ece_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_pred >= lo) & (y_pred < hi)
        n_bin = int(mask.sum())
        if n_bin == 0:
            continue
        ece += n_bin * abs(y_true[mask].mean() - y_pred[mask].mean())
    ece = float(ece / max(len(y_true), 1))

    return {"brier": brier, "logloss": logloss, "ece": ece}


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def build_merged_features(games_df: pd.DataFrame) -> pd.DataFrame:
    """Merge walk-forward Elo with leak-free EW SP-form features.

    Parameters
    ----------
    games_df : games DataFrame (columns required by walk_forward_elo + pitchers path)

    Returns
    -------
    pd.DataFrame sorted chronologically with columns:
      event_id, date, target_home_win,
      p_home_elo, elo_logit,
      sp_first6_diff_ew, home_sp_starts_prior, away_sp_starts_prior
    """
    from domains.mlb.ratings import walk_forward_elo
    from domains.mlb.asof_sp_form import build_sp_form_features

    elo_df = walk_forward_elo(games_df)

    pit_path = _REPO_ROOT / "data/domains/mlb/pitchers.parquet"
    sp_feat = build_sp_form_features(games=games_df)

    merged = elo_df.merge(
        sp_feat[[
            "event_id", "sp_first6_diff_ew",
            "home_sp_starts_prior", "away_sp_starts_prior",
        ]],
        on="event_id",
        how="left",
    )

    merged = merged[merged["target_home_win"].notna()].reset_index(drop=True)

    p_elo = np.clip(merged["p_home_elo"].values.astype(float), _EPS, 1.0 - _EPS)
    merged = merged.copy()
    merged["elo_logit"] = logit(p_elo)

    keep = [
        "event_id", "date", "target_home_win",
        "p_home_elo", "elo_logit",
        "sp_first6_diff_ew", "home_sp_starts_prior", "away_sp_starts_prior",
    ]
    return merged[keep].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Fit
# ---------------------------------------------------------------------------

def fit_sp_offset_weight(
    train_df: pd.DataFrame,
    sp_mean: Optional[float] = None,
    sp_std: Optional[float] = None,
) -> Tuple[float, float, float]:
    """Fit the SP offset weight w on training data only.

    Model: p = sigmoid(elo_logit + w * z_sp)
    z_sp = (sp_first6_diff_ew - sp_mean) / sp_std, NaN → 0.

    Optimises w via bounded scalar minimisation of mean log-loss.

    Parameters
    ----------
    train_df : DataFrame with 'elo_logit', 'sp_first6_diff_ew', 'target_home_win'
    sp_mean  : pre-computed mean (from training set); computed here if None
    sp_std   : pre-computed std (from training set); computed here if None

    Returns
    -------
    (w, sp_mean, sp_std)
    """
    sp_raw = train_df["sp_first6_diff_ew"].values.astype(float)
    if sp_mean is None:
        sp_mean = float(np.nanmean(sp_raw))
    if sp_std is None:
        sp_std = float(np.nanstd(sp_raw))
    sp_std = max(sp_std, _EPS)

    z_sp = np.where(np.isnan(sp_raw), 0.0, (sp_raw - sp_mean) / sp_std)
    elo_logit = train_df["elo_logit"].values.astype(float)
    y_true = train_df["target_home_win"].values.astype(float)

    def _nll(w: float) -> float:
        logit_pred = elo_logit + w * z_sp
        p = expit(logit_pred)
        p = np.clip(p, _EPS, 1.0 - _EPS)
        return float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))

    res = minimize_scalar(_nll, bounds=(-3.0, 3.0), method="bounded")
    w = float(res.x)
    return w, sp_mean, sp_std


# ---------------------------------------------------------------------------
# Predict
# ---------------------------------------------------------------------------

def predict_sp_elo(
    df: pd.DataFrame,
    w: float,
    sp_mean: float = 0.0,
    sp_std: float = 1.0,
) -> np.ndarray:
    """Apply the SP-aware Elo offset model to df.

    p_home = sigmoid(elo_logit + w * z_sp)
    NaN SP → z_sp = 0 (neutral, falls back to pure-Elo prediction).

    Parameters
    ----------
    df      : DataFrame with 'elo_logit' and 'sp_first6_diff_ew'
    w       : fitted SP offset weight (from fit_sp_offset_weight)
    sp_mean : training-set mean of sp_first6_diff_ew (for standardisation)
    sp_std  : training-set std  of sp_first6_diff_ew (for standardisation)

    Returns
    -------
    np.ndarray of predicted probabilities, shape (len(df),)
    """
    sp_raw = df["sp_first6_diff_ew"].values.astype(float)
    sp_std_safe = max(sp_std, _EPS)
    z_sp = np.where(np.isnan(sp_raw), 0.0, (sp_raw - sp_mean) / sp_std_safe)
    elo_logit = df["elo_logit"].values.astype(float)
    return expit(elo_logit + w * z_sp)


# ---------------------------------------------------------------------------
# Main evaluation entry point
# ---------------------------------------------------------------------------

def time_split_evaluation(
    games_df: pd.DataFrame,
    train_frac: float = _DEFAULT_TRAIN_FRAC,
) -> Dict[str, object]:
    """Leak-free time-split evaluation of SP-Elo offset vs baseline Elo.

    Steps:
      1. Build merged features (chronologically ordered).
      2. Split at train_frac (strictly chronological).
      3. Fit w on train rows ONLY.
      4. Predict on test rows.
      5. Return metrics dict (no modification of train rows after split).

    Parameters
    ----------
    games_df   : games DataFrame
    train_frac : fraction of rows to use for training (default 0.50)

    Returns
    -------
    dict with keys:
      w              — fitted SP weight
      sp_mean        — training sp_first6_diff_ew mean
      sp_std         — training sp_first6_diff_ew std
      split_date     — first date of test set (all train dates strictly before)
      n_train        — training row count
      n_test         — test row count
      coverage_pct   — % of test rows with non-NaN SP diff
      baseline        — metrics dict (Brier/logloss/ECE) for raw Elo
      sp_model        — metrics dict (Brier/logloss/ECE) for SP-Elo offset
    """
    merged = build_merged_features(games_df)
    n = len(merged)
    split_idx = max(1, int(n * train_frac))

    train_df = merged.iloc[:split_idx].reset_index(drop=True)
    test_df = merged.iloc[split_idx:].reset_index(drop=True)

    split_date = pd.to_datetime(test_df["date"].iloc[0]).date()

    w, sp_mean, sp_std = fit_sp_offset_weight(train_df)

    y_test = test_df["target_home_win"].values.astype(float)

    # Baseline: raw Elo probability
    p_baseline = np.clip(test_df["p_home_elo"].values.astype(float), _EPS, 1.0 - _EPS)
    baseline_metrics = evaluate_metrics(y_test, p_baseline)

    # SP-aware model
    p_sp = predict_sp_elo(test_df, w, sp_mean, sp_std)
    sp_metrics = evaluate_metrics(y_test, p_sp)

    sp_raw_test = test_df["sp_first6_diff_ew"].values.astype(float)
    coverage_pct = float(np.mean(~np.isnan(sp_raw_test)) * 100.0)

    return {
        "w": w,
        "sp_mean": sp_mean,
        "sp_std": sp_std,
        "split_date": split_date,
        "n_train": len(train_df),
        "n_test": len(test_df),
        "coverage_pct": coverage_pct,
        "baseline": baseline_metrics,
        "sp_model": sp_metrics,
    }
