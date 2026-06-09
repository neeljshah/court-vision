"""
test_cv_per_stat_deepdive.py — Per-stat CV feature deep-dive diagnostic.

Experiments:
  1. REB: feature importance + ablation (which subset drives the -0.0037 SHIP?)
  2. PTS: feature importance + inverse ablation + noisy-feature candidates
  3. Combined recommendation

Run:
    python scripts/test_cv_per_stat_deepdive.py

DO NOT modify src/ files or other test_cv_*.py scripts.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

warnings.filterwarnings("ignore")

os.environ.pop("PROP_USE_CV", None)

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import numpy as np

from src.prediction.prop_pergame import STATS, build_pergame_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

ALL_CV_COLS = [
    "avg_defender_distance",
    "contested_shot_rate",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
    "avg_spacing",
    "made_pct",
    "avg_shot_clock_at_shot",
    "n_shots_tracked",
    "shots_per_possession",
    "possession_duration_avg",
    "play_type_transition_pct",
    "play_type_drive_pct",
    "play_type_isolation_pct",
    "play_type_post_pct",
    "avg_contest_arm_angle",
    "avg_closeout_speed",
    "avg_fatigue_proxy",
    "catch_shoot_pct",
    "avg_dribble_count",
    "second_chance_rate",
    "avg_shot_distance",
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

N_SPLITS = 4
TARGET_STATS = ["reb", "pts"]

# ---------------------------------------------------------------------------
# Feature group definitions for ablation experiments
# ---------------------------------------------------------------------------
POSITION_FEATS = [
    "paint_dwell_pct",
    "shot_zone_paint_pct",
    "shot_zone_mid_range_pct",
    "shot_zone_3pt_pct",
]

POSSESSION_FEATS = [
    "touches_per_game",
    "shots_per_possession",
    "possession_duration_avg",
    "second_chance_rate",
    "n_shots_tracked",
]

MECHANICS_FEATS = [
    "contested_shot_rate",
    "avg_contest_arm_angle",
    "avg_closeout_speed",
    "catch_shoot_pct",
    "avg_dribble_count",
]

PLAYTYPE_FEATS = [
    "play_type_transition_pct",
    "play_type_drive_pct",
    "play_type_post_pct",
    "play_type_isolation_pct",
]

TIER1_FEATS = [
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# Candidate noisy features for PTS Step 2c
NOISY_CANDIDATES = [
    "defender_approach_speed",
    "preshot_velocity_peak",
    "avg_contest_arm_angle",
    "avg_fatigue_proxy",
    "contested_shot_rate",
]


# ---------------------------------------------------------------------------
# Data loading helpers (same logic as test_cv_isolated.py)
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    gd: Dict[str, str] = {}
    import glob as _glob
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    for fpath in _glob.glob(os.path.join(nba_dir, "season_games_*.json")):
        try:
            with open(fpath) as f:
                data = json.load(f)
            rows = data.get("rows", data) if isinstance(data, dict) else data
            for row in rows:
                if isinstance(row, dict) and "game_id" in row and "game_date" in row:
                    gd[row["game_id"]] = row["game_date"]
        except Exception as e:
            print(f"  [warn] could not load {fpath}: {e}")
    return gd


def _load_cv_data(game_date_map: Dict[str, str]) -> Dict[int, List[Tuple[str, str, float]]]:
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
    ).fetchall()
    conn.close()

    by_player: Dict[int, List[Tuple[str, str, float]]] = defaultdict(list)
    n_resolved = 0
    n_missing_date = 0
    for player_id, game_id, feature_name, feature_value in rows:
        gdate = game_date_map.get(game_id)
        if gdate is None:
            n_missing_date += 1
            continue
        by_player[player_id].append((gdate, feature_name, feature_value))
        n_resolved += 1

    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    print(f"  CV rows resolved: {n_resolved}  |  missing game_date: {n_missing_date}")
    return by_player


def _compute_last5_cv(
    player_id: int,
    row_date: str,
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[Dict[str, float], int]:
    history = by_player.get(player_id, [])
    if not history:
        return {}, 0

    lo, hi = 0, len(history)
    while lo < hi:
        mid = (lo + hi) // 2
        if history[mid][0] < row_date:
            lo = mid + 1
        else:
            hi = mid
    cutoff_idx = lo

    if cutoff_idx == 0:
        return {}, 0

    feature_sums: Dict[str, float] = defaultdict(float)
    feature_counts: Dict[str, int] = defaultdict(int)
    seen_dates: list = []

    for i in range(cutoff_idx - 1, -1, -1):
        gdate, fname, fval = history[i]
        if gdate not in seen_dates:
            seen_dates.append(gdate)
        if len(seen_dates) > 5:
            break
        feature_sums[fname] += fval
        feature_counts[fname] += 1

    n_games = len(seen_dates)
    avgs = {fname: feature_sums[fname] / feature_counts[fname] for fname in feature_sums}
    return avgs, n_games


def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 10000 == 0 and i > 0:
            print(f"    CV pre-compute: {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        avgs, n_games = _compute_last5_cv(pid, rdate, by_player)
        cv_n_games[i] = n_games
        for fname, val in avgs.items():
            idx = feat_idx.get(fname)
            if idx is not None:
                cv_matrix[i, idx] = val

    return cv_matrix, cv_n_games


# ---------------------------------------------------------------------------
# Training helper with optional feature importance capture
# ---------------------------------------------------------------------------
def _train_fold_with_importance(
    stat: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_ho: np.ndarray,
    y_ho: np.ndarray,
    sw: np.ndarray,
    feature_names: List[str] | None = None,
    capture_importance: bool = False,
) -> Tuple[float, Dict[str, float] | None]:
    """Train XGB+LGB, NNLS blend on val, return (holdout MAE, xgb_importance_or_None)."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4

    xgb_m = xgb.XGBRegressor(
        n_estimators=400,
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=2.0,
        reg_alpha=0.5,
        gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=30,
        eval_metric="mae",
        verbosity=0,
        tree_method="hist",
        device="cuda",
    )
    xgb_m.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        verbose=False,
    )

    lgb_m = lgb.LGBMRegressor(
        n_estimators=400,
        max_depth=depth,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1,
        verbosity=-1,
    )
    lgb_m.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )

    xv = xgb_m.predict(X_val)
    lv = lgb_m.predict(X_val)
    xh = xgb_m.predict(X_ho)
    lh = lgb_m.predict(X_ho)

    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    mae = float(mean_absolute_error(y_ho, preds))

    importance = None
    if capture_importance and feature_names is not None:
        scores = xgb_m.get_booster().get_score(importance_type="gain")
        # Map f0, f1, ... back to feature names
        importance = {}
        for k, v in scores.items():
            if k.startswith("f"):
                try:
                    fidx = int(k[1:])
                    fname = feature_names[fidx] if fidx < len(feature_names) else k
                    importance[fname] = float(v)
                except ValueError:
                    importance[k] = float(v)

    return mae, importance


