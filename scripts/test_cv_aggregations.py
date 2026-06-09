"""
test_cv_aggregations.py — CV feature aggregation sweep (X1a experiment).

Tests 10 aggregation strategies for CV features against a no-CV baseline,
running only on REB, PTS, AST for speed.  Gate is fully OFF (no PROP_USE_CV).

Run:
    python scripts/test_cv_aggregations.py

Outputs:
    data/models/test_cv_aggregations_results.json
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import sys
import time
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

# --- GATE OFF: ensure cv features are not injected by the base dataset -------
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

# Only test these 3 stats for speed
TARGET_STATS = ["reb", "pts", "ast"]

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


# ---------------------------------------------------------------------------
# Data loading (identical to test_cv_isolated.py)
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
    """Return {game_id: 'YYYY-MM-DD'} from all season_games_*.json files."""
    import glob as _glob
    gd: Dict[str, str] = {}
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
    """
    Returns by_player: {player_id: [(game_date, feature_name, value), ...]}
    sorted ascending by game_date.
    """
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


# ---------------------------------------------------------------------------
# Core helper: get ordered per-game data for a player up to row_date
# Returns list of dicts {feature_name: value} ordered oldest→newest
# Also returns list of game_dates in same order and last_game_date
# ---------------------------------------------------------------------------
def _get_player_prior_games(
    player_id: int,
    row_date: str,
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[List[Dict[str, float]], List[str]]:
    """
    Returns (games_oldest_to_newest, game_dates_oldest_to_newest).
    Each element in games is a dict of {feature_name: value} for that game.
    Only includes strictly prior games (date < row_date).
    """
    history = by_player.get(player_id, [])
    if not history:
        return [], []

    # Binary search for cutoff: all entries with date < row_date
    lo, hi = 0, len(history)
    while lo < hi:
        mid = (lo + hi) // 2
        if history[mid][0] < row_date:
            lo = mid + 1
        else:
            hi = mid
    cutoff_idx = lo

    if cutoff_idx == 0:
        return [], []

    # Collect per-game feature dicts
    # Walk forward through history[:cutoff_idx] grouping by date
    game_dicts: Dict[str, Dict[str, float]] = {}
    ordered_dates: List[str] = []
    for gdate, fname, fval in history[:cutoff_idx]:
        if gdate not in game_dicts:
            game_dicts[gdate] = {}
            ordered_dates.append(gdate)
        game_dicts[gdate][fname] = fval

    # ordered_dates is already sorted ascending (history was sorted)
    games_ordered = [game_dicts[d] for d in ordered_dates]
    return games_ordered, ordered_dates


# ---------------------------------------------------------------------------
# Aggregation functions
# Each returns (feature_dict, n_games_contributing, last_game_date_or_None)
# ---------------------------------------------------------------------------

def _agg_window_mean(
    games: List[Dict[str, float]], dates: List[str], window: Optional[int]
) -> Tuple[Dict[str, float], int]:
    """Equal-weighted mean over last `window` games (None = all)."""
    if not games:
        return {}, 0
    if window is not None:
        games = games[-window:]
        dates = dates[-window:]

    feature_sums: Dict[str, float] = defaultdict(float)
    feature_counts: Dict[str, int] = defaultdict(int)
    for g in games:
        for fname, fval in g.items():
            feature_sums[fname] += fval
            feature_counts[fname] += 1

    n = len(games)
    avgs = {fname: feature_sums[fname] / feature_counts[fname]
            for fname in feature_sums}
    return avgs, n


def _agg_exp_decay(
    games: List[Dict[str, float]], half_life: float
) -> Tuple[Dict[str, float], int]:
    """
    Exponential decay weighting.  Most recent game has highest weight.
    weight[i] = exp(-game_idx / half_life) where game_idx=0 is most recent.
    """
    if not games:
        return {}, 0

    n = len(games)
    # game_idx=0 is most recent; iterate reversed
    feature_wsum: Dict[str, float] = defaultdict(float)
    feature_wnorm: Dict[str, float] = defaultdict(float)

    for rev_idx, g in enumerate(reversed(games)):
        w = math.exp(-rev_idx / half_life)
        for fname, fval in g.items():
            feature_wsum[fname] += w * fval
            feature_wnorm[fname] += w

    avgs = {fname: feature_wsum[fname] / feature_wnorm[fname]
            for fname in feature_wsum}
    return avgs, n


def _agg_min_max_median(
    games: List[Dict[str, float]], window: int = 5
) -> Tuple[Dict[str, float], int]:
    """
    Returns min/max/median per feature over last `window` games.
    Column names: <feat>_min, <feat>_max, <feat>_median.
    """
    if not games:
        return {}, 0
    games = games[-window:]
    n = len(games)

    # Collect per-feature arrays
    feature_vals: Dict[str, List[float]] = defaultdict(list)
    for g in games:
        for fname, fval in g.items():
            feature_vals[fname].append(fval)

    result: Dict[str, float] = {}
    for fname, vals in feature_vals.items():
        arr = np.array(vals)
        result[f"{fname}_min"] = float(arr.min())
        result[f"{fname}_max"] = float(arr.max())
        result[f"{fname}_median"] = float(np.median(arr))
    return result, n


def _agg_std_mean(
    games: List[Dict[str, float]], window: int = 5
) -> Tuple[Dict[str, float], int]:
    """
    Returns mean + std per feature over last `window` games.
    Column names: <feat>_mean (same as baseline), <feat>_std (new).
    std=0 if fewer than 2 games.
    """
    if not games:
        return {}, 0
    games = games[-window:]
    n = len(games)

    feature_vals: Dict[str, List[float]] = defaultdict(list)
    for g in games:
        for fname, fval in g.items():
            feature_vals[fname].append(fval)

    result: Dict[str, float] = {}
    for fname, vals in feature_vals.items():
        arr = np.array(vals)
        result[f"{fname}_mean"] = float(arr.mean())
        result[f"{fname}_std"] = float(arr.std()) if len(arr) >= 2 else 0.0
    return result, n


# ---------------------------------------------------------------------------
# Aggregate CV matrix builders for each config
# ---------------------------------------------------------------------------

def _build_agg_matrix_window(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    window: Optional[int],
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Build (n, 27) CV matrix + (n,) n_games using equal-weighted window mean.
    Returns matrix, n_games, coverage_pct.
    """
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        games, dates = _get_player_prior_games(pid, rdate, by_player)
        avgs, ng = _agg_window_mean(games, dates, window)
        cv_n_games[i] = ng
        for fname, val in avgs.items():
            idx = feat_idx.get(fname)
            if idx is not None:
                cv_matrix[i, idx] = val

    rows_with_cv = int((cv_n_games > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return cv_matrix, cv_n_games, coverage


def _build_agg_matrix_decay(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    half_life: float,
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """Build (n, 27) CV matrix using exponential decay weighting."""
    n = len(rows)
    n_feats = len(ALL_CV_COLS)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}
    cv_matrix = np.zeros((n, n_feats), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        games, _ = _get_player_prior_games(pid, rdate, by_player)
        avgs, ng = _agg_exp_decay(games, half_life)
        cv_n_games[i] = ng
        for fname, val in avgs.items():
            idx = feat_idx.get(fname)
            if idx is not None:
                cv_matrix[i, idx] = val

    rows_with_cv = int((cv_n_games > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return cv_matrix, cv_n_games, coverage


def _build_agg_matrix_min_max_median(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float, List[str]]:
    """
    Build (n, 27*3) matrix for min/max/median per feature.
    Returns matrix, n_games, coverage_pct, col_names.
    """
    n = len(rows)
    col_names = []
    for f in ALL_CV_COLS:
        col_names += [f"{f}_min", f"{f}_max", f"{f}_median"]
    col_idx = {c: i for i, c in enumerate(col_names)}

    cv_matrix = np.zeros((n, len(col_names)), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        games, _ = _get_player_prior_games(pid, rdate, by_player)
        result, ng = _agg_min_max_median(games, window=5)
        cv_n_games[i] = ng
        for cname, val in result.items():
            idx = col_idx.get(cname)
            if idx is not None:
                cv_matrix[i, idx] = val

    rows_with_cv = int((cv_n_games > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return cv_matrix, cv_n_games, coverage, col_names


def _build_agg_matrix_std_mean(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float, List[str]]:
    """
    Build (n, 27*2) matrix for mean+std per feature.
    Returns matrix, n_games, coverage_pct, col_names.
    """
    n = len(rows)
    col_names = []
    for f in ALL_CV_COLS:
        col_names += [f"{f}_mean", f"{f}_std"]
    col_idx = {c: i for i, c in enumerate(col_names)}

    cv_matrix = np.zeros((n, len(col_names)), dtype=float)
    cv_n_games = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        games, _ = _get_player_prior_games(pid, rdate, by_player)
        result, ng = _agg_std_mean(games, window=5)
        cv_n_games[i] = ng
        for cname, val in result.items():
            idx = col_idx.get(cname)
            if idx is not None:
                cv_matrix[i, idx] = val

    rows_with_cv = int((cv_n_games > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return cv_matrix, cv_n_games, coverage, col_names


def _build_agg_matrix_time_since(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Single column: days_since_last_cv_game.
    0 = never had a CV game before this row.
    n_games = 1 if any prior CV game exists else 0 (for coverage counting).
    """
    n = len(rows)
    col = np.zeros((n, 1), dtype=float)
    n_games_arr = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        _, dates = _get_player_prior_games(pid, rdate, by_player)
        if dates:
            last_date = dates[-1]  # most recent prior CV game
            try:
                row_dt = datetime.fromisoformat(rdate)
                last_dt = datetime.fromisoformat(last_date)
                days = max(0.0, (row_dt - last_dt).days)
            except Exception:
                days = 0.0
            col[i, 0] = days
            n_games_arr[i] = 1

    rows_with_cv = int((n_games_arr > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return col, n_games_arr, coverage


def _build_agg_matrix_count_features(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
    config_name: str,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Two columns: cv_n_games_total (career count), cv_n_games_last30 (last 30 days).
    Does NOT include the per-feature averages — tests if count alone matters.
    """
    n = len(rows)
    col = np.zeros((n, 2), dtype=float)
    n_games_arr = np.zeros(n, dtype=int)

    t0 = time.time()
    for i, row in enumerate(rows):
        if i % 20000 == 0 and i > 0:
            print(f"    [{config_name}] {i}/{n} ({time.time()-t0:.1f}s)", flush=True)
        pid = row.get("player_id")
        rdate = row.get("date", "")
        _, dates = _get_player_prior_games(pid, rdate, by_player)
        total = len(dates)
        col[i, 0] = total

        if dates and rdate:
            try:
                row_dt = datetime.fromisoformat(rdate)
                last30 = sum(
                    1 for d in dates
                    if (row_dt - datetime.fromisoformat(d)).days <= 30
                )
                col[i, 1] = last30
            except Exception:
                pass

        if total > 0:
            n_games_arr[i] = total

    rows_with_cv = int((n_games_arr > 0).sum())
    coverage = 100.0 * rows_with_cv / n
    print(f"  [{config_name}] coverage: {rows_with_cv}/{n} = {coverage:.2f}%  ({time.time()-t0:.1f}s)")
    return col, n_games_arr, coverage


# ---------------------------------------------------------------------------
# Training (identical to test_cv_isolated.py)
# ---------------------------------------------------------------------------
def _train_fold(
    stat: str,
    X_tr: np.ndarray, y_tr: np.ndarray,
    X_val: np.ndarray, y_val: np.ndarray,
    X_ho: np.ndarray, y_ho: np.ndarray,
    sw: np.ndarray,
) -> float:
    """Train XGB+LGB, NNLS blend on val, return holdout MAE."""
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
    return float(mean_absolute_error(y_ho, preds))


# ---------------------------------------------------------------------------
# Walk-forward runner
# ---------------------------------------------------------------------------
def _run_walk_forward(
    rows: List[dict],
    X_base: np.ndarray,
    agg_matrices: Dict[str, Tuple[np.ndarray, np.ndarray]],
) -> dict:
    """
    agg_matrices: {config_name: (X_aug_extra_cols, n_games_arr)}
    X_aug_extra_cols can be 0 columns (for baseline) or any shape (n, k).

    Returns results[stat][config] = [fold_mae, ...]
    """
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]
    config_names = list(agg_matrices.keys())

    results: dict = {
        stat: {cfg: [] for cfg in config_names}
        for stat in TARGET_STATS
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

        for stat in TARGET_STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg_name, (extra_cols, ng_arr) in agg_matrices.items():
                if extra_cols.shape[1] > 0:
                    ng_col = ng_arr.reshape(-1, 1).astype(float)
                    X_aug = np.hstack([X_base, extra_cols, ng_col])
                else:
                    X_aug = X_base

                X_tr = X_aug[:tr_end]
                X_val_m = X_aug[tr_end:va_end]
                X_ho_m = X_aug[va_end:te_end]

                mae = _train_fold(stat, X_tr, y_tr, X_val_m, y_val, X_ho_m, y_ho, sw)
                results[stat][cfg_name].append(mae)

            fold_elapsed = time.time() - fold_t0
            base_mae = results[stat]["baseline"][-1]
            deltas = {
                cfg: results[stat][cfg][-1] - base_mae
                for cfg in config_names if cfg != "baseline"
            }
            delta_strs = []
            for cfg, d in deltas.items():
                marker = "**" if d < 0 else ""
                delta_strs.append(f"{cfg}={marker}{d:+.4f}{marker}")
            print(
                f"  {stat.upper():4s}  baseline={base_mae:.4f}  "
                + "  ".join(delta_strs)
                + f"  ({fold_elapsed:.1f}s)",
                flush=True,
            )

    return results


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------
def _build_report(
    results: dict,
    coverage: Dict[str, float],
) -> str:
    """Build the full markdown report string."""
    config_names = list(next(iter(results.values())).keys())
    non_base = [c for c in config_names if c != "baseline"]

    lines = [
        "",
        "## X1a CV Aggregation Sweep — Final Report",
        "",
        "### Coverage parity check",
        "| config | coverage % | flag |",
        "|--------|--------:|-------|",
    ]

    base_cov = coverage.get("baseline", 0.0)
    for cfg, cov in coverage.items():
        diff = abs(cov - base_cov)
        flag = "HIGH COVERAGE DELTA" if diff > 2.0 else "ok"
        if cfg == "baseline":
            flag = "reference"
        lines.append(f"| {cfg} | {cov:.2f}% | {flag} |")
    lines.append("")

    per_stat_detail: Dict[str, dict] = {}

    for stat in TARGET_STATS:
        stat_res = results[stat]
        base_maes = stat_res.get("baseline", [])
        if not base_maes:
            lines.append(f"### {stat.upper()} — no data\n")
            continue

        base_mean = float(np.mean(base_maes))
        n_folds = len(base_maes)

        lines.append(f"### {stat.upper()} results")
        lines.append(
            "| config | folds | best fold delta | worst fold delta "
            "| mean delta | folds_better/N | vs baseline |"
        )
        lines.append(
            "|--------|------:|----------------:|"
            "-----------------:|:----------:|:--------------:|:-----------|"
        )

        cfg_stats: Dict[str, dict] = {}
        for cfg in config_names:
            cfg_maes = stat_res.get(cfg, [])
            if not cfg_maes:
                cfg_stats[cfg] = {"mean": float("inf"), "folds_better": 0, "delta": 0.0}
                lines.append(f"| {cfg} | 0 | n/a | n/a | n/a | 0/{n_folds} | n/a |")
                continue

            cfg_mean = float(np.mean(cfg_maes))
            deltas_per_fold = [cm - bm for cm, bm in zip(cfg_maes, base_maes)]
            best_delta = min(deltas_per_fold)
            worst_delta = max(deltas_per_fold)
            mean_delta = cfg_mean - base_mean
            folds_better = sum(1 for d in deltas_per_fold if d < 0)

            cfg_stats[cfg] = {
                "mean": cfg_mean,
                "mean_delta": mean_delta,
                "folds_better": folds_better,
                "n_folds": n_folds,
            }

            marker = "**" if mean_delta < 0 else ""
            vs_base = "BETTER" if mean_delta < 0 else ("tie" if abs(mean_delta) < 0.0001 else "worse")
            lines.append(
                f"| {marker}{cfg}{marker} | {n_folds} "
                f"| {best_delta:+.4f} | {worst_delta:+.4f} "
                f"| {mean_delta:+.4f} | {folds_better}/{n_folds} | {vs_base} |"
            )

        lines.append("")
        per_stat_detail[stat] = cfg_stats

    # Verdict per stat
    lines.append("### Verdict per stat")
    for stat in TARGET_STATS:
        stat_res = results[stat]
        base_maes = stat_res.get("baseline", [])
        if not base_maes:
            lines.append(f"- **{stat.upper()}**: no data")
            continue

        base_mean = float(np.mean(base_maes))
        cfg_details = per_stat_detail.get(stat, {})
        best_cfg = "baseline"
        best_mean = base_mean
        for cfg, info in cfg_details.items():
            if cfg == "baseline":
                continue
            if info["mean"] < best_mean:
                best_mean = info["mean"]
                best_cfg = cfg

        delta_str = ""
        if best_cfg != "baseline":
            d = best_mean - base_mean
            folds_b = cfg_details[best_cfg]["folds_better"]
            n_f = cfg_details[best_cfg]["n_folds"]
            delta_str = f" (delta={d:+.4f}, {folds_b}/{n_f} folds better)"
        lines.append(f"- **{stat.upper()}**: best config = `{best_cfg}`{delta_str}")

    lines.append("")
    lines.append("### Honest read")

    # Aggregate: how many configs beat baseline across how many stats?
    configs_with_any_win = set()
    configs_with_all_fold_win: Dict[str, List[str]] = {}  # cfg -> list of stats
    for stat in TARGET_STATS:
        base_maes = results[stat].get("baseline", [])
        if not base_maes:
            continue
        n_folds = len(base_maes)
        for cfg in non_base:
            cfg_maes = results[stat].get(cfg, [])
            if not cfg_maes:
                continue
            folds_better = sum(1 for cm, bm in zip(cfg_maes, base_maes) if cm < bm)
            if folds_better > 0:
                configs_with_any_win.add(cfg)
            if folds_better == n_folds:
                configs_with_all_fold_win.setdefault(cfg, []).append(stat)

    if not configs_with_any_win:
        lines.append(
            "- No aggregation variant beat the baseline on any fold for any stat. "
            "Equal-weighted last-5 mean captures the available signal; "
            "smarter aggregation adds no value at current CV data density (~12% coverage)."
        )
    else:
        lines.append(
            f"- {len(configs_with_any_win)} config(s) beat baseline on at least one fold: "
            + ", ".join(sorted(configs_with_any_win))
        )

    if configs_with_all_fold_win:
        ship_list = []
        for cfg, stats in configs_with_all_fold_win.items():
            ship_list.append(f"`{cfg}` on {'+'.join(s.upper() for s in stats)}")
        lines.append(
            "- **SHIP CANDIDATES** (beat baseline ALL folds): " + "; ".join(ship_list)
        )
    else:
        lines.append("- No config beat baseline on ALL folds for any stat — nothing to ship.")

    lines.append("")
    lines.append("### Recommended further tests")
    lines.append(
        "- If coverage grows to >30%, re-run this sweep — most aggregation effects "
        "are noise at 12% coverage because ~88% of rows carry zero CV signal regardless."
    )
    lines.append(
        "- If decay variants show consistent direction (even if not 4/4 folds), "
        "try narrower half-lives (h=2 or h=3)."
    )
    lines.append(
        "- min/max/median tripling: if any stat improves, ablate to single dimension "
        "(max alone or median alone) to avoid unnecessary feature bloat."
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    # 1. Load dataset
    print("=" * 70)
    print("Step 1: Loading base dataset ...")
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
    print(f"  {len(by_player)} players have CV history")

    # 4. Build base feature matrix
    print("\nStep 4: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # 5. Pre-compute all aggregation matrices
    # Each entry: (extra_cols_array, n_games_array)
    # baseline has 0 extra cols (no CV), coverage = baseline's all-history
    print("\nStep 5: Pre-computing all aggregation matrices ...")
    print("  (This is the slow step — 10 configs × ~100k rows)")

    agg_matrices: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    coverage: Dict[str, float] = {}

    # Config 1 — baseline (no CV columns, all zeros)
    print("\n--- Config 1: baseline (no CV) ---")
    empty = np.zeros((n, 0), dtype=float)
    ng_empty = np.zeros(n, dtype=int)
    agg_matrices["baseline"] = (empty, ng_empty)
    coverage["baseline"] = 0.0  # no CV, coverage irrelevant; computed from all-history for reference

    # Also compute coverage reference (how many rows have any CV data)
    t0 = time.time()
    cov_ref = 0
    for i, row in enumerate(rows):
        pid = row.get("player_id")
        rdate = row.get("date", "")
        games, _ = _get_player_prior_games(pid, rdate, by_player)
        if games:
            cov_ref += 1
    coverage["baseline"] = 100.0 * cov_ref / n
    print(f"  baseline coverage reference (any prior CV game): {coverage['baseline']:.2f}% ({time.time()-t0:.1f}s)")

    # Config 2 — last-3 mean
    print("\n--- Config 2: last-3 mean ---")
    mat2, ng2, cov2 = _build_agg_matrix_window(rows, by_player, window=3, config_name="last3_mean")
    agg_matrices["last3_mean"] = (mat2, ng2)
    coverage["last3_mean"] = cov2

    # Config 1 (reference/all_cv_27) — last-5 mean (all 27 features)
    print("\n--- Config 1 (reference): last-5 mean (all_cv_27) ---")
    mat_ref, ng_ref, cov_ref2 = _build_agg_matrix_window(rows, by_player, window=5, config_name="last5_mean")
    agg_matrices["last5_mean"] = (mat_ref, ng_ref)
    coverage["last5_mean"] = cov_ref2

    # Config 3 — last-10 mean
    print("\n--- Config 3: last-10 mean ---")
    mat3, ng3, cov3 = _build_agg_matrix_window(rows, by_player, window=10, config_name="last10_mean")
    agg_matrices["last10_mean"] = (mat3, ng3)
    coverage["last10_mean"] = cov3

    # Config 4 — all-history mean
    print("\n--- Config 4: all-history mean ---")
    mat4, ng4, cov4 = _build_agg_matrix_window(rows, by_player, window=None, config_name="all_history_mean")
    agg_matrices["all_history_mean"] = (mat4, ng4)
    coverage["all_history_mean"] = cov4

    # Config 5 — exp decay half-life=5
    print("\n--- Config 5: exp decay h=5 ---")
    mat5, ng5, cov5 = _build_agg_matrix_decay(rows, by_player, half_life=5.0, config_name="decay_h5")
    agg_matrices["decay_h5"] = (mat5, ng5)
    coverage["decay_h5"] = cov5

    # Config 6 — exp decay half-life=10
    print("\n--- Config 6: exp decay h=10 ---")
    mat6, ng6, cov6 = _build_agg_matrix_decay(rows, by_player, half_life=10.0, config_name="decay_h10")
    agg_matrices["decay_h10"] = (mat6, ng6)
    coverage["decay_h10"] = cov6

    # Config 7 — min/max/median
    print("\n--- Config 7: min/max/median (last-5) ---")
    mat7, ng7, cov7, _ = _build_agg_matrix_min_max_median(rows, by_player, config_name="minmaxmed")
    agg_matrices["minmaxmed"] = (mat7, ng7)
    coverage["minmaxmed"] = cov7

    # Config 8 — std+mean
    print("\n--- Config 8: std+mean (last-5) ---")
    mat8, ng8, cov8, _ = _build_agg_matrix_std_mean(rows, by_player, config_name="std_mean")
    agg_matrices["std_mean"] = (mat8, ng8)
    coverage["std_mean"] = cov8

    # Config 9 — time-since-last-cv
    print("\n--- Config 9: time-since-last-CV-game ---")
    mat9, ng9, cov9 = _build_agg_matrix_time_since(rows, by_player, config_name="time_since")
    agg_matrices["time_since"] = (mat9, ng9)
    coverage["time_since"] = cov9

    # Config 10 — count features
    print("\n--- Config 10: count features ---")
    mat10, ng10, cov10 = _build_agg_matrix_count_features(rows, by_player, config_name="count_feats")
    agg_matrices["count_feats"] = (mat10, ng10)
    coverage["count_feats"] = cov10

    print(f"\nAll aggregation matrices ready. Starting walk-forward ...")

    # 6. Walk-forward
    print(f"\nStep 6: {N_SPLITS}-fold WF for {len(TARGET_STATS)} stats × {len(agg_matrices)} configs ...")
    results = _run_walk_forward(rows, X_base, agg_matrices)

    # 7. Report
    print("\n" + "=" * 70)
    report = _build_report(results, coverage)
    print(report)

    # 8. Save JSON
    out_path = os.path.join(MODELS_DIR, "test_cv_aggregations_results.json")
    serializable_results = {
        stat: {cfg: maes for cfg, maes in stat_res.items()}
        for stat, stat_res in results.items()
    }
    with open(out_path, "w") as f:
        json.dump(
            {
                "coverage": coverage,
                "results": serializable_results,
                "report": report,
                "wall_time_s": round(time.time() - t_total, 1),
                "target_stats": TARGET_STATS,
                "n_configs": len(agg_matrices),
                "n_folds": N_SPLITS,
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time() - t_total:.1f}s")


if __name__ == "__main__":
    main()
