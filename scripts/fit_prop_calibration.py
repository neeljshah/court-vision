"""
fit_prop_calibration.py — One-shot script: fit isotonic calibration for all 7 prop stats.

Loads prediction+actual pairs from:
  1. data/models/prop_residuals.json  (recorded at prediction time — most accurate)
  2. data/nba/gamelogs_*.json         (fallback box scores)

Fits one IsotonicRegression per stat and persists to
  data/models/calibration_{stat}.joblib

Run after a sufficient backlog of predictions has accumulated:
  python scripts/fit_prop_calibration.py

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
    main()
