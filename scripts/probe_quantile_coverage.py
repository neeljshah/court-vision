"""probe_quantile_coverage.py — empirically verify q10/q90 hit 80% coverage.

Cycle 40 shipped quantile_calibration.py which scales q10/q90 per stat to
hit 80% empirical coverage. This script verifies that's actually true on
the production holdout.

If empirical coverage is OFF (e.g., 75% instead of 80%), then:
  - Quantile widths are mis-sized — directly impacts:
    - compare_to_lines.py EV math (uses width as sigma proxy)
    - confidence.py variance score (uses (q90-q10)/q50)
  - A simple recalibration cycle could ship.

Run:
    python scripts/probe_quantile_coverage.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns, _MODEL_DIR,
    _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
)
from src.prediction.prop_quantiles import load_quantile_models, _inverse as _qinv  # noqa: E402
from src.prediction.quantile_calibration import apply as apply_quant_cal  # noqa: E402


def main() -> int:
    print("Loading pergame dataset...", flush=True)
    rows, _fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    holdout = rows[int(n * 0.80):]
    cols = feature_columns()
    X = np.array([[float(r.get(c, 0.0) or 0.0) for c in cols]
                  for r in holdout], dtype=float)
    print(f"  n={n} holdout={len(holdout)}\n", flush=True)

    print(f"{'stat':<5} {'n':>6} {'uncal_cov':>10} {'cal_cov':>10}  "
          f"{'tgt':>5}  {'q10_mean':>9} {'q90_mean':>9}  verdict")
    print("-" * 75)

    for stat in STATS:
        # Honest target getter (cycle-79 fix)
        y_true = np.array([
            np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(y_true)

        # Load quantile models
        qmodels = load_quantile_models(stat, _MODEL_DIR)
        if not qmodels or 0.1 not in qmodels or 0.9 not in qmodels:
            print(f"{stat:<5} (quantile models missing)")
            continue

        q10_raw = _qinv(stat, qmodels[0.1].predict(X))
        q90_raw = _qinv(stat, qmodels[0.9].predict(X))
        q50_raw = (_qinv(stat, qmodels[0.5].predict(X))
                   if 0.5 in qmodels else (q10_raw + q90_raw) / 2)

        # Apply calibration row-wise (apply_quant_cal returns (q10, q90) tuple).
        q10_cal = np.empty_like(q10_raw); q90_cal = np.empty_like(q90_raw)
        for i in range(len(q10_raw)):
            cq10, cq90 = apply_quant_cal(stat,
                                          float(q10_raw[i]), float(q50_raw[i]),
                                          float(q90_raw[i]))
            q10_cal[i] = cq10; q90_cal[i] = cq90

        # Empirical coverage = fraction of holdout actuals within [q10, q90]
        yt = y_true[mask]
        uncal_cov = float(np.mean((yt >= q10_raw[mask]) & (yt <= q90_raw[mask])))
        cal_cov = float(np.mean((yt >= q10_cal[mask]) & (yt <= q90_cal[mask])))
        n_used = int(mask.sum())

        # Target is 80% (q10..q90 is 80% interval by definition).
        # Verdict: |actual - 80%| <= 2% is "OK", otherwise "DRIFT".
        gap = abs(cal_cov - 0.80)
        if gap <= 0.02:
            verdict = "OK"
        elif cal_cov < 0.80:
            verdict = "TOO TIGHT"
        else:
            verdict = "TOO WIDE"

        print(f"{stat:<5} {n_used:>6d} {uncal_cov*100:>9.2f}% {cal_cov*100:>9.2f}%  "
              f"{'80%':>5}  {q10_cal[mask].mean():>9.3f} {q90_cal[mask].mean():>9.3f}  "
              f"{verdict}")

    print()
    print("If any verdict is TOO TIGHT or TOO WIDE, re-run "
          "`python -m src.prediction.quantile_calibration` to recalibrate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
