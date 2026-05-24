"""probe_bias.py — does the model systematically over- or under-predict?

For each stat, computes:
  mean(pred - actual)         # signed bias (+ = overpredict)
  mean(|pred - actual|)       # MAE (cycle-48 verified)
  mean(pred - actual) / MAE   # bias as fraction of MAE — if >0.10 ish,
                                worth correcting

If any stat has meaningful bias, a constant offset adjustment might help.
This is the simplest possible correction: subtract the mean residual from
every prediction.

If empirically validated, ship as a "calibrated offset" applied at inference
time. Tiny code change, no retrain.
"""
from __future__ import annotations

import os
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


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

    print(f"{'stat':<5} {'n':>6} {'pred_mean':>10} {'actual_mean':>11} "
          f"{'bias':>9} {'mae':>9} {'bias/mae':>9}  hypothetical")
    print("-" * 80)
    for stat in STATS:
        y_true = np.array([
            np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
            for r in holdout
        ], dtype=float)
        mask = ~np.isnan(y_true)
        pred = _bulk_predict(stat, X)
        if pred is None:
            print(f"{stat:<5} (model missing)")
            continue
        residual = pred[mask] - y_true[mask]
        bias = float(np.mean(residual))
        mae = float(np.mean(np.abs(residual)))
        # Hypothetical MAE if we subtracted the bias from every prediction
        # (in-sample best case — overestimates real-world gain).
        corrected = residual - bias
        mae_corrected = float(np.mean(np.abs(corrected)))
        delta = mae_corrected - mae
        verdict = ("BIASED -> -" + f"{bias:.3f} offset could help" if abs(bias / mae) > 0.05
                   else "unbiased")
        print(f"{stat:<5} {int(mask.sum()):>6d} {pred[mask].mean():>10.4f} "
              f"{y_true[mask].mean():>11.4f} {bias:>+9.4f} {mae:>9.4f} "
              f"{(bias / mae):>+9.4f}  {verdict}")
        if abs(bias / mae) > 0.05:
            print(f"      hypothetical bias-corrected MAE: {mae_corrected:.4f} "
                  f"(delta {delta:+.4f}, in-sample max)")
    print()
    print("Note: bias-corrected MAE is the IN-SAMPLE best case — empirical")
    print("validation against next-N-days holdout would be needed before shipping.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
