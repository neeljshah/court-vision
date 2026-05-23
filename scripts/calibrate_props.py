"""
calibrate_props.py — Fit isotonic calibration + conformal quantiles for prop models.

Steps:
1. Load holdout predictions from prop_residuals.json (predicted vs actual per stat)
2. Fit isotonic regression (predicted -> actual) per stat -> data/models/calibration_{stat}.joblib
3. Fit split-conformal quantiles (80% and 95%) -> data/models/conformal_{stat}.json
4. Compute median bias per stat -> update data/models/prop_residuals.json schema
5. Print before/after MAE & R² per stat
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_RESIDUALS_PATH = os.path.join(_MODELS_DIR, "prop_residuals.json")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]


def _load_holdout() -> dict:
    """Load prop_residuals.json and group by stat.

    Returns {stat: {"predicted": [...], "actual": [...]}}
    """
    if not os.path.exists(_RESIDUALS_PATH):
        print(f"[calibrate] {_RESIDUALS_PATH} not found — cannot calibrate.")
        return {}

    with open(_RESIDUALS_PATH, encoding="utf-8") as f:
        records = json.load(f)

    data: dict = defaultdict(lambda: {"predicted": [], "actual": []})
    for r in records:
        stat = r.get("stat")
        pred = r.get("predicted")
        actual = r.get("actual")
        if stat in STATS and pred is not None and actual is not None:
            try:
                data[stat]["predicted"].append(float(pred))
                data[stat]["actual"].append(float(actual))
            except (TypeError, ValueError):
                pass

    return dict(data)


def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(y_true - y_pred)))


def _r2(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 0.0
    return float(1.0 - ss_res / ss_tot)


def fit_isotonic(predicted: np.ndarray, actual: np.ndarray, stat: str) -> object:
    """Fit isotonic regression mapping raw predictions -> actual values."""
    from sklearn.isotonic import IsotonicRegression

    iso = IsotonicRegression(increasing=True, out_of_bounds="clip")
    iso.fit(predicted, actual)
    return iso


def fit_conformal(predicted: np.ndarray, actual: np.ndarray, coverage: float) -> float:
    """Compute split-conformal quantile for given coverage from residuals."""
    residuals = np.abs(actual - predicted)
    n = len(residuals)
    # Conformal quantile: ceil((n+1)*coverage)/n-th quantile
    level = np.ceil((n + 1) * coverage) / n
    level = min(level, 1.0)
    return float(np.quantile(residuals, level))


def main() -> None:
    import joblib
    import datetime

    os.makedirs(_MODELS_DIR, exist_ok=True)
    holdout = _load_holdout()

    if not holdout:
        print("[calibrate] No holdout data found. Exiting.")
        return

    print(f"[calibrate] Loaded holdout data for {len(holdout)} stats")

    # Summary dict for updated prop_residuals.json schema
    bias_summary: dict = {}

    print("\n{'stat':<6} {'n':>6}  {'MAE_before':>10}  {'MAE_after':>10}  "
          "{'R2_before':>10}  {'R2_after':>10}  {'median_bias':>12}")
    print("-" * 82)

    for stat in STATS:
        if stat not in holdout:
            print(f"{stat:<6} {'no data':>76}")
            continue

        y_pred = np.array(holdout[stat]["predicted"])
        y_true = np.array(holdout[stat]["actual"])
        n = len(y_pred)

        if n < 30:
            print(f"{stat:<6} {n:>6}  (too few samples to calibrate)")
            continue

        # Split: use first 80% for fitting calibration, last 20% for evaluation
        split = int(0.8 * n)
        y_pred_fit, y_true_fit = y_pred[:split], y_true[:split]
        y_pred_eval, y_true_eval = y_pred[split:], y_true[split:]

        # Before metrics (on eval split)
        mae_before = _mae(y_true_eval, y_pred_eval)
        r2_before = _r2(y_true_eval, y_pred_eval)

        # Fit isotonic calibration on fit split
        iso = fit_isotonic(y_pred_fit, y_true_fit, stat)

        # Apply to eval split
        y_cal_eval = iso.predict(y_pred_eval)
        mae_after = _mae(y_true_eval, y_cal_eval)
        r2_after = _r2(y_true_eval, y_cal_eval)

        # Save calibration model (overwrites win-prob variant)
        calib_path = os.path.join(_MODELS_DIR, f"calibration_{stat}.joblib")
        joblib.dump(iso, calib_path)

        # Conformal quantiles (fit on full data for max coverage)
        iso_full = fit_isotonic(y_pred, y_true, stat)
        y_cal_full = iso_full.predict(y_pred)
        q80 = fit_conformal(y_cal_full, y_true, 0.80)
        q95 = fit_conformal(y_cal_full, y_true, 0.95)

        conformal_path = os.path.join(_MODELS_DIR, f"conformal_{stat}.json")
        with open(conformal_path, "w") as f:
            json.dump({
                "stat": stat,
                "q80": round(q80, 4),
                "q95": round(q95, 4),
                "n_calibration": n,
                "computed_at": datetime.datetime.now().isoformat(),
            }, f, indent=2)

        # Bias: median of (predicted - actual) on full data
        residuals = y_pred - y_true
        median_bias = float(np.median(residuals))
        mae_full = _mae(y_true, y_pred)

        bias_summary[stat] = {
            "median_bias": round(median_bias, 6),
            "mae": round(mae_full, 4),
            "n": n,
            "q80": round(q80, 4),
            "q95": round(q95, 4),
            "computed_at": datetime.datetime.now().isoformat(),
        }

        print(f"{stat:<6} {n:>6}  {mae_before:>10.4f}  {mae_after:>10.4f}  "
              f"{r2_before:>10.4f}  {r2_after:>10.4f}  {median_bias:>+12.4f}")

    # Update prop_residuals.json with summary schema (preserve raw records, add summary key)
    # Write to separate summary file to avoid bloating residuals list
    summary_path = os.path.join(_MODELS_DIR, "prop_calibration_summary.json")
    with open(summary_path, "w") as f:
        json.dump(bias_summary, f, indent=2)
    print(f"\n[calibrate] Bias summary -> {summary_path}")

    # Also write per-stat bias to a clean prop_residuals_summary.json
    # (keeps prop_residuals.json intact for future reuse)
    residuals_summary_path = os.path.join(_MODELS_DIR, "prop_residuals_summary.json")
    with open(residuals_summary_path, "w") as f:
        json.dump(bias_summary, f, indent=2)
    print(f"[calibrate] Residuals summary -> {residuals_summary_path}")

    print("\n[calibrate] Done.")
    print(f"  Calibration models: data/models/calibration_{{stat}}.joblib")
    print(f"  Conformal quantiles: data/models/conformal_{{stat}}.json")
    print(f"  Bias summary: {summary_path}")


if __name__ == "__main__":
    main()
