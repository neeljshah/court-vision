"""train_foul_residual.py -- tier1-2 (loop 5).

Trains :class:`src.prediction.minute_trajectory_foul_residual.FoulChangeResidualModel`
on the FOUL_CHANGE subset of the 550-game per-quarter parquet. The global
minute_trajectory model (cycle 9d3) is GLOBALLY -10% PTS MAE but +0.16 PTS MAE
on the foul_change stratum. Stratum-specialized model REPLACES the global
prediction when the gate fires.

Stratum gate (matches `in_foul_change_stratum`):
    q3_pf >= 2   OR   pf_through_q3 >= 3   OR   (q3_pf == 0 AND pf_through_q3 == 4)

Chronological 80/20 split: earliest 80 % of game_ids train, latest 20 % validate.
Writes ``data/models/minute_trajectory_foul_residual.lgb`` plus meta JSON.

Usage:
    python scripts/train_foul_residual.py
    python scripts/train_foul_residual.py --max-games 100  (debug)
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Reuse the cycle 9d3 training infrastructure (position loader, gamelog
# rolling-mean, game-date lookup) -- the residual model uses the SAME inputs
# as the global model, plus q2_pf which lives in the parquet already.
import train_minute_trajectory as tmt  # noqa: E402
from src.prediction.minute_trajectory_foul_residual import (  # noqa: E402
    FoulChangeResidualModel,
    build_feature_row,
    in_foul_change_stratum,
)

_QPARQUET = os.path.join(PROJECT_DIR, "data", "player_quarter_stats.parquet")


def build_foul_change_corpus(max_games: Optional[int] = None) -> Tuple[
        List[List[float]], List[float], List[str], Dict[str, int]]:
    """Walk the per-quarter parquet and emit one (X_row, y) ONLY for rows
    that satisfy ``in_foul_change_stratum``.

    Returns (X, y, game_ids, stats) where stats is a {key: int} dict capturing
    corpus diagnostics (total rows seen, rows gated in, gate breakdown).
    """
    import pandas as pd

    df = pd.read_parquet(_QPARQUET)
    positions = tmt.load_positions()
    pid_log_index = tmt.load_player_gamelog_minutes()

    games_in_order = sorted(df["game_id"].unique().tolist())
    if max_games:
        games_in_order = games_in_order[:max_games]

    X_rows: List[List[float]] = []
    y: List[float] = []
    gids_out: List[str] = []
    stats = {
        "rows_total": 0,
        "rows_in_stratum": 0,
        "gate_q3_pf": 0,
        "gate_total_pf": 0,
        "gate_foul_out_edge": 0,
    }

    for gid in games_in_order:
        gdf = df[df["game_id"] == gid]
        if gdf.empty:
            continue
        target_date = tmt.find_game_date_for_game(gid, df, pid_log_index)

        for pid in gdf["player_id"].unique():
            pdf = gdf[gdf["player_id"] == pid]
            min_by_q: Dict[int, float] = {}
            pf_by_q: Dict[int, float] = {}
            for _, r in pdf.iterrows():
                p = int(r["period"])
                min_by_q[p] = float(r["min"])
                pf_by_q[p] = float(r["pf"])

            min_q1 = min_by_q.get(1, 0.0)
            min_q2 = min_by_q.get(2, 0.0)
            min_q3 = min_by_q.get(3, 0.0)
            min_through = min_q1 + min_q2 + min_q3
            if min_through <= 0.5:
                continue

            q2_pf = pf_by_q.get(2, 0.0)
            q3_pf = pf_by_q.get(3, 0.0)
            pf_through = (pf_by_q.get(1, 0.0)
                          + pf_by_q.get(2, 0.0)
                          + pf_by_q.get(3, 0.0))

            stats["rows_total"] += 1
            if not in_foul_change_stratum(q3_pf=q3_pf, pf_through_q3=pf_through):
                continue
            stats["rows_in_stratum"] += 1
            # Track which sub-clause fired (mutually-non-exclusive: tally any).
            if q3_pf >= 2:
                stats["gate_q3_pf"] += 1
            if pf_through >= 3:
                stats["gate_total_pf"] += 1
            if q3_pf == 0 and pf_through == 4:
                stats["gate_foul_out_edge"] += 1

            # Target: sum of period >= 4 (Q4 + OT) minutes.
            rem_min = 0.0
            for _, r in pdf.iterrows():
                if int(r["period"]) >= 4:
                    rem_min += float(r["min"])

            pos_str = positions.get(int(pid))
            l20 = tmt.rolling_mean_min(int(pid), target_date, 20, pid_log_index)
            l5 = tmt.rolling_mean_min(int(pid), target_date, 5, pid_log_index)

            row = build_feature_row(
                pf_through_q3=pf_through,
                q3_pf=q3_pf,
                min_q1=min_q1, min_q2=min_q2, min_q3=min_q3,
                period=3,
                score_margin_abs=0.0,
                is_leading_team=0,
                position_proxy=pos_str,
                l20_min=l20, l5_min=l5,
                q2_pf=q2_pf,
            )
            X_rows.append(row)
            y.append(float(rem_min))
            gids_out.append(gid)

    return X_rows, y, gids_out, stats


def chronological_split(X: List[List[float]], y: List[float],
                        game_id_rows: List[str], val_frac: float = 0.2) -> Tuple[
                            List[List[float]], List[float],
                            List[List[float]], List[float]]:
    """Same as train_minute_trajectory.chronological_split -- duplicated to
    avoid a hard import of that helper from the residual trainer.
    """
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

    print("  loading + building foul_change training corpus...")
    X, y, gids, stats = build_foul_change_corpus(max_games=args.max_games)
    print(f"  total endQ3 rows seen:      {stats['rows_total']}")
    print(f"  foul_change stratum rows:   {stats['rows_in_stratum']}")
    print(f"    gate q3_pf>=2:            {stats['gate_q3_pf']}")
    print(f"    gate total_pf>=3:         {stats['gate_total_pf']}")
    print(f"    gate q3_pf=0,total_pf=4:  {stats['gate_foul_out_edge']}")
    print(f"  unique games in stratum:    {len(set(gids))}")
    if not X:
        print("  ERROR: empty corpus, abort")
        return 2
    if len(X) < 200:
        print(f"  WARN: n={len(X)} < 200 (stability bar). Proceeding anyway "
              f"but consider relaxing the gate.")

    X_tr, y_tr, X_val, y_val = chronological_split(X, y, gids, val_frac=0.2)
    print(f"  split: train={len(X_tr)}  val={len(X_val)}")

    model = FoulChangeResidualModel()
    model.fit(X_tr, y_tr, X_val=X_val, y_val=y_val,
              num_boost_round=300, learning_rate=0.04,
              num_leaves=15, min_data_in_leaf=20, seed=42)

    import numpy as np
    pred_val = model.predict(X_val) if X_val else np.array([])
    val_mae = (float(np.mean(np.abs(pred_val - np.asarray(y_val))))
               if len(pred_val) else float("nan"))
    pred_tr = model.predict(X_tr)
    tr_mae = float(np.mean(np.abs(pred_tr - np.asarray(y_tr))))
    print(f"  train MAE: {tr_mae:.4f}  val MAE: {val_mae:.4f}")
    print(f"  fallback (train mean y): {model.fallback_mean:.4f}")
    if len(y_val):
        mean_pred = float(np.mean(y_tr))
        baseline_val_mae = float(np.mean(np.abs(np.asarray(y_val) - mean_pred)))
        print(f"  baseline (mean-pred) val MAE: {baseline_val_mae:.4f}  "
              f"(improvement: {baseline_val_mae - val_mae:+.4f})")

    model.save()
    print(f"  saved -> data/models/minute_trajectory_foul_residual.lgb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
