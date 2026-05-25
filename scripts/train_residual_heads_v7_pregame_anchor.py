"""scripts/train_residual_heads_v7_pregame_anchor.py -- R7-B residual heads.

Extends R2-F (14 features) with 1 STAT-SPECIFIC pregame anchor feature:
  pregame_proj_<stat> = OOF pergame prediction for THIS player/game/stat

Total features per head: 14 base + 1 anchor = 15 features.

Anchor lookup: data/cache/pregame_oof.parquet, joined by
(player_id, game_date, stat). Rows without an OOF match are DROPPED for that
stat (no zero-fill — we want to test signal on a clean joinable subset).

Gate: WF 4-fold GroupKFold by game_id. Save .lgb only if WF mean MAE
strictly < zero-pred on >= 3/4 folds (must beat R2-F's bar).

Output dir: data/models/residual_heads_v7_pregame_anchor/

Usage:
    python scripts/train_residual_heads_v7_pregame_anchor.py
    python scripts/train_residual_heads_v7_pregame_anchor.py --max-games 200
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
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models",
                       "residual_heads_v7_pregame_anchor")
OOF_PATH = os.path.join(PROJECT_DIR, "data", "cache", "pregame_oof.parquet")

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

BASE_FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]
# 15th feature is stat-specific -- name resolved per head at fit time.


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def load_oof_lookup() -> Dict[str, Dict[Tuple[int, str], float]]:
    """Load pregame OOF as {stat: {(pid, game_date): oof_pred}}.

    The parquet's game_id field is empty, so we key on (player_id, game_date).
    """
    import pandas as pd

    if not os.path.exists(OOF_PATH):
        raise FileNotFoundError(f"OOF cache not found at {OOF_PATH}")

    df = pd.read_parquet(OOF_PATH)
    out: Dict[str, Dict[Tuple[int, str], float]] = {s: {} for s in STATS}

    for row in df.itertuples(index=False):
        stat = str(row.stat).lower()
        if stat not in out:
            continue
        try:
            pid = int(row.player_id)
        except (TypeError, ValueError):
            continue
        date = str(row.game_date) if row.game_date else ""
        if not date:
            continue
        try:
            pred = float(row.oof_pred)
        except (TypeError, ValueError):
            continue
        out[stat][(pid, date)] = pred

    sizes = {s: len(out[s]) for s in STATS}
    print(f"  OOF lookup sizes: {sizes}")
    return out


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
    date_index: Dict[str, str],
    oof_lookup: Dict[str, Dict[Tuple[int, str], float]],
) -> Tuple[
    Dict[str, List[List[float]]],
    Dict[str, List[float]],
    Dict[str, List[str]],
    Dict[str, int],
    int,
]:
    """Build per-stat feature matrices, residual targets, and group ids.

    Returns:
        X_by_stat:   {stat: [[14 base + 1 anchor], ...]}
        Y_by_stat:   {stat: [residual, ...]}
        G_by_stat:   {stat: [game_id, ...]}
        hits_by_stat: {stat: int} (anchor join hits)
        n_candidate_rows: total endQ3 player rows considered
    """
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X_by_stat: Dict[str, List[List[float]]] = {s: [] for s in STATS}
    Y_by_stat: Dict[str, List[float]] = {s: [] for s in STATS}
    G_by_stat: Dict[str, List[str]] = {s: [] for s in STATS}
    hits_by_stat: Dict[str, int] = {s: 0 for s in STATS}
    n_candidate = 0

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

        game_date = date_index.get(gid)

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", ""))
            home_team = str(snap.get("home_team", ""))
            away_team = str(snap.get("away_team", ""))
            if team == home_team:
                raw_margin = home_pts - away_pts
            elif team == away_team:
                raw_margin = away_pts - home_pts
            else:
                raw_margin = 0.0

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

            base_feat = [
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
                float(pos_c),
                float(pos_f),
                float(pos_g),
            ]

            n_candidate += 1

            # Per-stat: only include if BOTH (a) actual+proj present and
            # (b) OOF anchor available for this (pid, date, stat).
            if not game_date:
                continue
            for stat in STATS:
                actual = actuals.get((pid, stat))
                proj = proj_map.get((pid, stat))
                if actual is None or proj is None:
                    continue
                anchor = oof_lookup[stat].get((pid, game_date))
                if anchor is None:
                    continue
                X_by_stat[stat].append(base_feat + [float(anchor)])
                Y_by_stat[stat].append(float(actual) - float(proj))
                G_by_stat[stat].append(gid)
                hits_by_stat[stat] += 1

    return X_by_stat, Y_by_stat, G_by_stat, hits_by_stat, n_candidate


def train_one_stat(
    stat: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold; save iff >= 3/4 folds beat zero-pred."""
    import lightgbm as lgb
    import numpy as np

    feature_names = BASE_FEATURE_NAMES + [f"pregame_proj_{stat}"]

    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_wins = 0
    fold_details = []

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])
        val_idx_set = {gid_to_idx[g] for g in val_game_set}

        train_mask = np.array(
            [gid_to_idx[gid] not in val_idx_set for gid in game_ids],
            dtype=bool,
        )
        val_mask = ~train_mask

        if (train_mask.sum() < LGB_PARAMS["min_child_samples"]
                or val_mask.sum() == 0):
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**LGB_PARAMS)
        model.fit(X[train_mask], y_arr[train_mask],
                  feature_name=feature_names)
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
        print(f"    [{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
              f"zero={mae_zero:.4f} delta={delta:+.4f} "
              f"{'WIN' if mae_model < mae_zero else 'loss'}")

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=feature_names)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(f"  [{stat}] NOT SAVED (only {fold_wins}/4 folds beat zero-pred)")

    return saved, {
        "stat": stat,
        "n_rows": len(y),
        "fold_wins": fold_wins,
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Train v7 residual heads with stat-specific pregame anchor.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  building game_id -> date index ...")
    from train_minute_trajectory import (
        load_player_gamelog_minutes, find_game_date_for_game)
    pid_log_index = load_player_gamelog_minutes()
    games_all = sorted(qstats_df["game_id"].unique().tolist())
    if args.max_games:
        games_all = games_all[:args.max_games]
    date_index: Dict[str, str] = {}
    for gid in games_all:
        d = find_game_date_for_game(gid, qstats_df, pid_log_index)
        if d:
            date_index[gid] = d
    print(f"  game dates resolved: {len(date_index)}/{len(games_all)}")

    print("  loading pregame OOF lookup ...")
    oof_lookup = load_oof_lookup()

    print("  building feature rows (14 base + 1 anchor per stat) ...")
    X_by, Y_by, G_by, hits, n_candidate = build_rows(
        qstats_df, args.max_games, positions, date_index, oof_lookup)

    print(f"  candidate endQ3 player rows: {n_candidate}")
    for stat in STATS:
        n = len(X_by[stat])
        rate = (100.0 * n / n_candidate) if n_candidate else 0.0
        print(f"    {stat}: {n} rows  ({rate:.1f}% join hit rate)")

    report = {
        "trained_stats": [],
        "skipped_stats": [],
        "n_features": 15,
        "n_candidate_rows": n_candidate,
        "join_hit_rate": {
            s: (round(100.0 * len(X_by[s]) / n_candidate, 2)
                if n_candidate else 0.0)
            for s in STATS
        },
    }

    for stat in STATS:
        X_rows = X_by[stat]
        y = Y_by[stat]
        gids = G_by[stat]
        if len(y) < 200:
            print(f"  [{stat}] too few rows ({len(y)}), skip")
            report["skipped_stats"].append(
                {"stat": stat, "n_rows": len(y), "reason": "too_few_rows"})
            continue
        saved, stat_report = train_one_stat(stat, X_rows, y, gids)
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {report_path}")

    trained = [r["stat"] if isinstance(r, dict) else r
               for r in report["trained_stats"]]
    print(f"  heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
