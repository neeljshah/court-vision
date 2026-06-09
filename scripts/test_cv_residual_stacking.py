"""
test_cv_residual_stacking.py — X2a CV residual stacking architecture test.

Architecture:
  Layer 1 (baseline): XGB(GPU) + LGB NNLS blend on X_base (129 features) → predict y
  Layer 2 (CV-only):  XGB(GPU) on CV features only → predict (y - layer1_pred)
  Final: layer1_pred + shrinkage * cv_correction

Gate kept OFF throughout (no PROP_USE_CV).

Run:
    python scripts/test_cv_residual_stacking.py
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

from src.prediction.prop_pergame import build_pergame_dataset  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(PROJECT_DIR, "data", "nba_ai.db")
MODELS_DIR = os.path.join(PROJECT_DIR, "data", "models")
os.makedirs(MODELS_DIR, exist_ok=True)

# Test only these 3 canonical stats
TARGET_STATS = ["reb", "pts", "ast"]

N_SPLITS = 4
SHRINKAGE_VALUES = [0.0, 0.25, 0.5, 0.75, 1.0]

ALL_CV_COLS = [
    # Original 22 features
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
    # P1 Tier-1 features (per-frame mining)
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# Tier-1: 5 best features from X1c finding + cv_n_games = 6 total
TIER1_5 = [
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# CV feature configs for Layer 2:
#   all_cv_28: all 27 CV features + cv_n_games = 28 cols
#   tier1_6:   5 Tier-1 features + cv_n_games = 6 cols
CV_CONFIGS = {
    "tier1_6": TIER1_5,
    "all_cv_28": ALL_CV_COLS,
}


# ---------------------------------------------------------------------------
# Step 1: Load game_id -> game_date map
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from all season_games_*.json files."""
    gd: Dict[str, str] = {}
    nba_dir = os.path.join(PROJECT_DIR, "data", "nba")
    import glob as _glob
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


# ---------------------------------------------------------------------------
# Step 2: Load CV data from DB
# ---------------------------------------------------------------------------
def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, str, float]]]:
    """Return {player_id: sorted list of (game_date, feature_name, value)}."""
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
    """Aggregate last-5 CV games where game_date < row_date."""
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
    avgs = {fname: feature_sums[fname] / feature_counts[fname]
            for fname in feature_sums}
    return avgs, n_games


