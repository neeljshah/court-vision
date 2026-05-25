"""scripts/train_residual_heads_v4_pregameproxy.py -- R5-B residual heads.

Extends R2-F (train_residual_heads.py) with 7 pregame proxy features:
  l20_pts_mean, l20_reb_mean, l20_ast_mean, l20_fg3m_mean,
  l20_stl_mean, l20_blk_mean, l20_tov_mean

Total features: 14 (R2-F base) + 7 = 21.

L20 means are computed walk-forward (strictly before game_date) using
data/nba/gamelog_<pid>_<season>.json.  If fewer than 5 prior games exist
the feature is set to 0 (model learns the zero pattern).

Gate: WF 4-fold GroupKFold by game_id.  Save .lgb only if WF mean MAE
strictly < zero-pred on >= 3/4 folds.

Output dir: data/models/residual_heads_v4_pregameproxy/

Usage:
    python scripts/train_residual_heads_v4_pregameproxy.py
    python scripts/train_residual_heads_v4_pregameproxy.py --max-games 200
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
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_v4_pregameproxy")

# Gamelog stat keys (upper-case in JSON)
_GAMELOG_STAT_KEYS = {
    "pts": "PTS",
    "reb": "REB",
    "ast": "AST",
    "fg3m": "FG3M",
    "stl": "STL",
    "blk": "BLK",
    "tov": "TOV",
}

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
PROXY_FEATURE_NAMES = [
    "l20_pts_mean", "l20_reb_mean", "l20_ast_mean", "l20_fg3m_mean",
    "l20_stl_mean", "l20_blk_mean", "l20_tov_mean",
]
FEATURE_NAMES = BASE_FEATURE_NAMES + PROXY_FEATURE_NAMES  # 21 total


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def load_gamelog_stat_index() -> Dict[int, List[Tuple[str, Dict[str, float]]]]:
    """Load all gamelog JSONs into {pid: [(date_iso, {stat: val}), ...]}.

    Each entry is (date_iso, {pts, reb, ast, fg3m, stl, blk, tov}).
    Lists are sorted chronologically ascending.
    """
    import glob

    from train_minute_trajectory import _parse_gamelog_date

    out: Dict[int, List[Tuple[str, Dict[str, float]]]] = {}
    pattern = os.path.join(PROJECT_DIR, "data", "nba", "gamelog_*.json")
    for fp in glob.glob(pattern):
        base = os.path.basename(fp)
        parts = base.split("_")
        if len(parts) < 2:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                rows = json.load(fh) or []
        except Exception:
            continue
        for row in rows:
            d = _parse_gamelog_date(row.get("GAME_DATE"))
            if d is None:
                continue
            try:
                mins = float(row.get("MIN") or 0)
            except (TypeError, ValueError):
                mins = 0.0
            if mins < 1.0:
                continue
            stat_vals: Dict[str, float] = {}
            for stat, key in _GAMELOG_STAT_KEYS.items():
                try:
                    stat_vals[stat] = float(row.get(key) or 0)
                except (TypeError, ValueError):
                    stat_vals[stat] = 0.0
            out.setdefault(pid, []).append((d, stat_vals))
    for pid in out:
        out[pid].sort(key=lambda x: x[0])
    return out


def l20_means(
    pid: int,
    target_date: Optional[str],
    gamelog_index: Dict[int, List[Tuple[str, Dict[str, float]]]],
    window: int = 20,
    min_games: int = 5,
) -> Dict[str, float]:
    """Return l20 means for all 7 stats, strictly before target_date.

    Returns zeros if fewer than min_games prior entries exist.
    """
    zero = {s: 0.0 for s in STATS}
    log = gamelog_index.get(pid)
    if not log:
        return zero
    if target_date:
        prior = [(d, sv) for (d, sv) in log if d < target_date][-window:]
    else:
        prior = log[-window:]
    if len(prior) < min_games:
        return zero
    result: Dict[str, float] = {}
    for stat in STATS:
        vals = [sv[stat] for (_, sv) in prior]
        result[stat] = sum(vals) / len(vals)
    return result


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
    gamelog_index: Dict[int, List[Tuple[str, Dict[str, float]]]],
    date_index: Dict[str, str],
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str]]:
    """Build 21-feature rows and per-stat residual targets."""
    games = sorted(qstats_df["game_id"].unique().tolist())
    if max_games:
        games = games[:max_games]

    X: List[List[float]] = []
    Y: Dict[str, List[float]] = {s: [] for s in STATS}
    game_ids_out: List[str] = []

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

        game_date = date_index.get(gid)  # may be None

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

            # -- 7 pregame proxy features --
            proxy = l20_means(pid, game_date, gamelog_index)

            feat = [
                # 14 base features
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
                # 7 pregame proxy features
                proxy["pts"],
                proxy["reb"],
                proxy["ast"],
                proxy["fg3m"],
                proxy["stl"],
                proxy["blk"],
                proxy["tov"],
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

    return X, Y, game_ids_out


def train_one_stat(
    stat: str,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
) -> Tuple[bool, Dict]:
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
        description="Train R5-B residual heads with l20 pregame proxy features.")
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

    print("  loading gamelog stat index ...")
    gamelog_index = load_gamelog_stat_index()
    print(f"  {len(gamelog_index)} players in gamelog index")

    print("  building game_id -> date index ...")
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

    print("  building feature rows (21 features) ...")
    X_rows, Y, game_ids = build_rows(
        qstats_df, args.max_games, positions, gamelog_index, date_index)
    print(f"  total rows: {len(X_rows)}")

    report = {"trained_stats": [], "skipped_stats": [], "n_features": len(FEATURE_NAMES)}
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
