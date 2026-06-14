"""domains.mlb.asof_sp_form_eval — CLI validation harness for EW SP-form features.

Validates EW SP-form lift vs solo-Elo on the real MLB corpus.
Loads games + SP-form features, joins with leak-free Elo (walk_forward_elo),
runs a time-split logistic (first 70% train / last 30% score), and prints:
  - Brier score  (lower is better)
  - Log-loss
  - Expected Calibration Error (ECE, 10 bins)
for solo-Elo vs (elo_logit + standardized sp_first6_diff_ew).
Reports coverage (% rows with both SPs >= MIN_PRIOR_STARTS prior starts).

Usage:
  python -m domains.mlb.asof_sp_form_eval [--alpha ALPHA] [--min-starts N]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from domains.mlb.asof_sp_form import (
    build_sp_form_features,
    EW_ALPHA as _DEFAULT_EW_ALPHA,
    MIN_PRIOR_STARTS as _DEFAULT_MIN_PRIOR_STARTS,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -30, 30)))


def _logloss(y_true: np.ndarray, y_prob: np.ndarray, eps: float = 1e-7) -> float:
    p = np.clip(y_prob, eps, 1.0 - eps)
    return float(-np.mean(y_true * np.log(p) + (1.0 - y_true) * np.log(1.0 - p)))


def _brier(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    return float(np.mean((y_prob - y_true) ** 2))


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        ece += mask.sum() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece / len(y_true))


# ---------------------------------------------------------------------------
# Logistic calibration helpers
# ---------------------------------------------------------------------------

def _fit_logistic_1d(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
) -> np.ndarray:
    """Fit w*X + b via scipy minimize_scalar on w (grid + refine), then b."""
    from scipy.optimize import minimize_scalar

    def _nll_b(b: float) -> float:
        p = _sigmoid(X_tr + b)
        return _logloss(y_tr, p)

    res_b = minimize_scalar(_nll_b, bounds=(-2, 2), method="bounded")
    b = float(res_b.x)

    def _nll_w(w: float) -> float:
        p = _sigmoid(w * X_tr + b)
        return _logloss(y_tr, p)

    res_w = minimize_scalar(_nll_w, bounds=(0.1, 5.0), method="bounded")
    w = float(res_w.x)
    return _sigmoid(w * X_te + b)


def _fit_logistic_2d(
    X1_tr: np.ndarray,
    X2_tr: np.ndarray,
    y_tr: np.ndarray,
    X1_te: np.ndarray,
    X2_te: np.ndarray,
) -> np.ndarray:
    """Fit w1*X1 + w2*X2 + b via L-BFGS-B (scipy.optimize.minimize)."""
    from scipy.optimize import minimize

    def _nll(params: np.ndarray) -> float:
        w1, w2, b = params
        logit = w1 * X1_tr + w2 * X2_tr + b
        p = _sigmoid(logit)
        return _logloss(y_tr, p)

    res = minimize(
        _nll,
        x0=np.array([1.0, 0.1, 0.0]),
        method="L-BFGS-B",
        bounds=[(0.0, 10.0), (-5.0, 5.0), (-3.0, 3.0)],
    )
    w1, w2, b = res.x
    logit_te = w1 * X1_te + w2 * X2_te + b
    return _sigmoid(logit_te)


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI: validate EW SP-form lift vs solo-Elo on the real MLB corpus."""
    ap = argparse.ArgumentParser(
        description="Validate EW SP form vs solo-Elo on MLB corpus"
    )
    ap.add_argument(
        "--alpha", type=float, default=_DEFAULT_EW_ALPHA,
        help=f"EW alpha (default {_DEFAULT_EW_ALPHA})",
    )
    ap.add_argument(
        "--min-starts", type=int, default=_DEFAULT_MIN_PRIOR_STARTS,
        help=f"Min prior starts to emit feature (default {_DEFAULT_MIN_PRIOR_STARTS})",
    )
    args = ap.parse_args()

    ew_alpha = args.alpha
    min_starts = args.min_starts

    from domains.mlb.ratings import walk_forward_elo
    from scipy.special import logit as _logit

    print("Loading games.parquet ...")
    games_path = _REPO_ROOT / "data/domains/mlb/games.parquet"
    games_df = pd.read_parquet(str(games_path))
    print(f"  {len(games_df):,} games loaded")

    print("Building EW SP-form features (walk-forward) ...")
    sp_feat = build_sp_form_features(games=games_df)
    print(f"  {len(sp_feat):,} rows generated")

    print("Computing leak-free Elo ...")
    elo_df = walk_forward_elo(games_df)
    print(f"  {len(elo_df):,} rows with Elo")

    # Merge everything; elo_df already sorted chronologically by walk_forward_elo
    merged = elo_df.merge(
        sp_feat[["event_id", "sp_first6_diff_ew",
                 "home_sp_starts_prior", "away_sp_starts_prior"]],
        on="event_id",
        how="left",
    )
    merged = merged[merged["target_home_win"].notna()].reset_index(drop=True)
    n_total = len(merged)

    # Coverage
    both_ok = (
        (merged["home_sp_starts_prior"] >= min_starts) &
        (merged["away_sp_starts_prior"] >= min_starts)
    )
    cov_pct = both_ok.mean() * 100.0
    print(
        f"\nCoverage: {both_ok.sum():,}/{n_total:,} rows have both SPs "
        f">= {min_starts} prior starts ({cov_pct:.1f}%)"
    )

    # Time split: first 70% = train, last 30% = test
    split = int(n_total * 0.70)
    train = merged.iloc[:split]
    test = merged.iloc[split:]
    print(f"Train: {len(train):,}  |  Test: {len(test):,}")

    y_test = test["target_home_win"].values.astype(float)
    y_train = train["target_home_win"].values.astype(float)

    # ---- Model A: solo-Elo (Platt-scale on train, apply on test) ----
    p_elo_train = train["p_home_elo"].values.astype(float)
    p_elo_test = test["p_home_elo"].values.astype(float)
    logit_elo_train = _logit(np.clip(p_elo_train, 1e-7, 1.0 - 1e-7))
    logit_elo_test = _logit(np.clip(p_elo_test, 1e-7, 1.0 - 1e-7))

    p_elo_cal = _fit_logistic_1d(logit_elo_train, y_train, logit_elo_test)

    brier_elo = _brier(y_test, p_elo_cal)
    ll_elo = _logloss(y_test, p_elo_cal)
    ece_elo = _ece(y_test, p_elo_cal)

    # ---- Model B: Elo + SP form (2-feature logistic) ----
    sp_train = train["sp_first6_diff_ew"].values.astype(float)
    sp_test = test["sp_first6_diff_ew"].values.astype(float)

    # Standardise on train stats
    sp_mean = float(np.nanmean(sp_train))
    sp_std = max(float(np.nanstd(sp_train)), 1e-8)
    sp_train_z = (sp_train - sp_mean) / sp_std
    sp_test_z = (sp_test - sp_mean) / sp_std

    # Replace NaN with 0 (neutral signal for rows without SP data)
    sp_train_z = np.where(np.isnan(sp_train_z), 0.0, sp_train_z)
    sp_test_z = np.where(np.isnan(sp_test_z), 0.0, sp_test_z)

    p_combo = _fit_logistic_2d(
        logit_elo_train, sp_train_z, y_train,
        logit_elo_test, sp_test_z,
    )

    brier_combo = _brier(y_test, p_combo)
    ll_combo = _logloss(y_test, p_combo)
    ece_combo = _ece(y_test, p_combo)

    # ---- Print comparison ----
    print("\n" + "=" * 62)
    print(f"{'Metric':<20}  {'Solo-Elo':>10}  {'Elo+SP-form':>12}  {'Delta':>8}")
    print("-" * 62)
    print(
        f"{'Brier':<20}  {brier_elo:>10.5f}  {brier_combo:>12.5f}  "
        f"{brier_combo - brier_elo:>+8.5f}"
    )
    print(
        f"{'Log-loss':<20}  {ll_elo:>10.5f}  {ll_combo:>12.5f}  "
        f"{ll_combo - ll_elo:>+8.5f}"
    )
    print(
        f"{'ECE (10 bins)':<20}  {ece_elo:>10.5f}  {ece_combo:>12.5f}  "
        f"{ece_combo - ece_elo:>+8.5f}"
    )
    print("=" * 62)
    print(f"N test: {len(y_test):,}  |  EW alpha={ew_alpha}  min_starts={min_starts}")
    print()

    # Honest verdict
    brier_delta = brier_combo - brier_elo
    ece_delta = ece_combo - ece_elo
    if brier_delta < -0.0005 and ece_delta <= 0.0005:
        verdict = (
            "SP-form (EW first-6 RA) IMPROVES Brier vs solo-Elo. "
            "Accuracy/calibration gain — not a betting edge."
        )
    elif brier_delta > 0.0005:
        verdict = (
            "SP-form HURTS or is NULL vs solo-Elo. "
            "Feature adds noise — do not add to production model."
        )
    else:
        verdict = (
            "SP-form is approximately NEUTRAL vs solo-Elo (delta < 0.0005). "
            "No meaningful accuracy gain — honest null result."
        )

    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
