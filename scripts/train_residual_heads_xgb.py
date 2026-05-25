"""scripts/train_residual_heads_xgb.py -- R4-H XGBoost residual heads (loop 5).

Mirrors train_residual_heads.py (LGB) but uses XGBoost.  Trains 7 XGB heads
on the RESIDUAL between the cycle-110 live_engine projection (endQ3) and the
actual full-game total.  Only trains stats where the matching LGB head was
saved (residual_heads/{stat}.lgb must exist).

Features (14): same as R2_F / train_residual_heads.py.

Usage:
    python scripts/train_residual_heads_xgb.py
    python scripts/train_residual_heads_xgb.py --max-games 200
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
LGB_HEAD_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads")
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_xgb")

XGB_PARAMS = dict(
    n_estimators=200,
    learning_rate=0.03,
    max_depth=5,
    min_child_weight=20,
    reg_alpha=0.5,
    reg_lambda=0.5,
    objective="reg:absoluteerror",
    tree_method="hist",
    random_state=42,
    n_jobs=-1,
)

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


def _lgb_head_exists(stat: str) -> bool:
    return os.path.exists(os.path.join(LGB_HEAD_DIR, f"{stat}.lgb"))


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    p = (pos_str or "").upper()
    if "C" in p and "F" not in p and "G" not in p:
        return 1, 0, 0
    if "F" in p and "C" not in p and "G" not in p:
        return 0, 1, 0
    if "G" in p and "F" not in p and "C" not in p:
        return 0, 0, 1
    return 0, 0, 0


def build_rows(
    qstats_df,
    max_games: Optional[int],
    positions: Dict[int, str],
) -> Tuple[List[List[float]], Dict[str, List[float]], List[str]]:
    """Build feature matrix X and per-stat residual vectors Y (identical to LGB trainer)."""
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
    """4-fold chronological WF gate: >= 3/4 folds beat zero-pred baseline."""
    import xgboost as xgb
    import numpy as np

    X = np.array(X_rows, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)

    unique_games = list(dict.fromkeys(game_ids))
    gid_to_idx = {gid: i for i, gid in enumerate(unique_games)}
    groups = np.array([gid_to_idx[gid] for gid in game_ids], dtype=np.int32)  # noqa: F841

    n_groups = len(unique_games)
    fold_size = max(1, n_groups // 4)
    fold_wins = 0
    fold_details = []

    for fi in range(4):
        lo = fi * fold_size
        hi = n_groups if fi == 3 else (fi + 1) * fold_size
        val_game_set = set(unique_games[lo:hi])

        val_game_idx = {gid_to_idx[g] for g in val_game_set}
        train_mask = np.array(
            [gid_to_idx[gid] not in val_game_idx for gid in game_ids], dtype=bool
        )
        val_mask = ~train_mask

        if train_mask.sum() < XGB_PARAMS["min_child_weight"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = xgb.XGBRegressor(**XGB_PARAMS, verbosity=0)
        model.fit(X[train_mask], y_arr[train_mask])
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
            f"    [{stat}] fold {fi+1}: mae_model={mae_model:.4f} "
            f"zero={mae_zero:.4f} delta={delta:+.4f} "
            f"{'WIN' if mae_model < mae_zero else 'loss'}"
        )

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = xgb.XGBRegressor(**XGB_PARAMS, verbosity=0)
        model_final.fit(X, y_arr)
        out_path = os.path.join(OUT_DIR, f"{stat}.json")
        model_final.get_booster().save_model(out_path)
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
    ap = argparse.ArgumentParser(description="Train XGB residual heads for R4-H ensemble.")
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

    # Only train stats where the LGB head was saved (apples-to-apples ensemble)
    stats_to_train = [s for s in STATS if _lgb_head_exists(s)]
    skipped_no_lgb = [s for s in STATS if not _lgb_head_exists(s)]
    if skipped_no_lgb:
        print(f"  skipping (no LGB head): {skipped_no_lgb}")
    print(f"  will train XGB for: {stats_to_train}")

    print("  building feature rows ...")
    X_rows, Y, game_ids = build_rows(qstats_df, args.max_games, positions)
    print(f"  total rows: {len(X_rows)}")

    report: Dict = {
        "trained_stats": [],
        "skipped_stats": list(skipped_no_lgb),
    }
    for stat in stats_to_train:
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

    trained = [r["stat"] if isinstance(r, dict) else r for r in report["trained_stats"]]
    print(f"  XGB heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