# ---------------------------------------------------------------------------
# Step 3: Pre-compute CV augmentation matrix
# ---------------------------------------------------------------------------
def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
        cv_matrix  — (n_rows, 27) float array, one col per ALL_CV_COLS feature
        cv_n_games — (n_rows,) int array, number of CV games contributing
    """
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 10000 == 0 and i > 0:
            elapsed = time.time() - t0
            print(f"    CV pre-compute: {i}/{n} ({elapsed:.1f}s)", flush=True)
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
# Step 4: Layer 1 — baseline XGB + LGB NNLS blend (no CV features)
# ---------------------------------------------------------------------------
def _train_layer1(
    stat: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_ho: np.ndarray,
    sw: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Train Layer 1 (baseline XGB + LGB blend).

    Returns:
        layer1_val_pred   — predictions on validation set
        layer1_ho_pred    — predictions on holdout set
        layer1_tr_pred    — predictions on training set
        blend_weights     — [w_xgb, w_lgb]
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression

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
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)

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
    xt = xgb_m.predict(X_tr)
    lt = lgb_m.predict(X_tr)

    # NNLS blend fit on val
    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    val_pred = w[0] * xv + w[1] * lv
    ho_pred = w[0] * xh + w[1] * lh
    tr_pred = w[0] * xt + w[1] * lt

    return val_pred, ho_pred, tr_pred, w


# ---------------------------------------------------------------------------
# Step 5: Layer 2 — XGB on CV features predicting baseline residuals
# ---------------------------------------------------------------------------
def _train_layer2(
    X_tr_cv: np.ndarray,
    residuals_tr: np.ndarray,
    cv_mask_tr: np.ndarray,
    X_val_cv: np.ndarray,
    residuals_val: np.ndarray,
    cv_mask_val: np.ndarray,
    X_ho_cv: np.ndarray,
    cv_mask_ho: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Train Layer 2: XGB on CV features predicting residuals.
    Only trains on rows where cv_n_games > 0.

    Returns:
        cv_correction_ho — corrections for holdout rows (0 where cv_mask_ho is False)
        cv_correction_val — corrections for val rows (for diagnostics)
        n_train_rows     — number of CV-eligible training rows used
    """
    import xgboost as xgb

    # Filter training to CV-eligible rows only
    tr_cv_idx = np.where(cv_mask_tr)[0]
    n_train_rows = len(tr_cv_idx)

    # Need at least a few hundred rows to train
    if n_train_rows < 100:
        zeros_ho = np.zeros(len(X_ho_cv))
        zeros_val = np.zeros(len(X_val_cv))
        return zeros_ho, zeros_val, n_train_rows

    X_tr_cv_filtered = X_tr_cv[tr_cv_idx]
    y_tr_res_filtered = residuals_tr[tr_cv_idx]

    # For val eval — use only CV-eligible val rows if enough, else use all val
    val_cv_idx = np.where(cv_mask_val)[0]
    if len(val_cv_idx) >= 50:
        X_val_cv_eval = X_val_cv[val_cv_idx]
        y_val_res_eval = residuals_val[val_cv_idx]
    else:
        X_val_cv_eval = X_val_cv
        y_val_res_eval = residuals_val

    layer2_xgb = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=3,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=10,
        reg_lambda=3.0,
        reg_alpha=1.0,
        gamma=0.5,
        random_state=42,
        objective="reg:squarederror",
        eval_metric="mae",
        early_stopping_rounds=20,
        verbosity=0,
        tree_method="hist",
        device="cuda",
    )
    layer2_xgb.fit(
        X_tr_cv_filtered,
        y_tr_res_filtered,
        eval_set=[(X_val_cv_eval, y_val_res_eval)],
        verbose=False,
    )

    # Predict corrections: zero out rows with no CV signal
    cv_correction_ho = np.zeros(len(X_ho_cv))
    ho_cv_idx = np.where(cv_mask_ho)[0]
    if len(ho_cv_idx) > 0:
        cv_correction_ho[ho_cv_idx] = layer2_xgb.predict(X_ho_cv[ho_cv_idx])

    cv_correction_val = np.zeros(len(X_val_cv))
    if len(val_cv_idx) > 0:
        cv_correction_val[val_cv_idx] = layer2_xgb.predict(X_val_cv[val_cv_idx])

    return cv_correction_ho, cv_correction_val, n_train_rows


