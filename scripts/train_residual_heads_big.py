"""scripts/train_residual_heads_big.py -- R5-D residual heads, bigger capacity.

Mirror of train_residual_heads.py with expanded LightGBM params:
  n_estimators=600, num_leaves=31, min_data_in_leaf=40, learning_rate=0.02,
  feature_fraction=0.9, bagging_fraction=0.8, bagging_freq=5,
  early_stopping_rounds=50 on val MAE.

Gate: WF mean MAE strictly < R2_F's WF MAE (from residual_heads/training_report.json).
Saves to data/models/residual_heads_big/{stat}.lgb only when that gate passes.
Logs best_iter per stat to training_report.json.

Usage:
    python scripts/train_residual_heads_big.py
    python scripts/train_residual_heads_big.py --max-games 200
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
OUT_DIR = os.path.join(PROJECT_DIR, "data", "models", "residual_heads_big")
R2F_REPORT_PATH = os.path.join(
    PROJECT_DIR, "data", "models", "residual_heads", "training_report.json"
)

# Expanded params for R5-D
LGB_PARAMS = {
    "n_estimators": 600,
    "learning_rate": 0.02,
    "num_leaves": 31,
    "min_child_samples": 40,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
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


def _load_r2f_thresholds() -> Dict[str, float]:
    """Load per-stat WF mean MAE from R2_F's training_report.json."""
    with open(R2F_REPORT_PATH, encoding="utf-8") as fh:
        report = json.load(fh)

    thresholds: Dict[str, float] = {}
    for entry in report.get("trained_stats", []):
        stat = entry["stat"]
        folds = [f for f in entry["folds"] if not f.get("skip")]
        if folds:
            thresholds[stat] = sum(f["mae_model"] for f in folds) / len(folds)
    return thresholds


def _pos_flags(pos_str: str) -> Tuple[int, int, int]:
    """Return (pos_C, pos_F, pos_G) one-hot from NBA position string."""
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
    """Build feature matrix X and per-stat residual vectors Y."""
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
    r2f_threshold: Optional[float],
) -> Tuple[bool, Dict]:
    """4-fold chronological GroupKFold with early stopping.

    Gate: WF mean MAE strictly < r2f_threshold (R2_F's WF mean MAE on same stat).
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
    fold_maes: List[float] = []
    fold_details = []
    best_iters: List[int] = []

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

        params = dict(LGB_PARAMS)
        early_stop = params.pop("n_estimators")  # use as max; early stop controls actual

        model = lgb.LGBMRegressor(
            **params,
            n_estimators=early_stop,
        )
        model.fit(
            X[train_mask], y_arr[train_mask],
            eval_set=[(X[val_mask], y_arr[val_mask])],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50, verbose=False),
                lgb.log_evaluation(period=-1),
            ],
            feature_name=FEATURE_NAMES,
        )

        best_iter = model.best_iteration_ if model.best_iteration_ > 0 else early_stop
        best_iters.append(best_iter)

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
            "best_iter": best_iter,
        })
        fold_maes.append(mae_model)
        print(
            f"    [{stat}] fold {fi+1}: mae={mae_model:.4f}  "
            f"zero={mae_zero:.4f}  delta={delta:+.4f}  best_iter={best_iter}"
        )

    if not fold_maes:
        print(f"  [{stat}] all folds skipped")
        return False, {"stat": stat, "skipped": True}

    wf_mean_mae = sum(fold_maes) / len(fold_maes)
    avg_best_iter = int(round(sum(best_iters) / len(best_iters))) if best_iters else None

    # Gate: strictly better than R2_F
    gate_passed = (r2f_threshold is not None) and (wf_mean_mae < r2f_threshold)
    saved = False

    threshold_str = f"{r2f_threshold:.5f}" if r2f_threshold is not None else "N/A"
    status = (
        f"wf_mean={wf_mean_mae:.5f}  r2f_threshold={threshold_str}  "
        f"avg_best_iter={avg_best_iter}  "
        f"{'GATE PASSED' if gate_passed else 'gate FAILED'}"
    )
    print(f"  [{stat}] {status}")

    if gate_passed:
        # Re-train on full data with n_estimators = avg best_iter from WF
        final_n_est = avg_best_iter if avg_best_iter and avg_best_iter > 0 else 600
        final_params = dict(LGB_PARAMS)
        final_params.pop("n_estimators", None)
        model_final = lgb.LGBMRegressor(n_estimators=final_n_est, **final_params)
        model_final.fit(X, y_arr, feature_name=FEATURE_NAMES)
        out_path = os.path.join(OUT_DIR, f"{stat}.lgb")
        model_final.booster_.save_model(out_path)
        saved = True
        print(f"  [{stat}] SAVED -> {out_path}")
    else:
        print(f"  [{stat}] NOT SAVED")

    return saved, {
        "stat": stat,
        "n_rows": len(y),
        "wf_mean_mae": round(wf_mean_mae, 5),
        "r2f_threshold": round(r2f_threshold, 5) if r2f_threshold is not None else None,
        "gate_passed": gate_passed,
        "saved": saved,
        "avg_best_iter": avg_best_iter,
        "folds": fold_details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Train big residual heads for R5-D.")
    ap.add_argument("--max-games", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("  loading R2_F thresholds ...")
    r2f_thresholds = _load_r2f_thresholds()
    for stat, thr in r2f_thresholds.items():
        print(f"    {stat}: r2f_wf_mae={thr:.5f}")

    print("  loading quarter stats ...")
    qstats_df = v1.load_quarter_stats()
    n_games_total = qstats_df["game_id"].nunique()
    print(f"  {n_games_total} games in parquet")

    print("  loading positions ...")
    from scripts.train_minute_trajectory import load_positions
    positions = load_positions()
    print(f"  {len(positions)} player positions loaded")

    print("  building feature rows ...")
    X_rows, Y, game_ids = build_rows(qstats_df, args.max_games, positions)
    print(f"  total rows: {len(X_rows)}")

    report: Dict = {"trained_stats": [], "skipped_stats": []}
    for stat in STATS:
        y = Y[stat]
        if len(y) < 200:
            print(f"  [{stat}] too few rows ({len(y)}), skip")
            report["skipped_stats"].append(stat)
            continue
        threshold = r2f_thresholds.get(stat)
        saved, stat_report = train_one_stat(stat, X_rows, y, game_ids, threshold)
        if saved:
            report["trained_stats"].append(stat_report)
        else:
            report["skipped_stats"].append(stat_report)

    report_path = os.path.join(OUT_DIR, "training_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"\n  training report -> {report_path}")

    trained = [
        r["stat"] if isinstance(r, dict) else r
        for r in report["trained_stats"]
    ]
    print(f"  heads saved: {trained or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
