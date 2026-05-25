"""scripts/train_residual_heads_v5_oppstat.py -- R5-E residual heads.

Extends R2-F (train_residual_heads.py) with 7 opponent-allowed L5 features:
  opp_l5_{pts,reb,ast,fg3m,stl,blk,tov}_allowed

These are the opponent team's mean stat totals allowed over their last 5 games
(walk-forward, shift(1)) from data/opp_l5_per_stat.parquet.

Total features: 14 (R2-F base) + 7 = 21.

The opponent for a player is the OTHER team in the snapshot (snap["away_team"]
if player.team == snap["home_team"], else snap["home_team"]).

Lookup key: (opp_team_abbreviation, game_date).  If no match, fills 0.0.

Gate: WF 4-fold GroupKFold by game_id (chronological).
Save .lgb only if WF mean MAE strictly < zero-pred on >= 3/4 folds.

Output dir: data/models/residual_heads_v5_oppstat/

Usage:
    python scripts/train_residual_heads_v5_oppstat.py
    python scripts/train_residual_heads_v5_oppstat.py --max-games 200
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
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v5_oppstat")
OPP_L5_PATH = os.path.join(PROJECT_DIR, "data", "opp_l5_per_stat.parquet")

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
OPP_FEATURE_NAMES = [
    "opp_l5_pts_allowed", "opp_l5_reb_allowed", "opp_l5_ast_allowed",
    "opp_l5_fg3m_allowed", "opp_l5_stl_allowed", "opp_l5_blk_allowed",
    "opp_l5_tov_allowed",
]
FEATURE_NAMES = BASE_FEATURE_NAMES + OPP_FEATURE_NAMES  # 21 total


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def load_opp_l5_index() -> Dict[Tuple[str, str], Dict[str, float]]:
    """Load opp_l5_per_stat.parquet into a fast lookup dict.

    Returns {(team_abbreviation, game_date_iso): {stat: float}}.
    """
    import pandas as pd

    if not os.path.exists(OPP_L5_PATH):
        print(f"  WARN: {OPP_L5_PATH} not found — opp features will be all zeros")
        return {}

    df = pd.read_parquet(OPP_L5_PATH)
    out: Dict[Tuple[str, str], Dict[str, float]] = {}
    for _, row in df.iterrows():
        key = (str(row["team_abbreviation"]), str(row["game_date"]))
        out[key] = {
            s: float(row[f"opp_l5_{s}_allowed"])
            for s in STATS
            if f"opp_l5_{s}_allowed" in row.index
        }
    return out


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
    opp_l5_index: Dict[Tuple[str, str], Dict[str, float]],
    date_index: Dict[str, str],
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str]]:
    """Build 21-feature rows and per-stat residual targets."""
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X: List[List[float]] = []
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []
    n_opp_hits = n_opp_miss = 0

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

        game_date = date_index.get(gid)  # ISO string or None
        home_team = str(snap.get("home_team", ""))
        away_team = str(snap.get("away_team", ""))

        home_pts = float(snap.get("home_score", 0))
        away_pts = float(snap.get("away_score", 0))
        margin = abs(home_pts - away_pts)

        for player in snap.get("players", []):
            try:
                pid = int(player["player_id"])
            except (TypeError, ValueError):
                continue

            team = str(player.get("team", ""))
            if team == home_team:
                raw_margin = home_pts - away_pts
                opp_team = away_team
            elif team == away_team:
                raw_margin = away_pts - home_pts
                opp_team = home_team
            else:
                raw_margin = 0.0
                opp_team = ""

            pos_c, pos_f, pos_g = _pos_flags(positions.get(pid, ""))

            # -- 7 opponent-allowed L5 features --
            opp_key = (opp_team, game_date) if (opp_team and game_date) else None
            opp_feats = opp_l5_index.get(opp_key, {}) if opp_key else {}
            if opp_feats:
                n_opp_hits += 1
            else:
                n_opp_miss += 1

            feat = [
                # 14 base features (same as R2-F)
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
                # 7 opp-allowed L5 features
                opp_feats.get("pts", 0.0),
                opp_feats.get("reb", 0.0),
                opp_feats.get("ast", 0.0),
                opp_feats.get("fg3m", 0.0),
                opp_feats.get("stl", 0.0),
                opp_feats.get("blk", 0.0),
                opp_feats.get("tov", 0.0),
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

            X.append(feat)
            for stat in STATS:
                Y[stat].append(row_residuals[stat])
            game_ids_out.append(gid)

    total = n_opp_hits + n_opp_miss
    hit_pct = 100 * n_opp_hits / total if total > 0 else 0
    print(f"  opp L5 lookup: {n_opp_hits}/{total} hits ({hit_pct:.1f}%)")
    return X, Y, game_ids_out


def train_one_stat(
    stat: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold, WF gate >= 3/4 folds beat zero-pred."""
    import lightgbm as lgb
    import numpy as np

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

        train_mask = np.array(
            [gid_to_idx[gid] not in {gid_to_idx[g] for g in val_game_set}
             for gid in game_ids], dtype=bool)
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
        print(f"    [{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
              f"zero={mae_zero:.4f} delta={delta:+.4f} "
              f"{'WIN' if mae_model < mae_zero else 'loss'}")

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**LGB_PARAMS)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
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
        description="Train R5-E residual heads with opponent-allowed L5 features.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading quarter stats ...", flush=True)
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...", flush=True)
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  loading opp L5 index ...", flush=True)
    opp_l5_index = load_opp_l5_index()
    print(f"  {len(opp_l5_index)} (team, date) entries in opp L5 index")

    print("  building game_id -> date index ...", flush=True)
    from train_minute_trajectory import load_player_gamelog_minutes, find_game_date_for_game
    pid_log_index = load_player_gamelog_minutes()
    games_all = sorted(qstats_df["game_id"].unique().tolist())
    if args.max_games:
        games_all = games_all[:args.max_games]
    date_index: Dict[str, str] = {}
    for gid in games_all:
        d = find_game_date_for_game(gid, qstats_df, pid_log_index)
        if d:
            date_index[gid] = d
    n_dated = sum(1 for v in date_index.values() if v)
    print(f"  game dates resolved: {n_dated}/{len(games_all)}")

    print("  building feature rows (21 features) ...", flush=True)
    X_rows, Y, game_ids = build_rows(
        qstats_df, args.max_games, positions, opp_l5_index, date_index)
    print(f"  total rows: {len(X_rows)}")

    report = {
        "trained_stats": [],
        "skipped_stats": [],
        "n_features": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
    }
    for stat in STATS:
        y = Y[stat]
        if len(y) < 200:
            print(f"  [{stat}] too few rows ({len(y)}), skip")
            report["skipped_stats"].append(stat)
            continue
        saved, stat_report = train_one_stat(stat, X_rows, y, game_ids)
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
