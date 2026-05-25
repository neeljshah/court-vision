"""train_heat_check_residual.py -- cycle 102b (loop 5).

Trains :class:`src.prediction.heat_check_residual.HeatCheckResidualModel` on
the heat_check subset of ``data/player_quarter_stats.parquet``.

Stratum gate (matches cycle 95b decompose_endQ3_mae):
    q3_ppm > 1.5 * q12_ppm  AND  q12_ppm > 0.3

Target: actual Q4 pts-per-minute (q4_pts / q4_min). Rows where the player
sits all of Q4 (q4_min < 0.5) are DROPPED to avoid PPM blow-up -- the
heat-check minute reduction is handled by the existing minute_trajectory
model; this residual learns SCORING-RATE reversion, not bench-out.

Chronological 80/20 split on game_id. Writes
``data/models/heat_check_residual.lgb`` + meta JSON.

Usage:
    python scripts/train_heat_check_residual.py
    python scripts/train_heat_check_residual.py --max-games 100  (debug)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

import train_minute_trajectory as tmt  # noqa: E402  (helper reuse)
from src.prediction.heat_check_residual import (  # noqa: E402
    HeatCheckResidualModel,
    build_feature_row,
    in_heat_check_stratum,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def _build_prior_ppm_index(qstats_df) -> Dict[Tuple[int, str], Tuple[float, float]]:
    """Build a per-(player, game_id) lookup of (season_ppm, l5_ppm)
    aggregated ONLY over PRIOR games (chronologically earlier game_ids).

    Returns {(pid, gid): (season_ppm_prior, l5_ppm_prior)} with NaN for
    players who have no prior games in the corpus.

    Computed from the same parquet -- aggregates per-game total pts / total
    min across all 4 periods for each (pid, gid), then walks forward in
    game_id order to compute the cumulative season and trailing-5 PPMs at
    each game.

    This is leakage-safe: a player's row for game G uses ONLY games < G.
    """
    import numpy as np
    import pandas as pd

    # Aggregate per (pid, gid).
    g = qstats_df.groupby(["player_id", "game_id"], as_index=False).agg(
        total_pts=("pts", "sum"),
        total_min=("min", "sum"),
    )
    g = g.sort_values(["player_id", "game_id"]).reset_index(drop=True)

    out: Dict[Tuple[int, str], Tuple[float, float]] = {}
    for pid, pdf in g.groupby("player_id"):
        pdf = pdf.reset_index(drop=True)
        cum_pts = 0.0
        cum_min = 0.0
        recent_pts: List[float] = []
        recent_min: List[float] = []
        for i, row in pdf.iterrows():
            gid = str(row["game_id"])
            # prior values BEFORE this game
            season_ppm = (cum_pts / cum_min) if cum_min > 0 else float("nan")
            recent_p_sum = sum(recent_pts)
            recent_m_sum = sum(recent_min)
            l5_ppm = (recent_p_sum / recent_m_sum
                      if recent_m_sum > 0 else float("nan"))
            out[(int(pid), gid)] = (season_ppm, l5_ppm)
            # Now consume this game's contribution for future games.
            tp = float(row["total_pts"])
            tm = float(row["total_min"])
            cum_pts += tp
            cum_min += tm
            recent_pts.append(tp)
            recent_min.append(tm)
            if len(recent_pts) > 5:
                recent_pts.pop(0)
                recent_min.pop(0)
    return out


def build_heat_check_corpus(max_games: Optional[int] = None) -> Tuple[
        List[List[float]], List[float], List[str], Dict[str, int]]:
    """Walk the parquet and emit (X, y, gids) ONLY for rows passing the
    heat_check gate AND having q4_min >= 0.5 (need a non-trivial Q4 sample
    to compute the PPM target without blowup).
    """
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = tmt.load_positions()
    prior_ppm_index = _build_prior_ppm_index(df)

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows: List[List[float]] = []
    y: List[float] = []
    gids_out: List[str] = []
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
        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            min_by_q: Dict[int, float] = {}
            pts_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pts_by_q[p] = float(r["pts"])

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            q1_pts = pts_by_q.get(1, 0.0)
            q2_pts = pts_by_q.get(2, 0.0)
            q3_pts = pts_by_q.get(3, 0.0)

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

            target_ppm = q4_pts / q4_min

            spm, lpm = prior_ppm_index.get((int(pid), gid), (float("nan"), float("nan")))
            pos_str = positions.get(int(pid))

            row = build_feature_row(
                q1_pts=q1_pts, q2_pts=q2_pts, q3_pts=q3_pts,
                min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
                season_pts_per_min=spm,
                l5_pts_per_min=lpm,
                position_proxy=pos_str,
            )
            X_rows.append(row)
            y.append(float(target_ppm))
            gids_out.append(gid)

    return X_rows, y, gids_out, stats


def chronological_split(X, y, game_id_rows, val_frac: float = 0.2):
    games_order = sorted(set(game_id_rows))
    cutoff = int(len(games_order) * (1 - val_frac))
    train_games = set(games_order[:cutoff])
    X_tr, y_tr, X_val, y_val = [], [], [], []
    for x, yi, gid in zip(X, y, game_id_rows):
        if gid in train_games:
            X_tr.append(x)
            y_tr.append(yi)
        else:
            X_val.append(x)
            y_val.append(yi)
    return X_tr, y_tr, X_val, y_val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  loading + building heat_check training corpus...")
    X, y, gids, stats = build_heat_check_corpus(max_games=args.max_games)
    print(f"  total endQ3 rows seen:         {stats['rows_total']}")
    print(f"  heat_check pre Q4-filter:      {stats['rows_in_stratum_pre_q4_filter']}")
    print(f"  dropped (q4_min < 0.5):        {stats['rows_dropped_q4_low_min']}")
    print(f"  final heat_check stratum:      {stats['rows_in_stratum']}")
    print(f"  unique games in stratum:       {len(set(gids))}")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2
    if len(X) < 200:
        print(f"  WARN: n={len(X)} < 200 (stability bar). Proceeding anyway.")

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, val_frac=0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    model = HeatCheckResidualModel()
    model.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
              num_boost_round=250, learning_rate=0.04,
              num_leaves=15, min_data_in_leaf=15, seed=42)

    import numpy as np
    pred_val = model.predict(X_val) if X_val else np.array([])
    val_mae = (float(np.mean(np.abs(pred_val - np.asarray(y_val))))
               if len(pred_val) else float("nan"))
    pred_tr = model.predict(X_tr)
    tr_mae = float(np.mean(np.abs(pred_tr - np.asarray(y_tr))))
    print(f"  train PPM MAE: {tr_mae:.4f}  val PPM MAE: {val_mae:.4f}")
    print(f"  fallback (train mean target ppm): {model.fallback_mean:.4f}")
    if len(y_val):
        mean_pred = float(np.mean(y_tr))
        baseline_val_mae = float(np.mean(np.abs(np.asarray(y_val) - mean_pred)))
        print(f"  baseline (mean-pred) val MAE: {baseline_val_mae:.4f}  "
              f"(improvement: {baseline_val_mae - val_mae:+.4f})")

    model.save()
    print(f"  saved -> data/models/heat_check_residual.lgb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
