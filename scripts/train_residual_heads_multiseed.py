"""scripts/train_residual_heads_multiseed.py -- R3-H multi-seed residual heads.

Operationalises feedback_seed_stability_check.md: trains 7 residual heads
(one per stat) for each of 5 seeds.  At inference the 5 predictions are
averaged, replacing R2_F's single-seed (42) prediction.

Model dir layout:
    data/models/residual_heads_seeds/seed_42/{stat}.lgb
    data/models/residual_heads_seeds/seed_7/{stat}.lgb
    ...

Hyperparams:   identical to R2_F (regression_l1, n_est=200, lr=0.03,
               num_leaves=15, min_child_samples=80).
Seed override: random_state, bagging_seed, feature_fraction_seed all set
               to the loop seed.
Target:        actual - cycle_110_projection  (same as R2_F — not post-R2_F).
Gate per seed/stat: WF mean MAE strictly < zero-pred baseline on >= 3/4 folds.
               Only saves if gate passes.

Usage:
    python scripts/train_residual_heads_multiseed.py
    python scripts/train_residual_heads_multiseed.py --max-games 200
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
SEEDS = [42, 7, 13, 99, 256]
OUT_BASE = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_seeds")

_BASE_PARAMS = {
    "n_estimators": 200,
    "learning_rate": 0.03,
    "num_leaves": 15,
    "min_child_samples": 80,
    "objective": "regression_l1",
    "verbosity": -1,
    "n_jobs": -1,
}

FEATURE_NAMES = [
    "cur_pts", "cur_reb", "cur_ast", "cur_fg3m",
    "cur_stl", "cur_blk", "cur_tov", "cur_pf",
    "min_through_q3", "score_margin_abs", "is_leading",
    "pos_C", "pos_F", "pos_G",
]


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
    """Build feature matrix X and per-stat residual vectors Y.

    Target = actual - BASELINE(cycle_110_projection).
    """
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
    seed: int,
    X_rows: List[List[float]],
    y: List[float],
    game_ids: List[str],
    out_dir: str,
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold, WF gate >= 3/4 folds beat zero-pred.

    Returns (saved: bool, report: dict).
    """
    import lightgbm as lgb
    import numpy as np

    params = dict(_BASE_PARAMS)
    params["random_state"] = seed
    params["bagging_seed"] = seed
    params["feature_fraction_seed"] = seed

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

        if train_mask.sum() < params["min_child_samples"] or val_mask.sum() == 0:
            fold_details.append({"fold": fi + 1, "skip": True})
            continue

        model = lgb.LGBMRegressor(**params)
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
        print(f"    [seed={seed} {stat}] fold {fi+1}: mae={mae_model:.4f} "
              f"zero={mae_zero:.4f} delta={delta:+.4f} "
              f"{'WIN' if mae_model < mae_zero else 'loss'}")

    gate_passed = fold_wins >= 3
    saved = False
    if gate_passed:
        model_final = lgb.LGBMRegressor(**params)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [seed={seed} {stat}] SAVED -> {out_path}  ({fold_wins}/4 folds won)")
    else:
        print(f"  [seed={seed} {stat}] NOT SAVED (only {fold_wins}/4 folds beat zero-pred)")

    return saved, {
        "seed": seed,
        "stat": stat,
        "n_rows": len(y),
        "fold_wins": fold_wins,
        "gate_passed": gate_passed,
        "saved": saved,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train multi-seed residual heads (R3-H).")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    print("  loading quarter stats ...", flush=True)
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet", flush=True)

    print("  loading positions ...", flush=True)
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded", flush=True)

    print("  building feature rows (shared across all seeds) ...", flush=True)
    X_rows, Y, game_ids = build_rows(qstats_df, args.max_games, positions)
    print(f"  total rows: {len(X_rows)}", flush=True)

    all_reports: List[Dict] = []
    summary_rows: List[str] = []

    for seed in SEEDS:
        seed_dir = os.path.join(OUT_BASE, f"seed_{seed}")
        os.makedirs(seed_dir, exist_ok=True)
        print(f"\n=== SEED {seed} ===", flush=True)
        seed_saved = []
        for stat in STATS:
            y = Y[stat]
            if len(y) < 200:
                print(f"  [seed={seed} {stat}] too few rows ({len(y)}), skip")
                continue
            saved, report = train_one_stat(stat, seed, X_rows, y, game_ids, seed_dir)
            all_reports.append(report)
            if saved:
                seed_saved.append(stat)
        summary_rows.append(
            f"seed={seed:>3}  saved={len(seed_saved)}/7  stats={seed_saved or 'none'}"
        )

    # Write aggregated report
    report_path = os.path.join(OUT_BASE, "training_report_multiseed.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(all_reports, fh, indent=2)
    print(f"\n  training report -> {report_path}", flush=True)

    print("\n=== SUMMARY ===", flush=True)
    for row in summary_rows:
        print(f"  {row}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
