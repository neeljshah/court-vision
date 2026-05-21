"""
fit_prop_calibration.py — One-shot script: fit isotonic calibration for all 7 prop stats.

Loads prediction+actual pairs from:
  1. data/models/prop_residuals.json  (recorded at prediction time — most accurate)
  2. data/nba/gamelogs_*.json         (fallback box scores)

Fits one IsotonicRegression per stat and persists to
  data/models/calibration_{stat}.joblib

Run after a sufficient backlog of predictions has accumulated:
  python scripts/fit_prop_calibration.py
  python scripts/fit_prop_calibration.py --ab-test

Do NOT auto-run this from the API or the pipeline.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
_NBA_DIR    = os.path.join(PROJECT_DIR, "data", "nba")

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
MIN_SAMPLES = 30   # skip stats with too few samples


def _load_residuals() -> list[dict]:
    path = os.path.join(_MODELS_DIR, "prop_residuals.json")
    if os.path.exists(path):
        try:
            data = json.load(open(path, encoding="utf-8"))
            if data:
                return data
        except Exception:
            pass

    # Fallback: gamelogs have actuals but no predictions — not usable for calibration
    print("  No prop_residuals.json found and no predicted values in gamelogs — "
          "nothing to calibrate.")
    return []


def ab_test_calibration(residuals: list[dict], holdout_frac: float = 0.2) -> dict:
    """A/B test: compare existing calibrators vs newly fitted ones on holdout data.

    Returns dict: {stat: {"old_brier": float, "new_brier": float, "promoted": bool, "n": int}}
    """
    from sklearn.isotonic import IsotonicRegression
    from sklearn.metrics import brier_score_loss
    import joblib

    results = {}
    for stat in STATS:
        rows = [r for r in residuals
                if r.get("stat") == stat
                and r.get("predicted") is not None
                and r.get("actual") is not None]

        if len(rows) < MIN_SAMPLES:
            results[stat] = {"n": len(rows), "promoted": False, "reason": "insufficient_data"}
            continue

        # Chronological split
        n_holdout = max(1, int(len(rows) * holdout_frac))
        train_rows = rows[:-n_holdout]
        test_rows = rows[-n_holdout:]

        if len(train_rows) < 10:
            results[stat] = {"n": len(rows), "promoted": False, "reason": "train_too_small"}
            continue

        # Convert to (probs, outcomes)
        def _to_prob_outcome(rr: list[dict]):
            preds = np.array([float(r["predicted"]) for r in rr])
            actuals = np.array([float(r["actual"]) for r in rr])
            lines = np.array([float(r.get("line") or r["predicted"]) for r in rr])
            std = max(preds.std(), 0.1)
            probs = 1.0 / (1.0 + np.exp(-(preds - lines) / std))
            outcomes = (actuals > lines).astype(float)
            return probs, outcomes

        train_p, train_o = _to_prob_outcome(train_rows)
        test_p, test_o = _to_prob_outcome(test_rows)

        # Fit new calibrator on train
        new_calib = IsotonicRegression(out_of_bounds="clip")
        new_calib.fit(train_p, train_o)
        new_preds = new_calib.predict(test_p)
        new_brier = float(brier_score_loss(test_o, new_preds))

        # Evaluate old calibrator on test
        old_calib_path = os.path.join(_MODELS_DIR, f"calibration_{stat}.joblib")
        old_brier = None
        if os.path.exists(old_calib_path):
            try:
                old_calib = joblib.load(old_calib_path)
                old_preds = old_calib.predict(test_p)
                old_brier = float(brier_score_loss(test_o, old_preds))
            except Exception:
                pass

        # Promote if new is better (or no old exists)
        promote = old_brier is None or new_brier < old_brier
        if promote:
            joblib.dump(new_calib, old_calib_path)

        results[stat] = {
            "n": len(rows),
            "n_train": len(train_rows),
            "n_test": len(test_rows),
            "old_brier": old_brier,
            "new_brier": round(new_brier, 6),
            "promoted": promote,
        }

    return results


def main() -> None:
    from src.prediction.prop_model_stack import CalibrationLayer, STATS as _STATS

    residuals = _load_residuals()
    if not residuals:
        print("No calibration data available. Run predictions first to accumulate residuals.")
        return

    calib = CalibrationLayer()
    for stat in _STATS:
        rows = [r for r in residuals
                if r.get("stat") == stat
                and r.get("predicted") is not None
                and r.get("actual") is not None]
        if len(rows) < MIN_SAMPLES:
            print(f"  {stat}: only {len(rows)} samples (need {MIN_SAMPLES}) — skipping")
            continue

        # Convert predictions to probabilities (sigmoid of normalised residual)
        # and outcomes to {0,1} (actual > predicted line = over = 1)
        preds   = np.array([float(r["predicted"]) for r in rows])
        actuals = np.array([float(r["actual"])     for r in rows])
        lines   = np.array([float(r.get("line") or r["predicted"]) for r in rows])

        # over_prob proxy: logistic of (pred - line) / std
        std = max(preds.std(), 0.1)
        probs    = 1.0 / (1.0 + np.exp(-(preds - lines) / std))
        outcomes = (actuals > lines).astype(float)

        calib.fit(stat, probs, outcomes)
        print(f"  {stat}: fitted on {len(rows)} samples -> "
              f"{os.path.join(_MODELS_DIR, f'calibration_{stat}.joblib')}")

    print("Calibration complete.")


if __name__ == "__main__":
    import argparse as _argparse
    _p = _argparse.ArgumentParser(description="Fit isotonic calibration for prop stats")
    _p.add_argument("--all-stats", action="store_true",
                    help="Fit calibration for all 7 stats (default behavior)")
    _p.add_argument("--stat", default=None,
                    choices=STATS, help="Fit only a specific stat")
    _p.add_argument("--min-samples", type=int, default=MIN_SAMPLES,
                    help=f"Minimum samples per stat (default: {MIN_SAMPLES})")
    _p.add_argument("--ab-test", action="store_true",
                    help="A/B test: compare old vs new calibrators; only promote if new is better")
    _args = _p.parse_args()

    if _args.stat:
        # Patch STATS to only fit the requested one
        import src.prediction.prop_model_stack as _pms
        _pms.STATS = [_args.stat]
    if _args.min_samples != MIN_SAMPLES:
        globals()["MIN_SAMPLES"] = _args.min_samples

    if _args.ab_test:
        residuals = _load_residuals()
        if not residuals:
            print("No calibration data available. Run predictions first to accumulate residuals.")
            sys.exit(0)
        results = ab_test_calibration(residuals)
        for stat, r in results.items():
            if "reason" in r:
                print(f"  {stat}: skipped ({r['reason']}, n={r.get('n', 0)})")
                continue
            promoted = "PROMOTED" if r.get("promoted") else "kept old"
            old = f"{r['old_brier']:.6f}" if isinstance(r.get("old_brier"), float) else "n/a"
            new = f"{r['new_brier']:.6f}"
            print(f"  {stat}: n={r.get('n', 0)}  old={old}  new={new}  [{promoted}]")
    else:
        main()
