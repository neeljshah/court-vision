"""train_heat_check_shrinkage_residual.py -- cycle 103b (loop 5).

Trains :class:`src.prediction.heat_check_shrinkage_residual.HeatCheckShrinkageResidualModel`
on the heat_check subset of ``data/player_quarter_stats.parquet``.

Stratum gate:
    q3_ppm > 1.5 * q12_ppm  AND  q12_ppm > 0.3  AND  q4_min >= 0.5

Target:
    ratio = actual_q4_ppm / q3_ppm        (then CLIPPED to [0.70, 1.00])

This is the V2 design: predict the SHRINKAGE FACTOR to apply to the cycle-88
extrapolation, not the absolute Q4 PPM. Cycle 102b's mistake was REPLACING
the cycle-88 projection (got too flat on genuine high-usage scorers).

Chronological 80/20 split on game_id. Writes
``data/models/heat_check_shrinkage_residual.lgb`` + meta JSON.

Usage:
    python scripts/train_heat_check_shrinkage_residual.py
    python scripts/train_heat_check_shrinkage_residual.py --max-games 100
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import train_minute_trajectory as tmt  # noqa: E402
import train_heat_check_residual as thr  # noqa: E402 (reuse prior PPM index)
from src.prediction.heat_check_shrinkage_residual import (  # noqa: E402
    FACTOR_CEIL,
    FACTOR_FLOOR,
    HeatCheckShrinkageResidualModel,
    build_feature_row,
    in_heat_check_stratum,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def build_shrinkage_corpus(max_games: Optional[int] = None):
    """Emit (X, y_ratio, gids, stats) for heat_check rows.

    y_ratio = actual_q4_ppm / q3_ppm  (raw; model.fit will clip).
    """
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = tmt.load_positions()
    prior_ppm_index = thr._build_prior_ppm_index(df)

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows: List[List[float]] = []
    y: List[float] = []
    gids_out: List[str] = []
    raw_ratios: List[float] = []   # unclipped, for diagnostics
    stats = {
        "rows_total": 0,
        "rows_in_stratum_pre_q4_filter": 0,
        "rows_dropped_q4_low_min": 0,
        "rows_in_stratum": 0,
    }

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        # Per-player plus-minus through Q3 (game-flow proxy fed into the
        # score_margin_abs feature slot).
        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            min_by_q: Dict[int, float] = {}
            pts_by_q: Dict[int, float] = {}
            pm_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pts_by_q[p] = float(r["pts"])
                pm_by_q[p] = float(r.get("plus_minus", 0.0) or 0.0)

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            q1_pts = pts_by_q.get(1, 0.0)
            q2_pts = pts_by_q.get(2, 0.0)
            q3_pts = pts_by_q.get(3, 0.0)
            pm_through_q3 = (pm_by_q.get(1, 0.0) + pm_by_q.get(2, 0.0)
                             + pm_by_q.get(3, 0.0))

            if min_q3 <= 0.0:
                continue
            if (min_q1 + min_q2) <= 0.0:
                continue

            q3_ppm = q3_pts / min_q3
            q12_ppm = (q1_pts + q2_pts) / (min_q1 + min_q2)

            stats["rows_total"] += 1
            if not in_heat_check_stratum(q3_ppm, q12_ppm):
                continue
            stats["rows_in_stratum_pre_q4_filter"] += 1

            q4_min = min_by_q.get(4, 0.0)
            q4_pts = pts_by_q.get(4, 0.0)
            if q4_min < 0.5:
                stats["rows_dropped_q4_low_min"] += 1
                continue
            stats["rows_in_stratum"] += 1

            actual_q4_ppm = q4_pts / q4_min
            # Naive extrapolation = q3_ppm (per spec).
            ratio = actual_q4_ppm / max(q3_ppm, 1e-6)
            raw_ratios.append(ratio)

            spm, lpm = prior_ppm_index.get(
                (int(pid), gid), (float("nan"), float("nan")))
            pos_str = positions.get(int(pid))

            row = build_feature_row(
                q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
                min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
                season_pts_per_min=spm,
                l5_pts_per_min=lpm,
                position_proxy=pos_str,
                score_margin_abs=abs(pm_through_q3),
            )
            X_rows.append(row)
            y.append(float(ratio))
            gids_out.append(gid)

    return X_rows, y, gids_out, stats, raw_ratios


def chronological_split(X, y, game_id_rows, val_frac: float = 0.2):
    games_order = sorted(set(game_id_rows))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, gid in zip(X, y, game_id_rows):
        if gid in train_games:
            X_tr.append(x); y_tr.append(yi)
        else:
            X_val.append(x); y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  building heat_check SHRINKAGE training corpus...")
    X, y, gids, stats, raw_ratios = build_shrinkage_corpus(args.max_games)
    print(f"  endQ3 rows seen:              {stats['rows_total']}")
    print(f"  heat_check pre Q4-filter:     {stats['rows_in_stratum_pre_q4_filter']}")
    print(f"  dropped (q4_min < 0.5):       {stats['rows_dropped_q4_low_min']}")
    print(f"  final heat_check stratum:     {stats['rows_in_stratum']}")
    print(f"  unique games:                 {len(set(gids))}")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2

    import numpy as np
    raw_arr = np.asarray(raw_ratios)
    print(f"  raw ratio stats: mean={raw_arr.mean():.3f}  "
          f"median={np.median(raw_arr):.3f}  "
          f"p10={np.percentile(raw_arr, 10):.3f}  "
          f"p90={np.percentile(raw_arr, 90):.3f}")
    clipped = np.clip(raw_arr, FACTOR_FLOOR, FACTOR_CEIL)
    print(f"  clipped[{FACTOR_FLOOR},{FACTOR_CEIL}] mean={clipped.mean():.3f} "
          f"(target distribution the model fits)")
    floor_frac = float(np.mean(raw_arr < FACTOR_FLOOR))
    ceil_frac = float(np.mean(raw_arr > FACTOR_CEIL))
    print(f"  fraction below floor: {floor_frac:.2%}  "
          f"above ceil: {ceil_frac:.2%}")

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, 0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    model = HeatCheckShrinkageResidualModel()
    model.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
              num_boost_round=300, learning_rate=0.04,
              num_leaves=15, min_data_in_leaf=15, seed=42)

    pred_val = model.predict(X_val) if X_val else np.array([])
    y_val_clipped = np.clip(np.asarray(y_val), FACTOR_FLOOR, FACTOR_CEIL)
    val_mae = (float(np.mean(np.abs(pred_val - y_val_clipped)))
               if len(pred_val) else float("nan"))
    pred_tr = model.predict(X_tr)
    y_tr_clipped = np.clip(np.asarray(y_tr), FACTOR_FLOOR, FACTOR_CEIL)
    tr_mae = float(np.mean(np.abs(pred_tr - y_tr_clipped)))
    print(f"  train RATIO MAE: {tr_mae:.4f}  val RATIO MAE: {val_mae:.4f}")
    print(f"  fallback (mean clipped ratio): {model.fallback_mean:.4f}")
    if len(y_val):
        mean_pred = float(np.mean(y_tr_clipped))
        baseline = float(np.mean(np.abs(y_val_clipped - mean_pred)))
        print(f"  baseline (mean-pred) val MAE: {baseline:.4f}  "
              f"(improvement: {baseline - val_mae:+.4f})")
        # Output distribution of predictions
        print(f"  val pred distribution: "
              f"mean={pred_val.mean():.3f}  "
              f"p10={np.percentile(pred_val, 10):.3f}  "
              f"p90={np.percentile(pred_val, 90):.3f}")

    model.save()
    print(f"  saved -> data/models/heat_check_shrinkage_residual.lgb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
