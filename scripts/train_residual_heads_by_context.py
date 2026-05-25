"""scripts/train_residual_heads_by_context.py -- R3-G context-aware residual heads.

Trains 14 LightGBM residual heads (7 stats × 2 context buckets):
  close  : |score_margin_abs| < 12
  blow   : |score_margin_abs| >= 12

Target: actual_full_game - cycle_110_projection (same residual as R2_F,
        but partitioned by game context so heads can specialise).

These heads REPLACE, not stack on top of, R2_F single-context heads at
inference time (probe_R3_G_context_aware_heads.py swaps v1 for v2).

WF gate per (bucket, stat): save only if WF mean MAE strictly < zero-pred
on >= 3/4 folds.

Artifacts:
  data/models/residual_heads_close/{stat}.lgb
  data/models/residual_heads_blow/{stat}.lgb
  data/models/residual_heads_context_training_report.json

Usage:
    python scripts/train_residual_heads_by_context.py
    python scripts/train_residual_heads_by_context.py --max-games 200
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import retro_inplay_mae as v1  # noqa: E402
from scripts.improve_loop.scaffold import BASELINE  # noqa: E402

STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
CLOSE_THRESHOLD = 12.0  # |margin| < 12 → close game

OUT_DIR_CLOSE = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_close")
OUT_DIR_BLOW = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_blow")
REPORT_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "residual_heads_context_training_report.json"
)

LGB_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "regression_l1",
    "random_state": 42,
    "verbosity": -1,
    "n_jobs": -1,
}

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot from NBA position string."""
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1.0, 0.0, 0.0
    if "F" in p and "C" not in p and "G" not in p:
        return 0.0, 1.0, 0.0
    if "G" in p and "F" not in p and "C" not in p:
        return 0.0, 0.0, 1.0
    return 0.0, 0.0, 0.0


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
) -> Tuple[
    Dict[str, List[List[float]]],  # X per bucket
    Dict[str, Dict[str, List[float]]],  # Y[bucket][stat]
    Dict[str, List[str]],  # game_ids per bucket
]:
    """Build feature rows split into 'close' and 'blow' buckets.

    Target residual = actual - BASELINE(endQ3_snap).
    This is identical to train_residual_heads.py — no R2_F adjustment
    because these context heads REPLACE R2_F single heads at inference.
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    buckets = ("close", "blow")
    X: Dict[str, List[List[float]]] = {b: [] for b in buckets}
    Y: Dict[str, Dict[str, List[float]]] = {b: {s: [] for s in STATS} for b in buckets}
    game_ids_out: Dict[str, List[str]] = {b: [] for b in buckets}

    n_games = len(games)
    for gi, gid in enumerate(games):
        if gi % 100 == 0:
            print(f"  building rows {gi}/{n_games} ...", flush=True)
        snap = v1.build_snapshot(gid, "endQ3", qstats_df)
        if snap is None:
            continue
        actuals = v1.actuals_for_game(gid, qstats_df)

        try:
            proj_map = BASELINE(snap)
        except Exception as exc:
            print(f"  WARN: BASELINE failed for {gid}: {exc}")
            continue

        home_pts = float(snap.get("home_score", 0) or 0)
        away_pts = float(snap.get("away_score", 0) or 0)
        margin = abs(home_pts - away_pts)
        bucket = "close" if margin < CLOSE_THRESHOLD else "blow"

        home_team = str(snap.get("home_team", "") or "")
        away_team = str(snap.get("away_team", "") or "")

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", "") or "")
            if team == home_team:
                raw_margin = home_pts - away_pts
            elif team == away_team:
                raw_margin = away_pts - home_pts
            else:
                raw_margin = 0.0

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

            feat = [
                float(player.get("pts", 0) or 0),
                float(player.get("reb", 0) or 0),
                float(player.get("ast", 0) or 0),
                float(player.get("fg3m", 0) or 0),
                float(player.get("stl", 0) or 0),
                float(player.get("blk", 0) or 0),
                float(player.get("tov", 0) or 0),
                float(player.get("pf", 0) or 0),
                float(player.get("min", 0) or 0),
                margin,
                float(raw_margin > 0),
                float(pos_c),
                float(pos_f),
                float(pos_g),
            ]

            all_stats_present = True
            row_residuals: Dict[str, float] = {}
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = proj_map.get((pid, stat))
                if actual is None or proj is None:
                    all_stats_present = False
                    break
                row_residuals[stat] = actual - proj

            if not all_stats_present:
                continue

            X[bucket].append(feat)
            for stat in STATS:
                Y[bucket][stat].append(row_residuals[stat])
            game_ids_out[bucket].append(gid)

    return X, Y, game_ids_out


def train_one_stat(
    stat: str,
    bucket: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
    out_dir: str,
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold gate >= 3/4 folds beat zero-pred.

    Returns (saved: bool, report: dict).
    """
    import lightgbm as lgb
    import numpy as np

    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
    groups = np.array([gid_to_idx[gid] for gid in game_ids], dtype=np.int32)

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_wins = 0
    fold_details = []

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])

        val_game_idxs = {gid_to_idx[g] for g in val_game_set}
        train_mask = np.array(
            [gid_to_idx[gid] not in val_game_idxs for gid in game_ids], dtype=bool
        )
        val_mask = ~train_mask

        if train_mask.sum() < LGB_PARAMS["min_child_samples"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(X[train_mask], y_arr[train_mask], feature_name=FEATURE_NAMES)
        preds = model.predict(X[val_mask])
        residuals_val = y_arr[val_mask]

        mae_model = float(np.mean(np.abs(preds - residuals_val)))
        mae_zero = float(np.mean(np.abs(residuals_val)))
        delta = mae_model - mae_zero
        fold_details.append({
            "fold": fi + 1,
            "n_val": int(val_mask.sum()),
            "mae_model": round(mae_model, 5),
            "mae_zero": round(mae_zero, 5),
            "delta": round(delta, 5),
        })
        if mae_model < mae_zero:
            fold_wins += 1
        print(
            f"    [{bucket}/{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
            f"zero={mae_zero:.4f} delta={delta:+.4f} "
            f"{'WIN' if mae_model < mae_zero else 'loss'}"
        )

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        out_path = os.path.join(out_dir, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{bucket}/{stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(
            f"  [{bucket}/{stat}] NOT SAVED (only {fold_wins}/4 folds beat zero-pred)"
        )

    return saved, {
        "stat": stat,
        "bucket": bucket,
        "n_rows": len(y),
        "fold_wins": fold_wins,
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Train context-aware residual heads for R3-G angle."
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR_CLOSE, exist_ok=True)
    os.makedirs(OUT_DIR_BLOW, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  building feature rows (split by context) ...")
    X_by_bucket, Y_by_bucket, game_ids_by_bucket = build_rows(
        qstats_df, args.max_games, positions
    )

    for bucket, out_dir in (("close", OUT_DIR_CLOSE), ("blow", OUT_DIR_BLOW)):
        n_rows = len(X_by_bucket[bucket])
        print(f"\n  === bucket={bucket} ({n_rows} rows) ===")

    report: Dict = {
        "close": {"trained_stats": [], "skipped_stats": []},
        "blow": {"trained_stats": [], "skipped_stats": []},
    }

    bucket_dirs = {"close": OUT_DIR_CLOSE, "blow": OUT_DIR_BLOW}
    for bucket, out_dir in bucket_dirs.items():
        X_rows = X_by_bucket[bucket]
        game_ids = game_ids_by_bucket[bucket]
        print(f"\n  ---- Training bucket={bucket} ({len(X_rows)} rows) ----")
        for stat in STATS:
            y = Y_by_bucket[bucket][stat]
            if len(y) < 200:
                print(f"  [{bucket}/{stat}] too few rows ({len(y)}), skip")
                report[bucket]["skipped_stats"].append({"stat": stat, "reason": "too_few_rows", "n": len(y)})
                continue
            saved, stat_report = train_one_stat(stat, bucket, X_rows, y, game_ids, out_dir)
            if saved:
                report[bucket]["trained_stats"].append(stat_report)
            else:
                report[bucket]["skipped_stats"].append(stat_report)

    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {REPORT_PATH}")

    for bucket in ("close", "blow"):
        saved_stats = [
            r["stat"] if isinstance(r, dict) else r
            for r in report[bucket]["trained_stats"]
        ]
        print(f"  [{bucket}] heads saved: {saved_stats or 'none'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