def _build_X_for_config(
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
    cv_feature_names: List[str],
    base_cols: List[str],
) -> Tuple[np.ndarray, List[str]]:
    """Build augmented X matrix + feature name list for a given CV config."""
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    if not cv_feature_names:
        return X_base, list(base_cols)

    cv_cols_idx = [feat_idx[f] for f in cv_feature_names if f in feat_idx]
    cv_extra = cv_matrix[:, cv_cols_idx]
    cv_ngames_col = cv_n_games.reshape(-1, 1).astype(float)
    X_aug = np.hstack([X_base, cv_extra, cv_ngames_col])
    aug_names = list(base_cols) + [cv_feature_names[i] for i in range(len(cv_cols_idx))] + ["cv_n_games_cv"]
    return X_aug, aug_names


# ---------------------------------------------------------------------------
# Core walk-forward runner for a single (stat, config_list) pair
# Returns: (fold_maes, accumulated_importance_dict_or_None)
# ---------------------------------------------------------------------------
def _run_wf_single(
    stat: str,
    rows: List[dict],
    X_aug: np.ndarray,
    feature_names: List[str],
    capture_importance: bool = False,
) -> Tuple[List[float], Dict[str, float] | None]:
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]
    fold_maes: List[float] = []
    accumulated_importance: Dict[str, float] = defaultdict(float)
    importance_folds = 0

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            continue

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr = y[:tr_end]
        y_val = y[tr_end:va_end]
        y_ho = y[va_end:te_end]

        X_tr = X_aug[:tr_end]
        X_val = X_aug[tr_end:va_end]
        X_ho = X_aug[va_end:te_end]

        mae, imp = _train_fold_with_importance(
            stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw,
            feature_names=feature_names,
            capture_importance=capture_importance and fold_idx == 0,
        )
        fold_maes.append(mae)
        if imp:
            for k, v in imp.items():
                accumulated_importance[k] += v
            importance_folds += 1

    final_importance = dict(accumulated_importance) if importance_folds > 0 else None
    return fold_maes, final_importance


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------
def run_experiments(
    rows: List[dict],
    base_cols: List[str],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    results = {}

    for stat in TARGET_STATS:
        print(f"\n{'='*60}")
        print(f"STAT: {stat.upper()}")
        print(f"{'='*60}")

        stat_results = {}

        # ------------------------------------------------------------------
        # Step A: baseline (no CV)
        # ------------------------------------------------------------------
        print(f"\n  [baseline] running ...")
        t0 = time.time()
        bl_maes, _ = _run_wf_single(stat, rows, X_base, list(base_cols))
        bl_mean = float(np.mean(bl_maes))
        stat_results["baseline"] = {
            "mae": bl_mean,
            "fold_maes": bl_maes,
            "delta_vs_baseline": 0.0,
            "folds_better": 0,
        }
        print(f"  baseline MAE = {bl_mean:.4f}  ({time.time()-t0:.1f}s)")

        # ------------------------------------------------------------------
        # Step B: all_cv_27 + capture feature importance
        # ------------------------------------------------------------------
        print(f"\n  [all_cv_27] running with importance capture ...")
        t0 = time.time()
        X_27, names_27 = _build_X_for_config(
            X_base, cv_matrix, cv_n_games, ALL_CV_COLS, base_cols
        )
        cv27_maes, importance = _run_wf_single(
            stat, rows, X_27, names_27, capture_importance=True
        )
        cv27_mean = float(np.mean(cv27_maes))
        delta_cv27 = cv27_mean - bl_mean
        folds_better_cv27 = sum(1 for bm, cm in zip(bl_maes, cv27_maes) if cm < bm)
        stat_results["all_cv_27"] = {
            "mae": cv27_mean,
            "fold_maes": cv27_maes,
            "delta_vs_baseline": round(delta_cv27, 4),
            "folds_better": folds_better_cv27,
        }
        print(f"  all_cv_27 MAE = {cv27_mean:.4f}  delta={delta_cv27:+.4f}  "
              f"folds_better={folds_better_cv27}/4  ({time.time()-t0:.1f}s)")

        # Sort and save feature importance
        top_importance: List[Tuple[str, float]] = []
        if importance:
            # Filter to only CV features
            cv_feat_set = set(ALL_CV_COLS) | {"cv_n_games_cv"}
            cv_importance = {k: v for k, v in importance.items() if k in cv_feat_set}
            all_importance_sorted = sorted(importance.items(), key=lambda x: -x[1])
            cv_importance_sorted = sorted(cv_importance.items(), key=lambda x: -x[1])
            top_importance = all_importance_sorted[:20]

            print(f"\n  --- Top-10 CV features by XGB gain (all_cv_27, fold 1) ---")
            for rank, (fname, gain) in enumerate(cv_importance_sorted[:10], 1):
                print(f"    {rank:2d}. {fname:<35s} {gain:.2f}")

            stat_results["xgb_importance_all"] = dict(all_importance_sorted)
            stat_results["xgb_importance_cv_only"] = dict(cv_importance_sorted)
            stat_results["top10_cv_features"] = cv_importance_sorted[:10]

            # Top-5 CV features for dynamic ablation
            top5_cv = [f for f, _ in cv_importance_sorted[:5]]
            stat_results["top5_cv_by_importance"] = top5_cv
        else:
            top5_cv = []
            stat_results["top5_cv_by_importance"] = []
            print("  [warn] No importance captured")

        # ------------------------------------------------------------------
        # Step C: Ablation configs (shared structure for REB and PTS)
        # ------------------------------------------------------------------
        if stat == "reb":
            ablation_configs = {
                "position_only": POSITION_FEATS,
                "possession_only": POSSESSION_FEATS,
                "mechanics_only": MECHANICS_FEATS,
                "playtype_only": PLAYTYPE_FEATS,
                "tier1_only": TIER1_FEATS,
                "top5_by_importance": top5_cv,
            }
        else:  # pts — inverse ablation (drop groups)
            ablation_configs = {
                "drop_position": [f for f in ALL_CV_COLS if f not in POSITION_FEATS],
                "drop_possession": [f for f in ALL_CV_COLS if f not in POSSESSION_FEATS],
                "drop_mechanics": [f for f in ALL_CV_COLS if f not in MECHANICS_FEATS],
                "drop_playtype": [f for f in ALL_CV_COLS if f not in PLAYTYPE_FEATS],
                "drop_tier1": [f for f in ALL_CV_COLS if f not in TIER1_FEATS],
            }

        print(f"\n  --- Ablation configs ---")
        for cfg_name, cv_feats in ablation_configs.items():
            t0 = time.time()
            X_abl, names_abl = _build_X_for_config(
                X_base, cv_matrix, cv_n_games, cv_feats, base_cols
            )
            fold_maes, _ = _run_wf_single(stat, rows, X_abl, names_abl)
            cfg_mean = float(np.mean(fold_maes))
            delta_vs_bl = cfg_mean - bl_mean
            delta_vs_cv27 = cfg_mean - cv27_mean
            folds_better = sum(1 for bm, cm in zip(bl_maes, fold_maes) if cm < bm)

            stat_results[cfg_name] = {
                "mae": cfg_mean,
                "fold_maes": fold_maes,
                "delta_vs_baseline": round(delta_vs_bl, 4),
                "delta_vs_all_cv_27": round(delta_vs_cv27, 4),
                "folds_better": folds_better,
                "n_cv_feats": len(cv_feats),
            }
            print(f"  [{cfg_name:<25s}] MAE={cfg_mean:.4f}  "
                  f"delta_bl={delta_vs_bl:+.4f}  delta_cv27={delta_vs_cv27:+.4f}  "
                  f"folds_better={folds_better}/4  ({time.time()-t0:.1f}s)")

        # ------------------------------------------------------------------
        # Step D (PTS only): Noisy feature candidates — add ONE at a time
        # ------------------------------------------------------------------
        if stat == "pts":
            print(f"\n  --- PTS noisy-feature candidates (baseline + 1 feature each) ---")
            for noisy_feat in NOISY_CANDIDATES:
                if noisy_feat not in ALL_CV_COLS:
                    print(f"  [skip] {noisy_feat} not in ALL_CV_COLS")
                    continue
                t0 = time.time()
                X_1f, names_1f = _build_X_for_config(
                    X_base, cv_matrix, cv_n_games, [noisy_feat], base_cols
                )
                fold_maes, _ = _run_wf_single(stat, rows, X_1f, names_1f)
                cfg_mean = float(np.mean(fold_maes))
                delta_vs_bl = cfg_mean - bl_mean
                folds_better = sum(1 for bm, cm in zip(bl_maes, fold_maes) if cm < bm)

                key = f"noisy_{noisy_feat}"
                stat_results[key] = {
                    "mae": cfg_mean,
                    "fold_maes": fold_maes,
                    "delta_vs_baseline": round(delta_vs_bl, 4),
                    "folds_better": folds_better,
                    "n_cv_feats": 1,
                }
                direction = "HURTS" if delta_vs_bl > 0.001 else ("helps" if delta_vs_bl < -0.001 else "neutral")
                print(f"  [+{noisy_feat:<35s}] MAE={cfg_mean:.4f}  "
                      f"delta_bl={delta_vs_bl:+.4f}  folds_better={folds_better}/4  [{direction}]  "
                      f"({time.time()-t0:.1f}s)")

        results[stat] = stat_results

    return results


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------
def _format_report(results: dict) -> str:
    lines: List[str] = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("## X1c Per-Stat Deep Dive — Final Report")
    lines.append("=" * 70)

    for stat in TARGET_STATS:
        stat_res = results.get(stat, {})
        bl_mae = stat_res.get("baseline", {}).get("mae", float("nan"))
        cv27 = stat_res.get("all_cv_27", {})
        cv27_mae = cv27.get("mae", float("nan"))
        cv27_delta = cv27.get("delta_vs_baseline", float("nan"))
        cv27_fb = cv27.get("folds_better", 0)

        lines.append(f"\n### {stat.upper()} findings")
        lines.append(f"\nBaseline MAE: {bl_mae:.4f}")
        lines.append(f"all_cv_27 MAE: {cv27_mae:.4f}  delta={cv27_delta:+.4f}  folds_better={cv27_fb}/4")

        # Feature importance table
        top10 = stat_res.get("top10_cv_features", [])
        if top10:
            lines.append("\n#### Feature importance (XGB gain, top 10 CV features, fold 1)")
            lines.append("| rank | feature | gain |")
            lines.append("|------|---------|------|")
            for rank, (fname, gain) in enumerate(top10, 1):
                lines.append(f"| {rank} | {fname} | {gain:.2f} |")

        top5 = stat_res.get("top5_cv_by_importance", [])
        if top5:
            lines.append(f"\nTop-5 CV features by gain: {top5}")

        # Ablation table
        if stat == "reb":
            abl_header = "#### Ablation results (REB MAE delta vs baseline)"
            abl_configs = [
                "all_cv_27", "position_only", "possession_only",
                "mechanics_only", "playtype_only", "tier1_only", "top5_by_importance"
            ]
            ref_key = "delta_vs_baseline"
        else:
            abl_header = "#### Inverse ablation (PTS MAE delta vs all_cv_27 = positive baseline)"
            abl_configs = [
                "all_cv_27", "drop_position", "drop_possession",
                "drop_mechanics", "drop_playtype", "drop_tier1"
            ]
            ref_key = "delta_vs_all_cv_27"

        lines.append(f"\n{abl_header}")
        lines.append("| config | n_cv_feats | mae | delta_vs_baseline | delta_vs_all_cv_27 | folds_better |")
        lines.append("|--------|-----------|-----|------------------|--------------------|-------------|")

        for cfg in abl_configs:
            r = stat_res.get(cfg, {})
            if not r:
                lines.append(f"| {cfg} | n/a | n/a | n/a | n/a | n/a |")
                continue
            n_feats = r.get("n_cv_feats", 27 if cfg == "all_cv_27" else "?")
            mae = r.get("mae", float("nan"))
            d_bl = r.get("delta_vs_baseline", float("nan"))
            d_cv27 = r.get("delta_vs_all_cv_27", 0.0 if cfg == "all_cv_27" else float("nan"))
            fb = r.get("folds_better", 0)
            ship = " SHIP" if fb == 4 and d_bl < 0 else ""
            lines.append(
                f"| {cfg} | {n_feats} | {mae:.4f} | {d_bl:+.4f} | {d_cv27:+.4f} | {fb}/4{ship} |"
            )

        # Noisy feature analysis (PTS only)
        if stat == "pts":
            lines.append("\n#### Top noisy feature analysis for PTS (+1 feature vs baseline)")
            lines.append("| feature | mae | delta_vs_baseline | folds_better | verdict |")
            lines.append("|---------|-----|------------------|--------------|---------|")
            for noisy_feat in NOISY_CANDIDATES:
                key = f"noisy_{noisy_feat}"
                r = stat_res.get(key, {})
                if not r:
                    continue
                mae = r.get("mae", float("nan"))
                d_bl = r.get("delta_vs_baseline", float("nan"))
                fb = r.get("folds_better", 0)
                verdict = "HURTS" if d_bl > 0.001 else ("helps" if d_bl < -0.001 else "neutral")
                lines.append(f"| {noisy_feat} | {mae:.4f} | {d_bl:+.4f} | {fb}/4 | {verdict} |")

            # Identify worst 3 noisy features
            noisy_deltas = []
            for noisy_feat in NOISY_CANDIDATES:
                key = f"noisy_{noisy_feat}"
                r = stat_res.get(key, {})
                if r:
                    noisy_deltas.append((noisy_feat, r.get("delta_vs_baseline", 0.0)))
            noisy_deltas.sort(key=lambda x: -x[1])
            top3_noisy = [f for f, d in noisy_deltas[:3] if d > 0]
            lines.append(f"\nTop-3 noisiest PTS features: {top3_noisy}")

        lines.append("")

    # Combined recommendation
    lines.append("\n### Combined recommendation")
    lines.append("")

    reb_res = results.get("reb", {})
    pts_res = results.get("pts", {})

    # Find best REB config (minimum MAE, folds_better >= 3)
    reb_bl = reb_res.get("baseline", {}).get("mae", float("nan"))
    reb_ship_configs = []
    reb_candidates = [
        "all_cv_27", "position_only", "possession_only",
        "mechanics_only", "playtype_only", "tier1_only", "top5_by_importance"
    ]
    for cfg in reb_candidates:
        r = reb_res.get(cfg, {})
        if r:
            d = r.get("delta_vs_baseline", 0.0)
            fb = r.get("folds_better", 0)
            if d < 0 and fb == 4:
                reb_ship_configs.append((cfg, d, r.get("mae", float("nan")), fb))
    reb_ship_configs.sort(key=lambda x: x[1])  # most negative delta first

    # Find best PTS config (minimizes regression or even helps)
    pts_bl = pts_res.get("baseline", {}).get("mae", float("nan"))
    pts_cv27_delta = pts_res.get("all_cv_27", {}).get("delta_vs_baseline", 0.0)
    pts_best_cfg = "baseline (no CV)"
    pts_best_delta = 0.0
    pts_drop_candidates = ["drop_position", "drop_possession", "drop_mechanics", "drop_playtype", "drop_tier1"]
    for cfg in pts_drop_candidates:
        r = pts_res.get(cfg, {})
        if r:
            d = r.get("delta_vs_baseline", 0.0)
            fb = r.get("folds_better", 0)
            # Better than all_cv_27 AND better than baseline?
            if d < pts_best_delta:
                pts_best_delta = d
                pts_best_cfg = cfg

    lines.append("**For REB:**")
    if reb_ship_configs:
        best_reb = reb_ship_configs[0]
        lines.append(f"  Best SHIP config: `{best_reb[0]}` (delta={best_reb[1]:+.4f}, {best_reb[3]}/4 folds)")
        all_ship = ", ".join(f"`{c}`" for c, _, _, _ in reb_ship_configs)
        lines.append(f"  All SHIP configs: {all_ship}")
    else:
        # Any config better than baseline, even if not 4/4?
        best_any = None
        best_any_delta = 0.0
        for cfg in reb_candidates:
            r = reb_res.get(cfg, {})
            if r:
                d = r.get("delta_vs_baseline", 0.0)
                if d < best_any_delta:
                    best_any_delta = d
                    best_any = cfg
        if best_any:
            lines.append(f"  No 4/4 SHIP found. Best partial: `{best_any}` (delta={best_any_delta:+.4f})")
        else:
            lines.append("  No REB config beats baseline in this run.")

    lines.append("")
    lines.append("**For PTS:**")
    lines.append(f"  all_cv_27 delta vs baseline: {pts_cv27_delta:+.4f}")
    if pts_best_cfg != "baseline (no CV)":
        lines.append(f"  Best pruned config: `{pts_best_cfg}` (delta={pts_best_delta:+.4f})")
    else:
        lines.append(f"  No CV config beats baseline for PTS — recommend: `baseline (no CV)`")

    lines.append("")
    lines.append("**Cross-stat verdict:**")
    lines.append("  (See detailed tables above for per-feature signal quality)")

    lines.append("")
    lines.append("### Honest read")
    lines.append("")
    lines.append("- Baseline MAEs used as reference throughout (no leakage from all_cv_27).")
    lines.append("- Feature importance captured on fold 1 only (sufficient to identify leading signals).")
    lines.append("- 4/4 folds-better is the SHIP gate; anything lower is informational only.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 60)
    print("test_cv_per_stat_deepdive.py — Per-stat CV feature deep-dive")
    print("=" * 60)

    # ---- 1. Load dataset ----
    print("\nStep 1: Loading base dataset ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- 2. Load game_date map ----
    print("\nStep 2: Loading game_date map ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped to dates")

    # ---- 3. Load CV data ----
    print("\nStep 3: Loading CV data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} players with CV history")

    # ---- 4. Pre-compute CV matrix ----
    print("\nStep 4: Pre-computing CV augmentation matrix ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {time.time()-t0:.1f}s — {rows_with_cv}/{n} rows have CV ({pct:.1f}%)")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run experiments ----
    print(f"\nStep 6: Running experiments for {TARGET_STATS} ...")
    results = run_experiments(rows, base_cols, X_base, cv_matrix, cv_n_games)

    # ---- 7. Format and print report ----
    print("\n" + "=" * 70)
    report = _format_report(results)
    print(report)

    # ---- 8. Save JSON ----
    out_path = os.path.join(MODELS_DIR, "test_cv_deepdive_results.json")

    # Serialize results (convert numpy types)
    def _to_serializable(obj):
        if isinstance(obj, dict):
            return {k: _to_serializable(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_to_serializable(v) for v in obj]
        if isinstance(obj, (np.floating, np.integer)):
            return float(obj)
        return obj

    with open(out_path, "w") as f:
        json.dump(
            {
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(pct, 4),
                },
                "results": _to_serializable(results),
                "wall_time_s": round(time.time() - t_total, 1),
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
