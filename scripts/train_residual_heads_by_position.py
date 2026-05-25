"""scripts/train_residual_heads_by_position.py -- R4-E position-stratified residual heads.

Mirrors train_residual_heads.py but partitions training rows by player position
(G, F, C) and trains 21 heads: 7 stats × 3 positions.

Position buckets:
  G  → PG / SG / G
  F  → SF / PF / F
  C  → C / F-C / C-F
  UNK → routed through G head (no separate model)

Models saved to:
  data/models/residual_heads_pos_G/{stat}.lgb
  data/models/residual_heads_pos_F/{stat}.lgb
  data/models/residual_heads_pos_C/{stat}.lgb

WF gate: save only if WF mean MAE < zero-pred baseline on >= 3/4 folds.
Target: actual_final[stat] - cycle_110_projection[stat]  (pre-R2_F baseline residual).
Skip stat-position combos with <2000 training rows (fallback to global R2_F).

Usage:
    python scripts/train_residual_heads_by_position.py
    python scripts/train_residual_heads_by_position.py --max-games 300
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

POS_BUCKETS = ("G", "F", "C")

# Output dirs per bucket
OUT_DIRS = {
    "G": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_G"),
    "F": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_F"),
    "C": os.path.join(PROJECT_DIR, "data", "models", "residual_heads_pos_C"),
}

MIN_ROWS = 2000  # skip combos below this threshold

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


def _pos_bucket(pos_str: str) -> str:
    """Map NBA position string to G / F / C bucket. UNK → 'G'."""
    p = (pos_str or "").upper()
    # Pure C or hybrid C-F / F-C → C bucket
    if "C" in p:
        return "C"
    # Pure F or SF / PF → F bucket
    if "F" in p:
        return "F"
    # PG / SG / G or anything unrecognized → G bucket (UNK fallback)
    return "G"


def _pos_flags(pos_str: str) -> Tuple[float, float, float]:
    """Return (pos_C, pos_F, pos_G) one-hot for the feature vector."""
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
    Dict[str, List[List[float]]],   # X per bucket
    Dict[str, Dict[str, List[float]]],  # Y per bucket per stat
    Dict[str, List[str]],            # game_ids per bucket
]:
    """Build stratified feature / target rows split by position bucket.

    Returns:
        X_by_pos:    {bucket: [[feat, ...], ...]}
        Y_by_pos:    {bucket: {stat: [residual, ...]}}
        gids_by_pos: {bucket: [game_id, ...]}
    """
    X_by_pos: Dict[str, List[List[float]]] = {b: [] for b in POS_BUCKETS}
    Y_by_pos: Dict[str, Dict[str, List[float]]] = {
        b: {s: [] for s in STATS} for b in POS_BUCKETS
    }
    gids_by_pos: Dict[str, List[str]] = {b: [] for b in POS_BUCKETS}

    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

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

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)
        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", ""))
            if team == home_team:
                raw_margin = home_pts - away_pts
            elif team == away_team:
                raw_margin = away_pts - home_pts
            else:
                raw_margin = 0.0

            pos_str = positions.get(pid, "")
            bucket = _pos_bucket(pos_str)
            pos_c, pos_f, pos_g = _pos_flags(pos_str)

            feat = [
                float(player.get("pts", 0)),
                float(player.get("reb", 0)),
                float(player.get("ast", 0)),
                float(player.get("fg3m", 0)),
                float(player.get("stl", 0)),
                float(player.get("blk", 0)),
                float(player.get("tov", 0)),
                float(player.get("pf", 0)),
                float(player.get("min", 0)),
                margin,
                float(raw_margin > 0),
                pos_c,
                pos_f,
                pos_g,
            ]

            # Collect residuals
            all_present = True
            row_res: Dict[str, float] = {}
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = proj_map.get((pid, stat))
                if actual is None or proj is None:
                    all_present = False
                    break
                row_res[stat] = actual - proj

            if not all_present:
                continue

            X_by_pos[bucket].append(feat)
            for stat in STATS:
                Y_by_pos[bucket][stat].append(row_res[stat])
            gids_by_pos[bucket].append(gid)

    return X_by_pos, Y_by_pos, gids_by_pos


def train_one_stat(
    stat: str,
    bucket: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold; WF gate >= 3/4 folds beat zero-pred.

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

        train_mask = np.array(
            [gid_to_idx[gid] not in {gid_to_idx[g] for g in val_game_set}
             for gid in game_ids],
            dtype=bool,
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
            f"    [{bucket}/{stat}] fold {fi + 1}: mae={mae_model:.4f} "
            f"zero={mae_zero:.4f} delta={delta:+.4f} "
            f"{'WIN' if mae_model < mae_zero else 'loss'}"
        )

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        out_path = os.path.join(OUT_DIRS[bucket], f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{bucket}/{stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(f"  [{bucket}/{stat}] NOT SAVED ({fold_wins}/4 folds beat zero-pred)")

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
        description="Train position-stratified residual heads for R4-E."
    )
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    for d in OUT_DIRS.values():
        os.makedirs(d, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  building stratified rows ...")
    X_by_pos, Y_by_pos, gids_by_pos = build_rows(qstats_df, args.max_games, positions)

    for bucket in POS_BUCKETS:
        n = len(X_by_pos[bucket])
        print(f"  bucket {bucket}: {n} rows")

    report = {"saved": [], "skipped": []}

    for bucket in POS_BUCKETS:
        X_rows = X_by_pos[bucket]
        gids = gids_by_pos[bucket]
        for stat in STATS:
            y = Y_by_pos[bucket][stat]
            if len(y) < MIN_ROWS:
                msg = f"{bucket}/{stat}: only {len(y)} rows < {MIN_ROWS}, skip (use R2_F fallback)"
                print(f"  [{msg}]")
                report["skipped"].append({"bucket": bucket, "stat": stat,
                                          "reason": "too_few_rows", "n_rows": len(y)})
                continue
            saved, stat_report = train_one_stat(stat, bucket, X_rows, y, gids)
            if saved:
                report["saved"].append(stat_report)
            else:
                report["skipped"].append(stat_report)

    # Summary
    saved_keys = [(r["bucket"], r["stat"]) for r in report["saved"]
                  if isinstance(r, dict) and r.get("saved")]
    print(f"\n  heads saved ({len(saved_keys)}): {saved_keys or 'none'}")

    report_path = os.path.join(PROJECT_DIR, "data", "models",
                               "residual_heads_pos_training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"  report -> {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
