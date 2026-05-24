"""probe_error_strata.py — find where the model has the biggest prediction errors.

Cycle 81 showed that naive post-prediction scaling (pull-to-L5, B2B penalty,
min-ratio) all REJECT empirically. The model is well-calibrated relative
to those signals. But the model isn't perfect either — somewhere there are
buckets of player-games where it systematically errs.

This script stratifies holdout MAE by feature buckets to identify those.

Stratifications tested:
  - l5_min bucket            (low / mid / high recent minutes)
  - prev_min / l10_min ratio (the cycle-79 proxy revisited — but for STRATIFIED error, not adjustment)
  - opp_def_pts bucket       (vs weak / avg / strong defenses)
  - home_rest_days bucket    (b2b / 1d / 2d / 3+d rested)
  - prediction MAGNITUDE     (errors on low vs high predictions)
  - L5 - prediction          (does the model misestimate when player is on a heater / cold streak?)

For each stratification + stat, report:
  - bucket sample sizes
  - bucket MAE
  - relative MAE vs overall (a 1.5x bucket indicates the model has a systematic weakness there)
  - signed bias (mean(pred - actual) per bucket — positive = overpredicts)

Run:
    python scripts/probe_error_strata.py
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

# Reuse the bulk-predict harness so this script uses the IDENTICAL prediction
# path as validate_adjustment + verify_production_mae.
from scripts.validate_adjustment import _bulk_predict  # noqa: E402
from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


def _y_true(holdout: List[dict], stat: str) -> np.ndarray:
    # Cycle-79 fix: 0.0 is a valid target — don't `or np.nan` it.
    return np.array([
        np.nan if r.get(f"target_{stat}") is None else float(r[f"target_{stat}"])
        for r in holdout
    ], dtype=float)


def stratify(
    holdout: List[dict],
    X: np.ndarray,
    feature_fn,        # rows -> array of feature values for stratification
    bucket_edges: List[float],
    bucket_labels: List[str],
    label: str,
) -> None:
    """Compute bucket-wise MAE + bias for every stat."""
    feat = np.array([feature_fn(r) for r in holdout], dtype=float)
    print(f"\n=== {label} ===")
    print(f"{'bucket':<25}", end="")
    for stat in STATS:
        print(f" {stat.upper():>8}", end="")
    print()

    # Header for sample sizes
    print(f"{'':<25}", end="")
    for stat in STATS:
        print(f" {'(n)':>8}", end="")
    print()

    # Per-stat predictions
    preds_per_stat = {}
    for stat in STATS:
        p = _bulk_predict(stat, X)
        if p is not None:
            preds_per_stat[stat] = p

    for bi in range(len(bucket_edges) - 1):
        lo, hi = bucket_edges[bi], bucket_edges[bi + 1]
        mask = (feat >= lo) & (feat < hi)
        n = int(mask.sum())
        if n < 50:    # too small to be reliable
            print(f"{bucket_labels[bi]:<25}", end="")
            for _ in STATS:
                print(f" {'<50':>8}", end="")
            print()
            continue
        # MAE per stat
        line = f"{bucket_labels[bi]:<25}"
        for stat in STATS:
            yt = _y_true(holdout, stat)
            valid = mask & ~np.isnan(yt)
            if valid.sum() == 0 or stat not in preds_per_stat:
                line += f" {'na':>8}"
                continue
            p = preds_per_stat[stat]
            err = np.abs(p[valid] - yt[valid])
            line += f" {err.mean():>8.4f}"
        line += f"  n={n}"
        print(line)

    # Print overall reference MAE
    line = f"{'OVERALL':<25}"
    for stat in STATS:
        yt = _y_true(holdout, stat)
        valid = ~np.isnan(yt)
        if valid.sum() == 0 or stat not in preds_per_stat:
            line += f" {'na':>8}"
            continue
        p = preds_per_stat[stat]
        err = np.abs(p[valid] - yt[valid])
        line += f" {err.mean():>8.4f}"
    line += f"  n={len(holdout)}"
    print(line)


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

    # Strat 1: by recent minutes
    stratify(
        holdout, X,
        feature_fn=lambda r: float(r.get("l5_min", 0.0) or 0.0),
        bucket_edges=[0, 15, 25, 32, 48],
        bucket_labels=["l5_min < 15", "15-25", "25-32", "32+"],
        label="MAE by L5 minutes bucket",
    )

    # Strat 2: by minutes ratio (does limited-prev-min predict error?)
    def min_ratio(r):
        prev = float(r.get("prev_min", 0.0) or 0.0)
        l10 = float(r.get("l10_min", 0.0) or 0.0)
        if l10 <= 0:
            return 1.0
        return prev / l10
    stratify(
        holdout, X,
        feature_fn=min_ratio,
        bucket_edges=[0, 0.5, 0.9, 1.1, 3.0],
        bucket_labels=["ratio < 0.5", "0.5-0.9", "0.9-1.1", "1.1+"],
        label="MAE by prev_min/l10_min ratio (cycle-79 lineup proxy)",
    )

    # Strat 3: by opponent defense
    stratify(
        holdout, X,
        feature_fn=lambda r: float(r.get("opp_def_pts", 1.0) or 1.0),
        bucket_edges=[0.8, 0.95, 1.0, 1.05, 1.2],
        bucket_labels=["opp_def<0.95 (great)", "0.95-1.0",
                        "1.0-1.05", "1.05+ (weak)"],
        label="MAE by opp_def_pts bucket (game-context defense)",
    )

    # Strat 4: by rest days (cycle 82 fix: actual field is `rest_days` /
    # `is_b2b`, per-player not per-team — cycle-81 probe used wrong field).
    def player_rest(r):
        return float(r.get("rest_days", 2.0) or 2.0)
    stratify(
        holdout, X,
        feature_fn=player_rest,
        bucket_edges=[0, 1, 2, 4, 30],
        bucket_labels=["b2b (rest<1)", "1d rest", "2-3d rest", "4+d rest"],
        label="MAE by rest_days bucket (per-player, cycle-82 fixed)",
    )

    # Strat 6: by is_b2b flag specifically
    stratify(
        holdout, X,
        feature_fn=lambda r: float(r.get("is_b2b", 0) or 0),
        bucket_edges=[-0.5, 0.5, 1.5],
        bucket_labels=["non-b2b", "b2b game"],
        label="MAE by is_b2b flag (cycle-82 fix)",
    )

    # Strat 5: by prediction MAGNITUDE (only PTS — biggest range)
    p_pts = _bulk_predict("pts", X)
    if p_pts is not None:
        # Capture pred magnitude per row, stratify on it.
        magnitudes = p_pts.copy()
        # Reuse stratify by attaching to row dict temporarily.
        for i, r in enumerate(holdout):
            r["_pred_pts_for_strat"] = float(magnitudes[i])
        stratify(
            holdout, X,
            feature_fn=lambda r: r.get("_pred_pts_for_strat", 0.0),
            bucket_edges=[0, 8, 15, 22, 60],
            bucket_labels=["pred_pts < 8", "8-15", "15-22", "22+"],
            label="MAE by predicted-PTS magnitude (do model errors scale with size?)",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