# ---------------------------------------------------------------------------
# Step 6: Run walk-forward with residual stacking
# ---------------------------------------------------------------------------
def _run_residual_stacking_wf(
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Run 4-fold WF residual stacking for TARGET_STATS × CV_CONFIGS × SHRINKAGE_VALUES.

    Returns nested result dict.
    """
    from sklearn.metrics import mean_absolute_error

    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    n = len(rows)

    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    # Storage: results[stat][cv_config][shrinkage] = [fold_mae, ...]
    results: dict = {
        stat: {
            cv_cfg: {s: [] for s in SHRINKAGE_VALUES}
            for cv_cfg in CV_CONFIGS
        }
        for stat in TARGET_STATS
    }

    # Also store L1 baseline per (stat, fold)
    layer1_maes: dict = {stat: [] for stat in TARGET_STATS}
    # CV-eligible-subset MAEs per (stat, cv_cfg, shrinkage, fold)
    cv_subset_maes: dict = {
        stat: {
            cv_cfg: {s: [] for s in SHRINKAGE_VALUES}
            for cv_cfg in CV_CONFIGS
        }
        for stat in TARGET_STATS
    }
    # CV-eligible counts per fold
    cv_eligible_counts: dict = {stat: [] for stat in TARGET_STATS}
    layer2_train_rows: dict = {stat: {cv_cfg: [] for cv_cfg in CV_CONFIGS} for stat in TARGET_STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == N_SPLITS - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, ho={te_end-va_end}) — skip")
            continue

        # Sample weights
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        # CV masks for each split
        cv_mask_tr = cv_n_games[:tr_end] > 0
        cv_mask_val = cv_n_games[tr_end:va_end] > 0
        cv_mask_ho = cv_n_games[va_end:te_end] > 0

        n_cv_ho = cv_mask_ho.sum()

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}  cv_tr={cv_mask_tr.sum()} cv_val={cv_mask_val.sum()} "
            f"cv_ho={n_cv_ho}",
            flush=True,
        )

        X_tr_base = X_base[:tr_end]
        X_val_base = X_base[tr_end:va_end]
        X_ho_base = X_base[va_end:te_end]

        for stat in TARGET_STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            cv_eligible_counts[stat].append(int(n_cv_ho))

            fold_t0 = time.time()

            # --- Layer 1: Baseline blend (no CV features) ---
            l1_val_pred, l1_ho_pred, l1_tr_pred, blend_w = _train_layer1(
                stat, X_tr_base, y_tr, X_val_base, y_val, X_ho_base, sw
            )
            l1_mae = float(mean_absolute_error(y_ho, l1_ho_pred))
            layer1_maes[stat].append(l1_mae)

            # Residuals
            residuals_tr = y_tr - l1_tr_pred
            residuals_val = y_val - l1_val_pred

            l1_time = time.time() - fold_t0
            print(
                f"  {stat.upper():3s} L1={l1_mae:.4f} "
                f"(blend w=[{blend_w[0]:.2f},{blend_w[1]:.2f}]) "
                f"[{l1_time:.1f}s]",
                flush=True,
            )

            # --- Layer 2: CV residual correction for each CV config ---
            for cv_cfg_name, cv_feat_names in CV_CONFIGS.items():
                l2_t0 = time.time()

                # Build CV feature matrix for this config + cv_n_games column
                cv_cols_idx = [feat_idx[f] for f in cv_feat_names if f in feat_idx]
                cv_sub_tr = cv_matrix[:tr_end][:, cv_cols_idx]
                cv_sub_val = cv_matrix[tr_end:va_end][:, cv_cols_idx]
                cv_sub_ho = cv_matrix[va_end:te_end][:, cv_cols_idx]

                cv_ngames_tr = cv_n_games[:tr_end].reshape(-1, 1).astype(float)
                cv_ngames_val = cv_n_games[tr_end:va_end].reshape(-1, 1).astype(float)
                cv_ngames_ho = cv_n_games[va_end:te_end].reshape(-1, 1).astype(float)

                X_tr_cv = np.hstack([cv_sub_tr, cv_ngames_tr])
                X_val_cv = np.hstack([cv_sub_val, cv_ngames_val])
                X_ho_cv = np.hstack([cv_sub_ho, cv_ngames_ho])

                cv_correction_ho, cv_correction_val, n_l2_rows = _train_layer2(
                    X_tr_cv, residuals_tr, cv_mask_tr,
                    X_val_cv, residuals_val, cv_mask_val,
                    X_ho_cv, cv_mask_ho,
                )
                layer2_train_rows[stat][cv_cfg_name].append(n_l2_rows)

                # Evaluate at each shrinkage level
                for shrinkage in SHRINKAGE_VALUES:
                    final_pred = l1_ho_pred + shrinkage * cv_correction_ho
                    full_mae = float(mean_absolute_error(y_ho, final_pred))
                    results[stat][cv_cfg_name][shrinkage].append(full_mae)

                    # CV-eligible subset MAE
                    if n_cv_ho >= 50:
                        ho_cv_idx = np.where(cv_mask_ho)[0]
                        subset_mae = float(mean_absolute_error(
                            y_ho[ho_cv_idx], final_pred[ho_cv_idx]
                        ))
                    else:
                        subset_mae = float("nan")
                    cv_subset_maes[stat][cv_cfg_name][shrinkage].append(subset_mae)

                l2_time = time.time() - l2_t0
                best_s = min(SHRINKAGE_VALUES, key=lambda s: np.mean(
                    [results[stat][cv_cfg_name][s][-1]] if results[stat][cv_cfg_name][s] else [999]
                ))
                best_mae = results[stat][cv_cfg_name][best_s][-1]
                print(
                    f"    {cv_cfg_name:12s}  L2_rows={n_l2_rows:5d}  "
                    f"best_s={best_s:.2f} MAE={best_mae:.4f} (delta={best_mae-l1_mae:+.4f}) "
                    f"[{l2_time:.1f}s]",
                    flush=True,
                )

    return {
        "results": results,
        "layer1_maes": layer1_maes,
        "cv_subset_maes": cv_subset_maes,
        "cv_eligible_counts": cv_eligible_counts,
        "layer2_train_rows": layer2_train_rows,
    }


# ---------------------------------------------------------------------------
# Step 7: Print final report
# ---------------------------------------------------------------------------
def _print_report(
    wf_output: dict,
    cv_coverage: dict,
) -> str:
    """Print the X2a Residual Stacking report. Return as string."""
    results = wf_output["results"]
    layer1_maes = wf_output["layer1_maes"]
    cv_subset_maes = wf_output["cv_subset_maes"]
    cv_eligible_counts = wf_output["cv_eligible_counts"]
    layer2_train_rows = wf_output["layer2_train_rows"]

    lines = [
        "",
        "=" * 70,
        "## X2a Residual Stacking — Final Report",
        "=" * 70,
        "",
        "### Architecture",
        "- Layer 1: XGB(GPU) + LGB NNLS blend on 129 baseline features",
        "- Layer 2: XGB(GPU) on CV features only, predicting baseline residuals",
        "- Filtered training for Layer 2: only rows with cv_n_games > 0",
        "",
        f"### CV Coverage",
        f"- Total rows: {cv_coverage['total_rows']}",
        f"- Rows with cv_n > 0: {cv_coverage['rows_with_cv']}",
        f"- Percent covered: {cv_coverage['pct_covered']:.2f}%",
        "",
        "### Layer 1 Baseline (no CV) — 4-fold WF MAE",
    ]

    for stat in TARGET_STATS:
        l1_folds = layer1_maes[stat]
        if l1_folds:
            mean_l1 = float(np.mean(l1_folds))
            lines.append(f"  {stat.upper():4s}: folds={[round(x,4) for x in l1_folds]}  mean={mean_l1:.4f}")
        else:
            lines.append(f"  {stat.upper():4s}: no folds")

    lines += [
        "",
        "### Layer 2 CV-Correction Results",
        "",
        "| stat | cv_config | shrinkage | full holdout MAE | delta vs L1-only | CV-eligible subset MAE | delta on subset |",
        "|------|-----------|-----------|----------------:|------------------:|----------------------:|---------------:|",
    ]

    best_per_stat_cfg: dict = {}

    for stat in TARGET_STATS:
        l1_folds = layer1_maes[stat]
        if not l1_folds:
            continue
        l1_mean = float(np.mean(l1_folds))

        for cv_cfg in CV_CONFIGS:
            best_shrinkage = None
            best_full_mae = float("inf")
            best_full_delta = 0.0

            for shrinkage in SHRINKAGE_VALUES:
                fold_maes = results[stat][cv_cfg][shrinkage]
                if not fold_maes:
                    continue
                full_mae_mean = float(np.mean(fold_maes))
                delta = full_mae_mean - l1_mean

                subset_maes = cv_subset_maes[stat][cv_cfg][shrinkage]
                # Filter NaN
                valid_subset = [x for x in subset_maes if not np.isnan(x)]
                if valid_subset:
                    subset_mae_mean = float(np.mean(valid_subset))
                    # Baseline subset MAE at shrinkage=0
                    subset_maes_s0 = cv_subset_maes[stat][cv_cfg][0.0]
                    valid_s0 = [x for x in subset_maes_s0 if not np.isnan(x)]
                    subset_base = float(np.mean(valid_s0)) if valid_s0 else float("nan")
                    subset_delta = subset_mae_mean - subset_base
                    subset_str = f"{subset_mae_mean:.4f}"
                    subset_delta_str = f"{subset_delta:+.4f}"
                else:
                    subset_mae_mean = float("nan")
                    subset_str = "n/a"
                    subset_delta_str = "n/a"

                flag = "**" if delta < 0 else ""
                row = (
                    f"| {stat} | {cv_cfg} | {shrinkage:.2f} | "
                    f"{flag}{full_mae_mean:.4f}{flag} | {flag}{delta:+.4f}{flag} | "
                    f"{subset_str} | {subset_delta_str} |"
                )
                lines.append(row)

                if full_mae_mean < best_full_mae:
                    best_full_mae = full_mae_mean
                    best_shrinkage = shrinkage
                    best_full_delta = delta

            if best_per_stat_cfg.get(stat) is None or best_full_mae < best_per_stat_cfg[stat]["full_mae"]:
                best_per_stat_cfg[stat] = {
                    "cv_cfg": cv_cfg,
                    "shrinkage": best_shrinkage,
                    "full_mae": best_full_mae,
                    "delta": best_full_delta,
                    "l2_rows_mean": float(np.mean(layer2_train_rows[stat][cv_cfg])) if layer2_train_rows[stat][cv_cfg] else 0,
                }

    lines += [
        "",
        "### Best Shrinkage Per (stat, cv_config)",
        "",
    ]

    for stat in TARGET_STATS:
        l1_folds = layer1_maes[stat]
        if not l1_folds:
            continue
        l1_mean = float(np.mean(l1_folds))

        for cv_cfg in CV_CONFIGS:
            per_shrinkage = {}
            for shrinkage in SHRINKAGE_VALUES:
                fold_maes = results[stat][cv_cfg][shrinkage]
                if fold_maes:
                    per_shrinkage[shrinkage] = float(np.mean(fold_maes))
            if per_shrinkage:
                best_s = min(per_shrinkage, key=lambda s: per_shrinkage[s])
                n_folds_beat = sum(
                    1 for i, fm in enumerate(results[stat][cv_cfg][best_s])
                    if fm < layer1_maes[stat][i]
                ) if results[stat][cv_cfg][best_s] else 0
                n_folds_total = len(results[stat][cv_cfg][best_s])
                lines.append(
                    f"  {stat:4s} / {cv_cfg:12s}: best shrinkage={best_s:.2f}  "
                    f"MAE={per_shrinkage[best_s]:.4f} (delta={per_shrinkage[best_s]-l1_mean:+.4f})  "
                    f"folds beat baseline={n_folds_beat}/{n_folds_total}  "
                    f"L2 train rows~{int(np.mean(layer2_train_rows[stat][cv_cfg])) if layer2_train_rows[stat][cv_cfg] else 0}"
                )

    # Reference comparison
    lines += [
        "",
        "### Comparison to Existing Direct-Dump Results",
        "",
        "  (from test_cv_isolated_results.json):",
        "  - all_cv_27 direct dump:  REB mean MAE = 1.8966  (delta ~ -0.0037 vs baseline 1.9003)",
        "  - tier1_5  direct dump:   REB mean MAE = 1.8984  (delta ~ -0.0019 vs baseline 1.9003)",
        "",
    ]

    for stat in TARGET_STATS:
        if stat in best_per_stat_cfg:
            b = best_per_stat_cfg[stat]
            l1_mean = float(np.mean(layer1_maes[stat])) if layer1_maes[stat] else float("nan")
            lines.append(
                f"  Residual stacking {stat.upper()} best: {b['cv_cfg']} shrinkage={b['shrinkage']:.2f}  "
                f"MAE={b['full_mae']:.4f}  delta={b['delta']:+.4f}  "
                f"(L1 baseline={l1_mean:.4f})"
            )

    lines += [
        "",
        "### Honest Read",
        "",
    ]

    # Determine overall verdict
    any_beats_direct = False
    any_4fold_win = False

    for stat in TARGET_STATS:
        if not layer1_maes[stat]:
            continue
        l1_mean = float(np.mean(layer1_maes[stat]))

        for cv_cfg in CV_CONFIGS:
            for shrinkage in SHRINKAGE_VALUES:
                fold_maes = results[stat][cv_cfg][shrinkage]
                if len(fold_maes) == 4:
                    n_folds_beat = sum(
                        1 for i, fm in enumerate(fold_maes)
                        if fm < layer1_maes[stat][i]
                    )
                    if n_folds_beat == 4:
                        any_4fold_win = True

    reb_best_delta = None
    if "reb" in best_per_stat_cfg:
        reb_best_delta = best_per_stat_cfg["reb"]["delta"]
        if reb_best_delta < -0.0037:
            any_beats_direct = True

    if any_4fold_win:
        verdict = "POSITIVE: At least one (stat, cv_config, shrinkage) beats baseline on all 4 folds."
        if any_beats_direct:
            verdict += " Residual stacking BEATS direct feature dumping for REB."
        else:
            verdict += " But does not clearly beat direct feature dumping."
    else:
        verdict = "NEGATIVE: No (stat, cv_config, shrinkage) combination beats baseline on all 4 folds."

    lines.append(f"  Overall verdict: {verdict}")
    lines.append("")

    if reb_best_delta is not None:
        if reb_best_delta < -0.0037:
            lines.append("  REB analysis: Residual stacking extracts MORE CV signal than direct feature dumping.")
            lines.append("  This suggests layer-1 does NOT fully absorb the linear CV combination,")
            lines.append("  and the residual correction adds orthogonal signal.")
        elif reb_best_delta < 0:
            lines.append(f"  REB analysis: Residual stacking improves over L1 baseline (delta={reb_best_delta:+.4f})")
            lines.append("  but does NOT beat direct feature dumping (which achieved ~-0.0037).")
            lines.append("  Conclusion: Direct feature dumping is equivalent or slightly better.")
        else:
            lines.append("  REB analysis: Residual stacking does NOT improve over L1 baseline.")
            lines.append("  The Layer 1 model already captures the CV signal through correlations")
            lines.append("  with baseline features. Layer 2 adds noise, not signal.")

    lines += [
        "",
        "  Key consideration: With only ~12% CV coverage, Layer 2 trains on a very sparse",
        "  signal (~12K rows out of ~100K). The small training set for Layer 2 limits its power.",
        "  The CV-eligible subset delta is the most honest measure — check if corrections",
        "  actually help the rows that have CV data.",
        "",
        "  Architecture verdict:",
    ]

    if any_4fold_win:
        lines.append("  - Residual stacking IS worth pursuing if 4/4 folds are positive.")
        lines.append("  - The isolated residual layer can pick up non-linear corrections")
        lines.append("    that direct feature addition dilutes in 129-feature space.")
    else:
        lines.append("  - Residual stacking provides NO advantage over direct feature use.")
        lines.append("  - Layer 1 already learns (or ignores as noise) the CV features.")
        lines.append("  - The architecture overhead is not justified; direct feature inclusion")
        lines.append("    (with cv_n_games as a reliability gate) is simpler and equivalent.")

    output = "\n".join(lines)
    print(output)
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 60)
    print("X2a Residual Stacking Test")
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
    print(f"  {len(game_date_map)} game_ids mapped")

    # ---- 3. Load CV data ----
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # ---- 4. Pre-compute CV matrix ----
    print("\nStep 4: Pre-computing CV augmentation matrix ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {time.time()-t0:.1f}s")
    print(f"  Total rows: {n}  |  rows with cv_n > 0: {rows_with_cv}  ({pct:.2f}%)")

    cv_coverage = {
        "total_rows": n,
        "rows_with_cv": rows_with_cv,
        "pct_covered": round(pct, 4),
    }

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run residual stacking walk-forward ----
    print(
        f"\nStep 6: Running {N_SPLITS}-fold WF residual stacking  "
        f"({len(TARGET_STATS)} stats × {len(CV_CONFIGS)} CV configs × "
        f"{len(SHRINKAGE_VALUES)} shrinkage values = "
        f"{len(TARGET_STATS)*len(CV_CONFIGS)*len(SHRINKAGE_VALUES)} layer-2 fits per fold) ...",
        flush=True,
    )
    wf_output = _run_residual_stacking_wf(rows, X_base, cv_matrix, cv_n_games)

    # ---- 7. Print + save report ----
    print("\n")
    report_text = _print_report(wf_output, cv_coverage)

    # Build structured summary for JSON
    layer1_summary = {}
    for stat in TARGET_STATS:
        l1_folds = wf_output["layer1_maes"][stat]
        layer1_summary[stat] = {
            "folds": l1_folds,
            "mean": float(np.mean(l1_folds)) if l1_folds else None,
        }

    best_per_stat = {}
    for stat in TARGET_STATS:
        l1_folds = wf_output["layer1_maes"][stat]
        if not l1_folds:
            best_per_stat[stat] = None
            continue
        l1_mean = float(np.mean(l1_folds))
        best = {"delta": 0.0, "full_mae": l1_mean, "cv_cfg": "layer1_only", "shrinkage": 0.0}
        for cv_cfg in CV_CONFIGS:
            for shrinkage in SHRINKAGE_VALUES:
                fold_maes = wf_output["results"][stat][cv_cfg][shrinkage]
                if fold_maes:
                    fm = float(np.mean(fold_maes))
                    if fm < best["full_mae"]:
                        best = {
                            "full_mae": fm,
                            "delta": fm - l1_mean,
                            "cv_cfg": cv_cfg,
                            "shrinkage": shrinkage,
                        }
        best_per_stat[stat] = best

    out = {
        "cv_coverage": cv_coverage,
        "layer1_baseline": layer1_summary,
        "residual_stacking": {
            stat: {
                cv_cfg: {
                    str(s): {
                        "fold_maes": wf_output["results"][stat][cv_cfg][s],
                        "mean_mae": float(np.mean(wf_output["results"][stat][cv_cfg][s]))
                        if wf_output["results"][stat][cv_cfg][s]
                        else None,
                        "delta_vs_l1": (
                            float(np.mean(wf_output["results"][stat][cv_cfg][s]))
                            - float(np.mean(wf_output["layer1_maes"][stat]))
                        )
                        if wf_output["results"][stat][cv_cfg][s] and wf_output["layer1_maes"][stat]
                        else None,
                        "cv_subset_fold_maes": wf_output["cv_subset_maes"][stat][cv_cfg][s],
                        "cv_subset_mean_mae": float(np.nanmean(
                            [x for x in wf_output["cv_subset_maes"][stat][cv_cfg][s] if not np.isnan(x)]
                        )) if any(not np.isnan(x) for x in wf_output["cv_subset_maes"][stat][cv_cfg][s]) else None,
                    }
                    for s in SHRINKAGE_VALUES
                }
                for cv_cfg in CV_CONFIGS
            }
            for stat in TARGET_STATS
        },
        "best_per_stat": best_per_stat,
        "layer2_train_rows": wf_output["layer2_train_rows"],
        "cv_eligible_counts_per_fold": wf_output["cv_eligible_counts"],
        "report": report_text,
        "wall_time_s": round(time.time() - t_total, 1),
    }

    out_path = os.path.join(MODELS_DIR, "test_cv_residual_stacking_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
