"""
test_cv_algorithms.py — Algorithm sweep for CV feature extraction.

Tests 5 algorithm classes on all_cv_27 vs baseline to see if any extract
more signal than the current XGB+LGB blend.

Algorithms tested:
  1. XGB+LGB NNLS blend      (reference — mirrors test_cv_isolated.py)
  2. Lasso (L1)               (linear, explicit feature selection)
  3. Random Forest            (shallow trees, less interaction overfitting)
  4. XGB with monotonic       (physics-constrained XGB for REB)
  5. LGB quantile q50         (median predictor — matches prop O/U lines)

Test stats: REB, PTS, AST
Config: baseline vs all_cv_27 (27 CV features + cv_n_games_cv)
Folds: 4-fold walk-forward

Run:
    python scripts/test_cv_algorithms.py
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

TEST_STATS = ["reb", "pts", "ast"]

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

# Algorithm names
ALG_NAMES = [
    "xgb_lgb_blend",
    "lasso",
    "random_forest",
    "xgb_monotonic",
    "lgb_quantile_q50",
]

CONFIGS = ["baseline", "all_cv_27"]


# ---------------------------------------------------------------------------
# Data loading helpers (copied verbatim from test_cv_isolated.py)
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


def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Dict[int, List[Tuple[str, str, float]]]:
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
    avgs = {fname: feature_sums[fname] / feature_counts[fname]
            for fname in feature_sums}
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
# NaN-safe imputation helper
# ---------------------------------------------------------------------------
def _impute_nans(X: np.ndarray) -> np.ndarray:
    """Replace NaN/inf with 0 (safe for all algorithms)."""
    X = np.array(X, dtype=float)
    X = np.where(np.isfinite(X), X, 0.0)
    return X


# ---------------------------------------------------------------------------
# Algorithm trainers — each returns holdout MAE
# ---------------------------------------------------------------------------

def _train_xgb_lgb_blend(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
) -> float:
    """XGB+LGB NNLS blend — reference algorithm."""
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

    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


def _train_lasso(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
    cv_feature_names: List[str],  # for reporting non-zero coefficients
) -> Tuple[float, Dict[str, float]]:
    """
    Lasso with alpha sweep on val MAE.
    Returns (holdout_mae, {feature_name: coef for non-zero CV features}).
    """
    from sklearn.linear_model import Lasso
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import mean_absolute_error

    X_tr_c = _impute_nans(X_tr)
    X_val_c = _impute_nans(X_val)
    X_ho_c = _impute_nans(X_ho)

    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr_c)
    X_val_s = sc.transform(X_val_c)
    X_ho_s = sc.transform(X_ho_c)

    best_alpha = 0.01
    best_val_mae = float("inf")
    for alpha in [0.001, 0.01, 0.1, 1.0]:
        m = Lasso(alpha=alpha, max_iter=5000, random_state=42)
        m.fit(X_tr_s, y_tr, sample_weight=sw)
        val_preds = m.predict(X_val_s)
        val_mae = mean_absolute_error(y_val, val_preds)
        if val_mae < best_val_mae:
            best_val_mae = val_mae
            best_alpha = alpha

    final = Lasso(alpha=best_alpha, max_iter=5000, random_state=42)
    final.fit(X_tr_s, y_tr, sample_weight=sw)
    ho_preds = final.predict(X_ho_s)
    ho_mae = float(mean_absolute_error(y_ho, ho_preds))

    # Extract CV feature coefficients (non-zero only)
    coefs = final.coef_
    n_base = X_tr_c.shape[1] - (len(cv_feature_names) + 1 if cv_feature_names else 0)
    cv_coefs: Dict[str, float] = {}
    if cv_feature_names:
        # CV columns start at n_base, cv_n_games_cv is the last column
        cv_col_names = cv_feature_names + ["cv_n_games_cv"]
        for j, fname in enumerate(cv_col_names):
            col_idx = n_base + j
            if col_idx < len(coefs) and abs(coefs[col_idx]) > 1e-8:
                cv_coefs[fname] = float(coefs[col_idx])

    return ho_mae, cv_coefs


def _train_random_forest(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
) -> float:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error

    X_tr_c = _impute_nans(X_tr)
    X_ho_c = _impute_nans(X_ho)

    m = RandomForestRegressor(
        n_estimators=300,
        max_depth=8,
        min_samples_leaf=10,
        n_jobs=-1,
        random_state=42,
    )
    m.fit(X_tr_c, y_tr, sample_weight=sw)
    preds = m.predict(X_ho_c)
    return float(mean_absolute_error(y_ho, preds))


def _build_monotone_constraints(
    stat: str,
    base_n_cols: int,
    cv_feature_names: List[str],
) -> tuple:
    """
    Build monotone_constraints tuple for XGB.
    For REB: paint_dwell_pct=+1, cv_n_games_cv=+1, all others=0.
    For PTS/AST: all zeros (no physical constraints known).
    """
    n_total = base_n_cols + (len(cv_feature_names) + 1 if cv_feature_names else 0)
    constraints = [0] * n_total

    if cv_feature_names and stat == "reb":
        cv_start = base_n_cols
        for j, fname in enumerate(cv_feature_names):
            if fname == "paint_dwell_pct":
                constraints[cv_start + j] = 1
        # cv_n_games_cv is the last appended column
        constraints[cv_start + len(cv_feature_names)] = 1

    return tuple(constraints)


def _train_xgb_monotonic(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
    cv_feature_names: List[str],
) -> float:
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    is_count = stat in ("stl", "blk")
    depth = 3 if is_count else 4

    # Derive base column count:  X_tr may have cv cols appended (n_cv + 1 for cv_n_games)
    n_cv_appended = len(cv_feature_names) + 1 if cv_feature_names else 0
    base_n = X_tr.shape[1] - n_cv_appended
    constraints = _build_monotone_constraints(stat, base_n, cv_feature_names)

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
        monotone_constraints=constraints,
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
    preds = xgb_m.predict(X_ho)
    return float(mean_absolute_error(y_ho, preds))


def _train_lgb_quantile(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
) -> float:
    """LGB quantile q50. MAE on q50 preds vs targets (apples-to-apples)."""
    import lightgbm as lgb
    from sklearn.metrics import mean_absolute_error

    m = lgb.LGBMRegressor(
        objective="quantile",
        alpha=0.5,
        n_estimators=400,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        min_child_samples=20,
        reg_lambda=2.0,
        reg_alpha=0.5,
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )
    m.fit(
        X_tr, y_tr,
        eval_set=[(X_val, y_val)],
        sample_weight=sw,
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )
    preds = m.predict(X_ho)
    return float(mean_absolute_error(y_ho, preds))


# ---------------------------------------------------------------------------
# Walk-forward loop
# ---------------------------------------------------------------------------
def _run_walk_forward(
    rows: List[dict],
    base_cols: List[str],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> Tuple[dict, dict]:
    """
    Returns:
        results[stat][alg_name][config] = [fold_mae, ...]
        lasso_coefs[stat][config][fold] = {feature: coef}
    """
    n = len(rows)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    results: dict = {
        stat: {alg: {cfg: [] for cfg in CONFIGS} for alg in ALG_NAMES}
        for stat in TEST_STATS
    }
    lasso_coefs: dict = {
        stat: {cfg: [] for cfg in CONFIGS}
        for stat in TEST_STATS
    }

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

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        for stat in TEST_STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg in CONFIGS:
                if cfg == "all_cv_27":
                    cv_cols_idx = [feat_idx[f] for f in ALL_CV_COLS if f in feat_idx]
                    cv_extra = cv_matrix[:, cv_cols_idx]
                    cv_ngames_col = cv_n_games.reshape(-1, 1).astype(float)
                    X_aug = np.hstack([X_base, cv_extra, cv_ngames_col])
                    cv_names_used = ALL_CV_COLS
                else:
                    X_aug = X_base
                    cv_names_used = []

                X_tr = X_aug[:tr_end]
                X_val_arr = X_aug[tr_end:va_end]
                X_ho_arr = X_aug[va_end:te_end]

                # --- Algorithm 1: XGB+LGB blend (reference) ---
                mae = _train_xgb_lgb_blend(
                    stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, y_ho, sw
                )
                results[stat]["xgb_lgb_blend"][cfg].append(mae)

                # --- Algorithm 2: Lasso ---
                lasso_mae, cv_coefs = _train_lasso(
                    stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, y_ho, sw,
                    cv_names_used,
                )
                results[stat]["lasso"][cfg].append(lasso_mae)
                lasso_coefs[stat][cfg].append(cv_coefs)

                # --- Algorithm 3: Random Forest ---
                rf_mae = _train_random_forest(
                    stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, y_ho, sw
                )
                results[stat]["random_forest"][cfg].append(rf_mae)

                # --- Algorithm 4: XGB monotonic ---
                mono_mae = _train_xgb_monotonic(
                    stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, y_ho, sw,
                    cv_names_used,
                )
                results[stat]["xgb_monotonic"][cfg].append(mono_mae)

                # --- Algorithm 5: LGB quantile q50 ---
                q50_mae = _train_lgb_quantile(
                    stat, X_tr, y_tr, X_val_arr, y_val, X_ho_arr, y_ho, sw
                )
                results[stat]["lgb_quantile_q50"][cfg].append(q50_mae)

            # Quick fold summary for this stat
            elapsed = time.time() - fold_t0
            ref_base = results[stat]["xgb_lgb_blend"]["baseline"][-1]
            ref_cv   = results[stat]["xgb_lgb_blend"]["all_cv_27"][-1]
            print(
                f"  {stat.upper():4s}  xgb_lgb base={ref_base:.4f} cv={ref_cv:.4f} "
                f"delta={ref_cv-ref_base:+.4f}  ({elapsed:.1f}s)",
                flush=True,
            )

    return results, lasso_coefs


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------
def _build_report(results: dict, lasso_coefs: dict) -> str:
    lines = [
        "",
        "=" * 70,
        "## X1b Algorithm Sweep — Final Report",
        "=" * 70,
        "",
        "### Setup",
        f"- Test stats: {', '.join(s.upper() for s in TEST_STATS)}",
        "- Algorithms: XGB+LGB blend (ref), Lasso, RF, XGB-monotonic, LGB-quantile-q50",
        "- Configs: baseline (no CV) vs all_cv_27 (27 CV features + cv_n_games_cv)",
        "- 4-fold walk-forward, GPU XGBoost",
        "",
    ]

    for stat in TEST_STATS:
        lines.append(f"### {stat.upper()}")
        lines.append(
            "| algorithm | baseline MAE | with_cv MAE | delta | folds_better/N |"
        )
        lines.append(
            "|-----------|-------------:|------------:|------:|---------------:|"
        )
        for alg in ALG_NAMES:
            base_maes = results[stat][alg].get("baseline", [])
            cv_maes   = results[stat][alg].get("all_cv_27", [])
            if not base_maes or not cv_maes:
                lines.append(f"| {alg} | n/a | n/a | n/a | n/a |")
                continue
            base_mean = float(np.mean(base_maes))
            cv_mean   = float(np.mean(cv_maes))
            delta     = cv_mean - base_mean
            n_folds   = min(len(base_maes), len(cv_maes))
            folds_better = sum(1 for b, c in zip(base_maes, cv_maes) if c < b)
            delta_str = f"**{delta:+.4f}**" if delta < 0 else f"{delta:+.4f}"
            lines.append(
                f"| {alg} | {base_mean:.4f} | {cv_mean:.4f} | {delta_str} | {folds_better}/{n_folds} |"
            )
        lines.append("")

    # --- Lasso feature selection ---
    lines.append("### Lasso Feature Selection (non-zero CV coefficients, all_cv_27)")
    lines.append(
        "Which CV features survived L1 penalty? (positive = more stat, negative = less)"
    )
    lines.append("")
    for stat in TEST_STATS:
        fold_coefs = lasso_coefs[stat].get("all_cv_27", [])
        if not fold_coefs:
            lines.append(f"**{stat.upper()}**: no data")
            continue
        # Aggregate across folds: count how many folds each feature was non-zero
        agg: Dict[str, List[float]] = defaultdict(list)
        for fold_dict in fold_coefs:
            for fname, coef in fold_dict.items():
                agg[fname].append(coef)
        # Sort by abs mean coef descending, take top 5
        sorted_feats = sorted(agg.items(), key=lambda x: abs(np.mean(x[1])), reverse=True)
        top5 = sorted_feats[:5]
        feat_strs = [
            f"{fname} ({np.mean(coefs):+.4f}, {len(coefs)}/{len(fold_coefs)} folds)"
            for fname, coefs in top5
        ]
        lines.append(f"**{stat.upper()}**: " + " | ".join(feat_strs) if top5 else f"**{stat.upper()}**: all zeroed out")
    lines.append("")

    # --- XGB monotonic insight ---
    lines.append("### XGB-Monotonic Insight (REB focus)")
    for stat in TEST_STATS:
        base_maes = results[stat]["xgb_monotonic"].get("baseline", [])
        cv_maes   = results[stat]["xgb_monotonic"].get("all_cv_27", [])
        ref_base  = results[stat]["xgb_lgb_blend"].get("baseline", [])
        if not base_maes or not cv_maes or not ref_base:
            continue
        mono_base_mean = float(np.mean(base_maes))
        mono_cv_mean   = float(np.mean(cv_maes))
        ref_base_mean  = float(np.mean(ref_base))
        ref_cv_maes    = results[stat]["xgb_lgb_blend"].get("all_cv_27", [])
        ref_cv_mean    = float(np.mean(ref_cv_maes)) if ref_cv_maes else float("nan")
        constraint_verdict = "helped" if mono_cv_mean < ref_cv_mean else "hurt"
        lines.append(
            f"- {stat.upper()}: monotonic base={mono_base_mean:.4f} cv={mono_cv_mean:.4f} "
            f"delta={mono_cv_mean-mono_base_mean:+.4f} "
            f"vs ref_cv={ref_cv_mean:.4f} → constraints {constraint_verdict}"
        )
    lines.append("")

    # --- Quantile regression finding ---
    lines.append("### Quantile Regression (LGB q50) Finding")
    lines.append("Comparing q50 CV delta vs mean-based CV delta:")
    lines.append("")
    for stat in TEST_STATS:
        q50_base = results[stat]["lgb_quantile_q50"].get("baseline", [])
        q50_cv   = results[stat]["lgb_quantile_q50"].get("all_cv_27", [])
        ref_base = results[stat]["xgb_lgb_blend"].get("baseline", [])
        ref_cv   = results[stat]["xgb_lgb_blend"].get("all_cv_27", [])
        if not (q50_base and q50_cv and ref_base and ref_cv):
            continue
        q50_delta = float(np.mean(q50_cv)) - float(np.mean(q50_base))
        ref_delta = float(np.mean(ref_cv)) - float(np.mean(ref_base))
        q50_folds = sum(1 for b, c in zip(q50_base, q50_cv) if c < b)
        verdict = "q50 BETTER at CV utilization" if q50_delta < ref_delta else "mean-pred better"
        lines.append(
            f"- {stat.upper()}: q50 delta={q50_delta:+.4f} ({q50_folds}/{len(q50_base)} folds) "
            f"vs mean-pred delta={ref_delta:+.4f} → {verdict}"
        )
    lines.append("")

    # --- Honest read ---
    lines.append("### Honest Read")

    # Best algorithm for each stat (by CV delta)
    for stat in TEST_STATS:
        alg_deltas = {}
        for alg in ALG_NAMES:
            base_maes = results[stat][alg].get("baseline", [])
            cv_maes   = results[stat][alg].get("all_cv_27", [])
            if base_maes and cv_maes:
                alg_deltas[alg] = float(np.mean(cv_maes)) - float(np.mean(base_maes))
        if alg_deltas:
            best_alg = min(alg_deltas, key=lambda a: alg_deltas[a])
            best_delta = alg_deltas[best_alg]
            lines.append(
                f"- **{stat.upper()}** best algorithm for CV: {best_alg} (delta={best_delta:+.4f})"
            )

    lines.append("")

    # Lasso zero-out check
    lines.append("**Lasso signal check:**")
    for stat in TEST_STATS:
        fold_coefs = lasso_coefs[stat].get("all_cv_27", [])
        if fold_coefs:
            n_nonzero_any = len(set(
                fname for fold_dict in fold_coefs for fname in fold_dict
            ))
            total_cv = len(ALL_CV_COLS) + 1  # +cv_n_games_cv
            pct_zero = 100.0 * (total_cv - n_nonzero_any) / total_cv
            verdict = "NOISE-DOMINATED" if pct_zero > 70 else "partial signal"
            lines.append(
                f"- {stat.upper()}: {n_nonzero_any}/{total_cv} CV features non-zero "
                f"({pct_zero:.0f}% zeroed) → {verdict}"
            )

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 60)
    print("X1b Algorithm Sweep — CV Feature Architecture Test")
    print("=" * 60)

    # 1. Load dataset
    print("\nStep 1: Loading base dataset ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # 2. Load game_date map
    print("\nStep 2: Loading game_date map ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped to dates")

    # 3. Load CV data
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # 4. Pre-compute CV matrix
    print("\nStep 4: Pre-computing CV augmentation ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {elapsed:.1f}s — {rows_with_cv}/{n} rows have CV ({pct:.2f}%)")

    # 5. Build base feature matrix
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # 6. Run walk-forward
    print(
        f"\nStep 6: Running {N_SPLITS}-fold WF — "
        f"{len(TEST_STATS)} stats × {len(CONFIGS)} configs × {len(ALG_NAMES)} algorithms "
        f"= {N_SPLITS * len(TEST_STATS) * len(CONFIGS) * len(ALG_NAMES)} trainings ..."
    )
    results, lasso_coefs = _run_walk_forward(rows, base_cols, X_base, cv_matrix, cv_n_games)

    # 7. Report
    print("\nStep 7: Generating report ...")
    report = _build_report(results, lasso_coefs)
    print(report)

    # 8. Save JSON
    out_path = os.path.join(MODELS_DIR, "test_cv_algorithms_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "test_stats": TEST_STATS,
                "algorithms": ALG_NAMES,
                "configs": CONFIGS,
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(pct, 4),
                },
                "results": results,
                "lasso_coefs": {
                    stat: {
                        cfg: [dict(d) for d in fold_list]
                        for cfg, fold_list in cfg_dict.items()
                    }
                    for stat, cfg_dict in lasso_coefs.items()
                },
                "report": report,
                "wall_time_s": round(time.time() - t_total, 1),
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
