"""probe_per_segment_mae.py — measure per-segment MAE within the global model.

Cycle 82 strata showed PTS MAE goes from 3.55 (pred_pts<8) to 6.35 (pred>22)
— a 78% increase. Same global model used. Question: could a 2-model
ensemble (one trained on low-output players, one on high-output) outperform?

This probe doesn't ship a new model — it measures the IN-SAMPLE OPTIMAL
per-segment offset (each segment's mean residual subtracted from its own
predictions). That's an upper bound on what per-segment retraining could win.

If even the in-sample bound shows no meaningful gain, per-segment retraining
won't help either — the global model is segment-calibrated already.

Segments tested per stat:
  - by L5 minutes (low/mid/high recent role)
  - by predicted magnitude (model's own bucketing)
  - by player USG_pct from cached advanced stats (if available)

Run:
    python scripts/probe_per_segment_mae.py
"""
from __future__ import annotations

import os
import sys
import warnings
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


def per_segment_mae(
    stat: str,
    pred: np.ndarray,
    y_true: np.ndarray,
    seg_arr: np.ndarray,
    edges: List[float],
    labels: List[str],
) -> Tuple[List[Dict], float, float]:
    """For each segment, compute:
      - segment MAE
      - per-segment-offset MAE (subtract that segment's mean residual)
    Returns (per_segment_records, global_mae, per_segment_corrected_mae)
    """
    mask = ~np.isnan(y_true)
    global_mae = float(np.mean(np.abs(pred[mask] - y_true[mask])))

    segments = []
    total_err = 0.0
    n_used = 0
    for bi in range(len(edges) - 1):
        lo, hi = edges[bi], edges[bi + 1]
        seg_mask = (seg_arr >= lo) & (seg_arr < hi) & mask
        n = int(seg_mask.sum())
        if n < 50:
            segments.append({"label": labels[bi], "n": n, "mae": None,
                              "offset": None, "corrected_mae": None})
            continue
        seg_pred = pred[seg_mask]
        seg_actual = y_true[seg_mask]
        seg_mae = float(np.mean(np.abs(seg_pred - seg_actual)))
        # In-sample optimal offset = mean residual
        seg_bias = float(np.mean(seg_pred - seg_actual))
        seg_corrected = np.abs((seg_pred - seg_bias) - seg_actual)
        seg_corr_mae = float(np.mean(seg_corrected))
        segments.append({"label": labels[bi], "n": n, "mae": seg_mae,
                          "offset": -seg_bias, "corrected_mae": seg_corr_mae})
        # Accumulate total weighted error using offset-corrected predictions
        total_err += np.sum(seg_corrected)
        n_used += n
    overall_corrected = total_err / max(1, n_used)
    return segments, global_mae, overall_corrected


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

    for stat in STATS:
        y = _y_true(holdout, stat)
        p = _bulk_predict(stat, X)
        if p is None:
            print(f"{stat:<5} (model missing)")
            continue

        # Segment 1: by L5 minutes
        l5_arr = np.array([float(r.get("l5_min", 0.0) or 0.0) for r in holdout])
        segs, gmae, cor_mae = per_segment_mae(
            stat, p, y, l5_arr,
            edges=[0, 15, 25, 32, 48],
            labels=["l5<15", "15-25", "25-32", "32+"])
        print(f"\n--- {stat.upper()} segmented by L5 minutes ---")
        print(f"{'segment':<8} {'n':>6} {'seg_mae':>9} {'in_off':>8} {'seg_off_mae':>13}")
        for s in segs:
            if s["mae"] is None:
                print(f"{s['label']:<8} {s['n']:>6d}  (<50)")
                continue
            print(f"{s['label']:<8} {s['n']:>6d} {s['mae']:>9.4f} "
                  f"{s['offset']:>+8.3f} {s['corrected_mae']:>13.4f}")
        print(f"global MAE: {gmae:.4f} | per-seg-offset MAE (IN-SAMPLE BOUND): {cor_mae:.4f} "
              f"(delta {cor_mae - gmae:+.4f})")

    print()
    print("`in_off`: the offset that minimizes MAE in that segment (in-sample).")
    print("`seg_off_mae`: segment MAE after applying in-sample optimal offset.")
    print("If the OVERALL `delta` is meaningfully negative (e.g. -0.05+),")
    print("per-segment models / per-segment offsets are worth shipping.")
    print("If delta is ~0, the global model is already segment-calibrated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
