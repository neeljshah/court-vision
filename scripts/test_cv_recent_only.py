"""
test_cv_recent_only.py — CV honesty test: measure TRUE CV signal on slices where CV exists.

Three approaches:
  1. Full-train, holdout filtered to cv_n_games > 0 (CV-restricted holdout)
  2. 2025-26-only (season slice where CV training data actually exists)
  3. Per-row MAE bucketed by cv_n_games count

Run:
    python scripts/test_cv_recent_only.py

DO NOT modify: prop_pergame.py, player_props.py, test_cv_isolated.py, or src/ files.
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
# Constants — mirror test_cv_isolated.py exactly
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

# The best config from prior runs (all 27 CV features + cv_n_games)
CONFIGS = {
    "baseline": [],
    "all_cv_27": ALL_CV_COLS,
}

# 2025-26 season cutoff
SEASON_2526_CUTOFF = "2025-10-15"


# ---------------------------------------------------------------------------
# Data loading helpers (copied from test_cv_isolated.py)
# ---------------------------------------------------------------------------
def _load_game_date_map() -> Dict[str, str]:
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
# Training helper
# ---------------------------------------------------------------------------
def _train_fold(
    stat: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_ho: np.ndarray,
    y_ho: np.ndarray,
    sw: np.ndarray,
    ho_mask: np.ndarray | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Train XGB+LGB NNLS blend.
    Returns (baseline_preds_holdout, with_cv_preds_holdout) if called with augmented X.
    Actually: returns (holdout_preds, ) — caller splits by config.

    Simplified: train one model for the given X_tr/X_ho and return holdout predictions.
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
    return preds


def _sample_weights(dates: List[str]) -> np.ndarray:
    dts = [datetime.fromisoformat(d) for d in dates]
    max_d = max(dts)
    age = np.array([(max_d - d).days / 365.0 for d in dts], dtype=float)
    return np.exp(-0.5 * age)


# ---------------------------------------------------------------------------
# Approach 1: full-train, CV-only holdout
# ---------------------------------------------------------------------------
def run_approach1(
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Train on 80%, val 10%, test 10% — report MAE filtered to cv_n_games > 0 holdout rows.
    Also collect per-row errors for Approach 3.
    """
    n = len(rows)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}

    tr_end = int(n * 0.80)
    va_end = int(n * 0.90)
    ho_end = n

    print(f"\n[Approach 1] train={tr_end} val={va_end - tr_end} holdout={ho_end - va_end}")

    # Sample weights on train
    sw = _sample_weights([rows[i]["date"] for i in range(tr_end)])

    # CV mask on holdout
    ho_cv_mask = cv_n_games[va_end:ho_end] > 0
    ho_cv_count = int(ho_cv_mask.sum())
    ho_cv_n_games_arr = cv_n_games[va_end:ho_end]

    print(f"  Holdout rows: {ho_end - va_end}  |  cv_n_games > 0: {ho_cv_count} ({100*ho_cv_count/(ho_end-va_end):.1f}%)")

    results: dict = {}  # stat -> {baseline_mae, with_cv_mae, delta, baseline_preds, with_cv_preds, y_ho}
    per_row_data: dict = {}  # stat -> (y_ho, baseline_preds, with_cv_preds, cv_n_games_ho)

    for stat in STATS:
        y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
        y_tr = y[:tr_end]
        y_val = y[tr_end:va_end]
        y_ho = y[va_end:ho_end]

        t0 = time.time()
        stat_results = {}

        # Baseline
        X_tr_b = X_base[:tr_end]
        X_val_b = X_base[tr_end:va_end]
        X_ho_b = X_base[va_end:ho_end]
        preds_base = _train_fold(stat, X_tr_b, y_tr, X_val_b, y_val, X_ho_b, y_ho, sw)

        # With CV (all_cv_27)
        cv_cols_idx = list(range(len(ALL_CV_COLS)))  # all 27
        cv_extra = cv_matrix[:, cv_cols_idx]
        cv_ngames_col = cv_n_games.reshape(-1, 1).astype(float)
        X_aug = np.hstack([X_base, cv_extra, cv_ngames_col])

        X_tr_cv = X_aug[:tr_end]
        X_val_cv = X_aug[tr_end:va_end]
        X_ho_cv = X_aug[va_end:ho_end]
        preds_cv = _train_fold(stat, X_tr_cv, y_tr, X_val_cv, y_val, X_ho_cv, y_ho, sw)

        # Full holdout MAE
        from sklearn.metrics import mean_absolute_error
        base_mae_full = float(mean_absolute_error(y_ho, preds_base))
        cv_mae_full = float(mean_absolute_error(y_ho, preds_cv))

        # Filtered to cv_n_games > 0
        if ho_cv_count > 0:
            base_mae_filtered = float(np.mean(np.abs(y_ho[ho_cv_mask] - preds_base[ho_cv_mask])))
            cv_mae_filtered = float(np.mean(np.abs(y_ho[ho_cv_mask] - preds_cv[ho_cv_mask])))
        else:
            base_mae_filtered = float("nan")
            cv_mae_filtered = float("nan")

        elapsed = time.time() - t0
        delta = cv_mae_filtered - base_mae_filtered
        delta_pct = 100.0 * delta / base_mae_filtered if base_mae_filtered > 0 else float("nan")
        print(
            f"  {stat.upper():4s}  base_full={base_mae_full:.4f}  cv_full={cv_mae_full:.4f}"
            f"  |  base_filt={base_mae_filtered:.4f}  cv_filt={cv_mae_filtered:.4f}"
            f"  delta={delta:+.4f} ({delta_pct:+.2f}%)  ({elapsed:.1f}s)",
            flush=True,
        )

        stat_results = {
            "baseline_mae_full": base_mae_full,
            "cv_mae_full": cv_mae_full,
            "baseline_mae_filtered": base_mae_filtered,
            "cv_mae_filtered": cv_mae_filtered,
            "delta_filtered": delta,
            "delta_pct_filtered": delta_pct,
            "n_holdout_total": int(ho_end - va_end),
            "n_holdout_cv": int(ho_cv_count),
        }
        results[stat] = stat_results
        per_row_data[stat] = (y_ho, preds_base, preds_cv, ho_cv_n_games_arr)

    return results, per_row_data


