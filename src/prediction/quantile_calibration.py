"""quantile_calibration.py — per-stat scale factor to make q10/q90 hit 80%.

The cycle-26 q10/q90 intervals are misclibrated:
  - PTS  coverage_80 = 74.7%   (too tight)
  - REB  coverage_80 = 78.7%
  - AST  coverage_80 = 76.2%   (too tight)
  - FG3M coverage_80 = 87.2%   (too wide)
  - STL  coverage_80 = 89.8%   (too wide — log1p + clip-at-0 squeezes)
  - BLK  coverage_80 = 89.8%   (too wide)
  - TOV  coverage_80 = 85.1%   (too wide)

This module computes a per-stat scale factor `s` such that:
    calibrated_q90 = q50 + s * (q90 - q50)
    calibrated_q10 = q50 - s * (q50 - q10)
covers exactly 80% on a held-out slice. Persisted as
data/models/quantile_calibration.json and applied at inference time by
prop_quantiles.predict_pergame_quantiles_calibrated.

s > 1 widens the interval, s < 1 narrows it.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    build_pergame_dataset, feature_columns,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    _inverse, load_quantile_models,
)


_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models")
_CAL_PATH = os.path.join(_MODEL_DIR, "quantile_calibration.json")


def _grid_search_scale(q10, q50, q90, actuals, target=0.80,
                       lo=0.05, hi=3.0, n=120) -> float:
    """Grid search the scale s that minimises |coverage - target|.

    Two grids: one with symmetric scaling (q10 + q90 both scale), one with
    asymmetric scaling (q10 floor preserved, only q90 scales). The asymmetric
    branch matters for stats where q10 is heavily clipped at 0 (FG3M/STL/BLK/
    TOV) — symmetric scaling has a coverage DISCONTINUITY at s=1.0 because
    crossing below s=1 lifts cal_q10 above 0 and chops out all zero-actuals
    instantly. The asymmetric branch (cal_q10 := q10) only narrows the upper
    side, which behaves monotonically with s.
    """
    q10_zero_frac = float((q10 <= 0.01).mean())
    asymmetric = q10_zero_frac > 0.30  # majority/heavy q10-at-zero clipping

    grid = np.linspace(lo, hi, n)
    best_s = 1.0; best_diff = 1.0
    for s in grid:
        if asymmetric:
            cal_q10 = q10  # preserve floor
            cal_q90 = q50 + s * (q90 - q50)
        else:
            cal_q10 = q50 - s * (q50 - q10)
            cal_q90 = q50 + s * (q90 - q50)
        cov = float(((actuals >= cal_q10) & (actuals <= cal_q90)).mean())
        diff = abs(cov - target)
        if diff < best_diff:
            best_diff = diff; best_s = float(s)
    return best_s


def calibrate(holdout_frac: float = 0.2, val_frac: float = 0.15) -> dict:
    """Fit per-stat scale factors on the VAL slice (NOT the holdout used for
    production metrics — that would leak into the calibration estimate)."""
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    train_end = int(n * (1.0 - holdout_frac - val_frac))
    val_end   = int(n * (1.0 - holdout_frac))
    val_rows = rows[train_end:val_end]
    print(f"calibration on val slice: {len(val_rows)} games", flush=True)

    X_val = np.array([[r[c] for c in fc] for r in val_rows], dtype=float)

    cal = {}
    for stat in STATS:
        models = load_quantile_models(stat, _MODEL_DIR)
        if 0.1 not in models or 0.5 not in models or 0.9 not in models:
            print(f"  [skip] {stat}: missing q10/q50/q90 models")
            continue
        q10_t = models[0.1].predict(X_val)
        q50_t = models[0.5].predict(X_val)
        q90_t = models[0.9].predict(X_val)
        q10 = _inverse(stat, q10_t)
        q50 = _inverse(stat, q50_t)
        q90 = _inverse(stat, q90_t)
        actuals = np.array([r[f"target_{stat}"] for r in val_rows], dtype=float)

        raw_cov = float(((actuals >= q10) & (actuals <= q90)).mean())
        s = _grid_search_scale(q10, q50, q90, actuals, target=0.80)
        q10_zero_frac = float((q10 <= 0.01).mean())
        if q10_zero_frac > 0.30:
            cal_q10 = q10  # preserve floor for asymmetric stats
            cal_q90 = q50 + s * (q90 - q50)
        else:
            cal_q10 = q50 - s * (q50 - q10)
            cal_q90 = q50 + s * (q90 - q50)
        cal_cov = float(((actuals >= cal_q10) & (actuals <= cal_q90)).mean())
        avg_width_raw = float(np.mean(q90 - q10))
        avg_width_cal = float(np.mean(cal_q90 - cal_q10))
        cal[stat] = {
            "scale":             round(s, 4),
            "asymmetric":        bool(q10_zero_frac > 0.30),
            "q10_zero_frac":     round(q10_zero_frac, 4),
            "raw_coverage_80":   round(raw_cov, 4),
            "cal_coverage_80":   round(cal_cov, 4),
            "raw_avg_width":     round(avg_width_raw, 4),
            "cal_avg_width":     round(avg_width_cal, 4),
        }
        print(f"  {stat.upper():4s} scale={s:.3f}  raw_cov={raw_cov:.3f} -> cal_cov={cal_cov:.3f}  "
              f"width {avg_width_raw:.3f} -> {avg_width_cal:.3f}", flush=True)

    with open(_CAL_PATH, "w", encoding="utf-8") as f:
        json.dump(cal, f, indent=2)
    print(f"[done] wrote {_CAL_PATH}")
    return cal


def get_scale(stat: str) -> float:
    """Per-stat quantile-width scale factor. 1.0 when no calibration cached."""
    if not os.path.exists(_CAL_PATH):
        return 1.0
    try:
        cal = json.load(open(_CAL_PATH, encoding="utf-8"))
        return float(cal.get(stat, {}).get("scale", 1.0))
    except Exception:
        return 1.0


def apply(stat: str, q10: float, q50: float, q90: float) -> tuple:
    """Return calibrated (q10, q90) for one prediction. Reads asymmetric flag
    from the calibration JSON when present so stats with q10-floor preservation
    apply the right transform at inference."""
    s = get_scale(stat)
    cal_entry = {}
    if os.path.exists(_CAL_PATH):
        try:
            cal_entry = json.load(open(_CAL_PATH, encoding="utf-8")).get(stat, {})
        except Exception:
            pass
    if cal_entry.get("asymmetric"):
        return float(max(0.0, q10)), float(q50 + s * (q90 - q50))
    cal_q10 = q50 - s * (q50 - q10)
    cal_q90 = q50 + s * (q90 - q50)
    return float(max(0.0, cal_q10)), float(cal_q90)


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore")
    calibrate()