# ---------------------------------------------------------------------------
# Approach 2: 2025-26-only train/test
# ---------------------------------------------------------------------------
def run_approach2(
    rows: List[dict],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Use only 2025-26 rows. 60/20/20 chronological split. Full test MAE reported.
    """
    season_mask = np.array([r["date"] >= SEASON_2526_CUTOFF for r in rows])
    season_idx = np.where(season_mask)[0]
    n_season = len(season_idx)

    if n_season < 1000:
        print(f"\n[Approach 2] Only {n_season} 2025-26 rows — too few to run, skipping")
        return {}

    print(f"\n[Approach 2] 2025-26 rows: {n_season} (cutoff: {SEASON_2526_CUTOFF})")

    # Slice the arrays
    rows_2526 = [rows[i] for i in season_idx]
    X_base_2526 = X_base[season_idx]
    cv_matrix_2526 = cv_matrix[season_idx]
    cv_n_2526 = cv_n_games[season_idx]

    # Print CV coverage in this slice
    cv_cover = int((cv_n_2526 > 0).sum())
    print(f"  CV-eligible rows in 2025-26 slice: {cv_cover} ({100*cv_cover/n_season:.1f}%)")

    tr_end = int(n_season * 0.60)
    va_end = int(n_season * 0.80)
    ho_end = n_season

    print(f"  Split: train={tr_end} val={va_end - tr_end} test={ho_end - va_end}")

    sw = _sample_weights([rows_2526[i]["date"] for i in range(tr_end)])

    results: dict = {}

    for stat in STATS:
        y = np.array([r[f"target_{stat}"] for r in rows_2526], dtype=float)
        y_tr = y[:tr_end]
        y_val = y[tr_end:va_end]
        y_ho = y[va_end:ho_end]

        t0 = time.time()

        # Baseline
        preds_base = _train_fold(
            stat,
            X_base_2526[:tr_end], y_tr,
            X_base_2526[tr_end:va_end], y_val,
            X_base_2526[va_end:ho_end], y_ho,
            sw,
        )

        # With CV
        cv_ngames_col = cv_n_2526.reshape(-1, 1).astype(float)
        X_aug = np.hstack([X_base_2526, cv_matrix_2526, cv_ngames_col])

        preds_cv = _train_fold(
            stat,
            X_aug[:tr_end], y_tr,
            X_aug[tr_end:va_end], y_val,
            X_aug[va_end:ho_end], y_ho,
            sw,
        )

        from sklearn.metrics import mean_absolute_error
        base_mae = float(mean_absolute_error(y_ho, preds_base))
        cv_mae = float(mean_absolute_error(y_ho, preds_cv))
        delta = cv_mae - base_mae
        delta_pct = 100.0 * delta / base_mae if base_mae > 0 else float("nan")
        elapsed = time.time() - t0

        print(
            f"  {stat.upper():4s}  baseline={base_mae:.4f}  with_cv={cv_mae:.4f}"
            f"  delta={delta:+.4f} ({delta_pct:+.2f}%)  ({elapsed:.1f}s)",
            flush=True,
        )

        results[stat] = {
            "baseline_mae": base_mae,
            "cv_mae": cv_mae,
            "delta": delta,
            "delta_pct": delta_pct,
        }

    results["__meta__"] = {
        "n_season": n_season,
        "n_train": tr_end,
        "n_val": va_end - tr_end,
        "n_test": ho_end - va_end,
        "cv_cover": cv_cover,
        "cv_cover_pct": round(100 * cv_cover / n_season, 2),
    }
    return results


# ---------------------------------------------------------------------------
# Approach 3: Per-row MAE bucketed by cv_n_games
# ---------------------------------------------------------------------------
def run_approach3(
    per_row_data: dict,  # stat -> (y_ho, baseline_preds, with_cv_preds, cv_n_games_ho)
) -> dict:
    """
    Bucket holdout rows by cv_n_games count and compute mean MAE per bucket.
    """
    BUCKETS = [(0, 0, "0"), (1, 1, "1"), (2, 2, "2"), (3, 5, "3-5"), (6, 9999, "6+")]

    results: dict = {}

    for stat in STATS:
        if stat not in per_row_data:
            continue
        y_ho, preds_base, preds_cv, cv_n_arr = per_row_data[stat]

        abs_err_base = np.abs(y_ho - preds_base)
        abs_err_cv = np.abs(y_ho - preds_cv)

        stat_buckets = []
        for lo, hi, label in BUCKETS:
            mask = (cv_n_arr >= lo) & (cv_n_arr <= hi)
            n_bucket = int(mask.sum())
            if n_bucket == 0:
                continue
            b_mae = float(np.mean(abs_err_base[mask]))
            cv_mae = float(np.mean(abs_err_cv[mask]))
            delta = cv_mae - b_mae
            stat_buckets.append({
                "bucket": label,
                "n": n_bucket,
                "baseline_mae": b_mae,
                "cv_mae": cv_mae,
                "delta": delta,
            })
        results[stat] = stat_buckets

    return results


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------
def print_report(
    rows: List[dict],
    cv_n_games: np.ndarray,
    a1_results: dict,
    a2_results: dict,
    a3_results: dict,
    n_holdout_cv: int,
) -> str:
    n = len(rows)
    rows_with_cv = int((cv_n_games > 0).sum())
    season_rows = sum(1 for r in rows if r["date"] >= SEASON_2526_CUTOFF)
    a2_meta = a2_results.get("__meta__", {})

    # Previous WF reported values (from task spec) for comparison
    PREV_WF = {
        "pts":  ("-0.0031", "1/4"),
        "reb":  ("-0.0037", "4/4 SHIP"),
        "ast":  ("+0.0000", "0/4"),
        "fg3m": ("N/A",     "--"),
        "stl":  ("N/A",     "--"),
        "blk":  ("N/A",     "--"),
        "tov":  ("N/A",     "--"),
    }

    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append("F1 CV-RESTRICTED MAGNITUDE TEST — FINAL REPORT")
    lines.append("=" * 80)
    lines.append("")
    lines.append("### Dataset breakdown")
    lines.append(f"- Total rows: {n:,}")
    lines.append(f"- Rows with cv_n_games > 0: {rows_with_cv:,} ({100*rows_with_cv/n:.2f}%)")
    lines.append(f"- 2025-26 rows (Approach 2): {season_rows:,}")
    lines.append("")

    # ---------- Approach 1 ----------
    lines.append("### Approach 1: Full-train, CV-only holdout")
    lines.append("")
    lines.append(f"Holdout slice: last 10% of timeline, filtered to cv_n_games > 0")
    lines.append(f"- N holdout rows used (cv > 0): {n_holdout_cv}")
    lines.append("")
    lines.append(
        "| stat | baseline MAE (restricted) | with_cv MAE (restricted) "
        "| delta | delta % | full-WF reported (comparison) |"
    )
    lines.append(
        "|------|--------------------------|-------------------------|"
        "-------|---------|-------------------------------|"
    )

    for stat in STATS:
        if stat not in a1_results:
            continue
        r = a1_results[stat]
        prev_delta, prev_wf = PREV_WF.get(stat, ("N/A", "—"))
        base_f = r.get("baseline_mae_filtered")
        cv_f = r.get("cv_mae_filtered")
        delta = r.get("delta_filtered")
        dpct = r.get("delta_pct_filtered")

        def fmt(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "N/A"
            return f"{v:.4f}"

        def fmt_pct(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "N/A"
            return f"{v:+.2f}%"

        def fmt_delta(v):
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return "N/A"
            s = f"{v:+.4f}"
            return f"**{s}**" if v < 0 else s

        lines.append(
            f"| {stat} | {fmt(base_f)} | {fmt(cv_f)} | {fmt_delta(delta)} | {fmt_pct(dpct)} | {prev_delta} ({prev_wf}) |"
        )

    lines.append("")

    # ---------- Approach 2 ----------
    lines.append("### Approach 2: 2025-26-only train/test")
    lines.append("")
    if not a2_meta:
        lines.append("*Skipped — insufficient 2025-26 rows*")
    else:
        lines.append(f"- N train rows (2025-26): {a2_meta.get('n_train', 'N/A')}")
        lines.append(f"- N val rows: {a2_meta.get('n_val', 'N/A')}")
        lines.append(f"- N test rows: {a2_meta.get('n_test', 'N/A')}")
        lines.append(f"- CV-eligible rows in slice: {a2_meta.get('cv_cover', 'N/A')} ({a2_meta.get('cv_cover_pct', 'N/A')}%)")
        lines.append("")
        lines.append(
            "| stat | baseline MAE | with_cv MAE | delta | delta % |"
        )
        lines.append("|------|-------------|------------|-------|---------|")
        for stat in STATS:
            if stat not in a2_results:
                continue
            r = a2_results[stat]
            base_m = r.get("baseline_mae")
            cv_m = r.get("cv_mae")
            delta = r.get("delta")
            dpct = r.get("delta_pct")

            def fmt2(v):
                return "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.4f}"
            def fmt2d(v):
                if v is None or (isinstance(v, float) and np.isnan(v)):
                    return "N/A"
                s = f"{v:+.4f}"
                return f"**{s}**" if v < 0 else s
            def fmt2pct(v):
                return "N/A" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:+.2f}%"

            lines.append(f"| {stat} | {fmt2(base_m)} | {fmt2(cv_m)} | {fmt2d(delta)} | {fmt2pct(dpct)} |")

    lines.append("")

    # ---------- Approach 3 ----------
    lines.append("### Approach 3: MAE by CV coverage bucket")
    lines.append("")
    lines.append("For each stat, how does MAE improvement scale with cv_n_games?")
    lines.append("")
    lines.append("| stat | cv_n_games | n rows | baseline_MAE | with_cv_MAE | delta |")
    lines.append("|------|-----------|--------|-------------|------------|-------|")

    for stat in STATS:
        if stat not in a3_results:
            continue
        for b in a3_results[stat]:
            delta = b["delta"]
            dstr = f"**{delta:+.4f}**" if delta < 0 else f"{delta:+.4f}"
            lines.append(
                f"| {stat} | {b['bucket']} | {b['n']} | {b['baseline_mae']:.4f} | {b['cv_mae']:.4f} | {dstr} |"
            )

    lines.append("")

    # ---------- Honest read ----------
    lines.append("### Honest read")
    lines.append("")

    # Improvement stats
    improved_a1 = [s for s in STATS if s in a1_results and a1_results[s].get("delta_filtered", 0) < 0]
    improved_a2 = [s for s in STATS if s in a2_results and isinstance(a2_results[s], dict) and a2_results[s].get("delta", 0) < 0]

    # Check if CV-restricted MAE is bigger (in absolute improvement) than the full WF
    lines.append("**Per-stat CV signal magnitude comparison:**")
    for stat in STATS:
        if stat not in a1_results:
            continue
        r1 = a1_results[stat]
        base_f = r1.get("baseline_mae_filtered")
        cv_f = r1.get("cv_mae_filtered")
        delta_f = r1.get("delta_filtered")
        dpct = r1.get("delta_pct_filtered")

        in_a2 = stat in improved_a2
        in_a1 = stat in improved_a1

        if base_f is None or np.isnan(base_f):
            lines.append(f"- **{stat.upper()}**: no CV-eligible holdout rows")
            continue

        consistent = in_a1 and in_a2
        lines.append(
            f"- **{stat.upper()}**: Approach 1 delta = {delta_f:+.4f} ({dpct:+.2f}%)  "
            f"| Approach 2 {'IMPROVED' if in_a2 else 'REGRESSED'}  "
            f"| Consistent: {'YES' if consistent else 'NO'}"
        )

    lines.append("")

    # Check bucket trend
    lines.append("**Bucket analysis -- does CV improvement scale with cv_n_games?**")
    for stat in STATS:
        if stat not in a3_results:
            continue
        buckets = a3_results[stat]
        if len(buckets) < 2:
            continue
        # Check if delta improves (more negative) as cv_n_games increases
        deltas = [b["delta"] for b in buckets]
        trend = "SCALES (more CV = better)" if deltas[-1] < deltas[0] else "FLAT or REVERSES"
        lines.append(f"- **{stat.upper()}**: {trend}  |  buckets: " +
                     ", ".join(f"{b['bucket']}={b['delta']:+.4f}" for b in buckets))

    lines.append("")

    output = "\n".join(lines)
    # Print safely on Windows (replace unencodable chars)
    safe = output.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8", errors="replace")
    print(safe)
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 60)
    print("F1 CV-RESTRICTED MAGNITUDE TEST")
    print("=" * 60)

    # ---- Step 1: Load dataset ----
    print("\nStep 1: Loading base dataset ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n:,} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- Step 2: Load game_date map ----
    print("\nStep 2: Loading game_date map ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped")

    # ---- Step 3: Load CV data ----
    print("\nStep 3: Loading CV feature data ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} players have CV history")

    # ---- Step 4: Pre-compute CV matrix ----
    print("\nStep 4: Pre-computing CV augmentation matrix ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Total rows: {n:,}  |  cv_n_games > 0: {rows_with_cv:,} ({pct:.2f}%)")

    # Print cv_n_games distribution
    unique_vals, counts = np.unique(cv_n_games, return_counts=True)
    print("  cv_n_games distribution:")
    for v, c in zip(unique_vals[:10], counts[:10]):
        print(f"    {v}: {c:,}")

    # ---- Step 5: Build base feature matrix ----
    print("\nStep 5: Building X_base ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- Step 6: Approach 1 ----
    print("\n" + "=" * 60)
    print("APPROACH 1: Full-train, CV-restricted holdout")
    print("=" * 60)
    a1_results, per_row_data = run_approach1(rows, X_base, cv_matrix, cv_n_games)

    # Grab n_holdout_cv from first stat
    n_holdout_cv = 0
    for stat in STATS:
        if stat in a1_results:
            n_holdout_cv = a1_results[stat].get("n_holdout_cv", 0)
            break

    # ---- Step 7: Approach 2 ----
    print("\n" + "=" * 60)
    print("APPROACH 2: 2025-26-only train/test")
    print("=" * 60)
    a2_results = run_approach2(rows, X_base, cv_matrix, cv_n_games)

    # ---- Step 8: Approach 3 ----
    print("\n" + "=" * 60)
    print("APPROACH 3: Per-row MAE by cv_n_games bucket")
    print("=" * 60)
    a3_results = run_approach3(per_row_data)

    # ---- Step 9: Save JSON first (before report so crash doesn't lose data) ----
    out_path = os.path.join(MODELS_DIR, "test_cv_recent_only_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "approach1": a1_results,
                "approach2": a2_results,
                "approach3": {
                    stat: bkts for stat, bkts in a3_results.items()
                },
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(pct, 4),
                },
                "wall_time_s": round(time.time() - t_total, 1),
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")

    # ---- Step 10: Report ----
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    # Use sys.stdout with utf-8 encoding to avoid cp1252 issues on Windows
    import io
    report_text = print_report(
        rows, cv_n_games, a1_results, a2_results, a3_results, n_holdout_cv
    )
    # Write report to file with utf-8 encoding
    report_path = os.path.join(MODELS_DIR, "test_cv_recent_only_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Report saved to: {report_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
