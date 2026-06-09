"""
test_cv_isolated.py — Standalone CV feature test harness (DO NOT modify prod files).

Tests 4 CV feature configs against the baseline XGB+LGB blend on a 4-fold
walk-forward.  Gate is kept fully OFF throughout (no PROP_USE_CV env var).

Run:
    python scripts/test_cv_isolated.py
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

# --- GATE OFF: ensure cv features are not injected by the base dataset -------
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
    # Original 22 features (P0/P0.5)
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

# 7 "basic" CV features (overlap with NBA API signals)
BASIC_7 = [
    "avg_defender_distance",
    "contested_shot_rate",
    "shot_zone_paint_pct",
    "shot_zone_3pt_pct",
    "shots_per_possession",
    "possession_duration_avg",
    "play_type_transition_pct",
]

# 7 "mechanical" CV features — NOT available via NBA API
MECHANICAL_7 = [
    "avg_contest_arm_angle",
    "avg_closeout_speed",
    "avg_fatigue_proxy",
    "catch_shoot_pct",
    "avg_dribble_count",
    "second_chance_rate",
    "avg_shot_distance",
]

# 5 P1 Tier-1 per-frame features
TIER1_5 = [
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# Configs: name -> list of CV feature names (raw, without cv_ prefix)
#   cv_n_games_cv is appended automatically when the list is non-empty
CONFIGS = {
    "baseline":     [],
    "basic_8":      BASIC_7,            # + cv_n_games_cv = 8 total
    "mechanical_7": MECHANICAL_7,       # + cv_n_games_cv = 8 total
    "all_cv_22":    ALL_CV_COLS[:22],   # original 22 features + cv_n_games = 23 total
    "tier1_5":      TIER1_5,            # P1 only: 5 Tier-1 + cv_n_games = 6 total
    "all_cv_27":    ALL_CV_COLS,        # all 27 + cv_n_games = 28 total
}

N_SPLITS = 4


# ---------------------------------------------------------------------------
# Step 1: Load game_id -> game_date map from season_games JSON files
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
# Step 2: Bulk-load cv_features from DB, aggregate per (player_id, date)
# ---------------------------------------------------------------------------
def _load_cv_data(
    game_date_map: Dict[str, str],
) -> Tuple[Dict[Tuple[int, str], Dict[str, float]], Dict[Tuple[int, str], str]]:
    """
    Returns:
        player_cv_history:  {player_id: [(game_date_str, feature_name, value), ...]}
                            sorted by game_date ascending.
        Delivered as a per-player sorted list of (date, feature_name, value) triples
        to support O(log n) slicing.
    """
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT player_id, game_id, feature_name, feature_value FROM cv_features"
    ).fetchall()
    conn.close()

    # group: player_id -> list of (game_date, feature_name, value)
    # Only include rows whose game_id we can resolve to a date
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

    # Sort each player's history by game_date
    for pid in by_player:
        by_player[pid].sort(key=lambda x: x[0])

    print(f"  CV rows resolved: {n_resolved}  |  missing game_date: {n_missing_date}")
    return by_player


def _compute_last5_cv(
    player_id: int,
    row_date: str,
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[Dict[str, float], int]:
    """
    Aggregate the player's last-5 CV games where game_date < row_date.
    Returns ({feature_name: mean_value, ...}, n_games_contributed).
    """
    history = by_player.get(player_id, [])
    if not history:
        return {}, 0

    # Binary search for the cutoff: all entries with date < row_date
    # history is sorted by date string (ISO format, so lexicographic == chronological)
    lo, hi = 0, len(history)
    while lo < hi:
        mid = (lo + hi) // 2
        if history[mid][0] < row_date:
            lo = mid + 1
        else:
            hi = mid
    cutoff_idx = lo  # history[:cutoff_idx] are all strictly before row_date

    if cutoff_idx == 0:
        return {}, 0

    # Take up to last 5 distinct games before cutoff
    # Collect game dates (in reverse) to get up to 5 distinct games
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
# Step 3: Pre-compute CV augmentation for all rows
# ---------------------------------------------------------------------------
def _build_cv_matrix(
    rows: List[dict],
    by_player: Dict[int, List[Tuple[str, str, float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Returns:
        cv_matrix  — (n_rows, 22) float array, one column per ALL_CV_COLS feature
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
# Step 4: Walk-forward training (XGB + LGB only, no MLP)
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

    # NNLS blend fit on val
    stacker = LinearRegression(positive=True, fit_intercept=False)
    stacker.fit(np.column_stack([xv, lv]), y_val)
    w = stacker.coef_
    # guard against degenerate weights
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


def _run_walk_forward(
    rows: List[dict],
    base_cols: List[str],
    X_base: np.ndarray,
    cv_matrix: np.ndarray,
    cv_n_games: np.ndarray,
) -> dict:
    """
    Run 4-fold WF for each (stat, config).
    Returns nested dict: results[stat][config] = [fold_mae, ...]
    """
    n = len(rows)
    feat_idx = {f: i for i, f in enumerate(ALL_CV_COLS)}

    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    # Initialise results storage
    results: dict = {
        stat: {cfg: [] for cfg in CONFIGS}
        for stat in STATS
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

        # Compute sample weights (exponential decay by age in years)
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(
            f"\n[fold {fold_idx+1}/{N_SPLITS}] tr={tr_end} val={va_end-tr_end} "
            f"ho={te_end-va_end}",
            flush=True,
        )

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr = y[:tr_end]
            y_val = y[tr_end:va_end]
            y_ho = y[va_end:te_end]

            fold_t0 = time.time()
            for cfg_name, cv_feature_names in CONFIGS.items():
                if cv_feature_names:
                    # Append CV columns + cv_n_games_cv
                    cv_cols_idx = [feat_idx[f] for f in cv_feature_names if f in feat_idx]
                    cv_extra = cv_matrix[:, cv_cols_idx]  # (n, k)
                    cv_ngames_col = cv_n_games.reshape(-1, 1).astype(float)
                    X_aug = np.hstack([X_base, cv_extra, cv_ngames_col])
                else:
                    X_aug = X_base

                X_tr = X_aug[:tr_end]
                X_val = X_aug[tr_end:va_end]
                X_ho = X_aug[va_end:te_end]

                mae = _train_fold(
                    stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw
                )
                results[stat][cfg_name].append(mae)

            fold_elapsed = time.time() - fold_t0
            baseline_mae = results[stat]["baseline"][-1]
            deltas = {
                cfg: results[stat][cfg][-1] - baseline_mae
                for cfg in CONFIGS if cfg != "baseline"
            }
            delta_str = "  ".join(
                f"{cfg}={d:+.4f}" for cfg, d in deltas.items()
            )
            print(
                f"  {stat.upper():4s}  baseline={baseline_mae:.4f}  {delta_str}"
                f"  ({fold_elapsed:.1f}s)",
                flush=True,
            )

    return results


# ---------------------------------------------------------------------------
# Step 5: Format and print summary table
# ---------------------------------------------------------------------------
def _print_summary(results: dict) -> str:
    """Print markdown table, return as string."""
    cfg_names = list(CONFIGS.keys())
    non_base = [c for c in cfg_names if c != "baseline"]

    header = (
        "| stat | baseline | "
        + " | ".join(f"{c} (delta)" for c in non_base)
        + " | best |"
    )
    sep = (
        "|------|--------:|"
        + "".join("-------------------:|" for _ in non_base)
        + ":-------------|"
    )

    lines = [
        "",
        "=== CV Feature Group MAE Comparison (4-fold WF, XGB+LGB blend) ===",
        "",
        header,
        sep,
    ]

    per_stat_best: dict = {}
    for stat in STATS:
        stat_res = results[stat]
        base_maes = stat_res.get("baseline", [])
        if not base_maes:
            lines.append(f"| {stat} | no folds | - | - | - | - |")
            continue
        base_mean = float(np.mean(base_maes))

        col_vals = [f"{base_mean:.4f}"]
        cfg_means: Dict[str, float] = {}
        for cfg in non_base:
            cfg_maes = stat_res.get(cfg, [])
            if cfg_maes:
                cm = float(np.mean(cfg_maes))
                delta = cm - base_mean
                cfg_means[cfg] = cm
                if delta < 0:
                    col_vals.append(f"**{cm:.4f} ({delta:+.4f})**")
                else:
                    col_vals.append(f"{cm:.4f} ({delta:+.4f})")
            else:
                cfg_means[cfg] = float("inf")
                col_vals.append("n/a")

        # Best config
        best_cfg = min(cfg_means, key=lambda c: cfg_means[c])
        if cfg_means[best_cfg] < base_mean:
            per_stat_best[stat] = best_cfg
        else:
            best_cfg = "baseline"
            per_stat_best[stat] = "baseline"

        row = f"| {stat} | " + " | ".join(col_vals) + f" | {best_cfg} |"
        lines.append(row)

    lines.append("")

    # Per-fold win counts
    win_summary_parts = []
    ship_candidates = []
    for stat in STATS:
        base_folds = results[stat].get("baseline", [])
        n_folds = len(base_folds)
        if n_folds == 0:
            win_summary_parts.append(f"{stat}=no_data")
            continue

        best_cfg = per_stat_best[stat]
        if best_cfg == "baseline":
            wins = 0
        else:
            cfg_folds = results[stat].get(best_cfg, [])
            wins = sum(
                1 for bm, cm in zip(base_folds, cfg_folds) if cm < bm
            )
            if wins == n_folds:
                ship_candidates.append(f"{stat}={best_cfg}")

        win_summary_parts.append(f"{stat}={best_cfg} {wins}/{n_folds}")

    lines.append("Per-stat best config (folds-CV-better / N): " + " | ".join(win_summary_parts))
    lines.append("")

    if ship_candidates:
        lines.append("SHIP CANDIDATES (beat baseline ALL folds): " + ", ".join(ship_candidates))
    else:
        lines.append("No config beat baseline on all folds for any stat.")
    lines.append("")

    output = "\n".join(lines)
    print(output)
    return output


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    # ---- 1. Load dataset ----
    print("=" * 60)
    print("Step 1: Loading base dataset (may take ~30s) ...")
    t0 = time.time()
    rows, base_cols = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  Loaded {n} rows, {len(base_cols)} base features ({time.time()-t0:.1f}s)")

    # ---- 2. Load game_date map ----
    print("\nStep 2: Loading game_date map from season_games JSON ...")
    game_date_map = _load_game_date_map()
    print(f"  {len(game_date_map)} game_ids mapped to dates")

    # ---- 3. Bulk-load CV data ----
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # ---- 4. Pre-compute CV augmentation matrix ----
    print("\nStep 4: Pre-computing CV augmentation (last-5 rolling per row) ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0
    rows_with_cv = int((cv_n_games > 0).sum())
    pct = 100.0 * rows_with_cv / n
    print(f"  Done in {elapsed:.1f}s")
    print(f"\n=== CV Coverage Debug ===")
    print(f"  Total rows:          {n}")
    print(f"  Rows with cv_n > 0:  {rows_with_cv}")
    print(f"  Percent covered:     {pct:.2f}%")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run walk-forward ----
    print(f"\nStep 6: Running {N_SPLITS}-fold walk-forward for {len(STATS)} stats × {len(CONFIGS)} configs ...")
    results = _run_walk_forward(rows, base_cols, X_base, cv_matrix, cv_n_games)

    # ---- 7. Print + save summary ----
    print("\nStep 7: Summary")
    _print_summary(results)

    # Build one-line takeaway
    per_stat_best_simple: Dict[str, str] = {}
    for stat in STATS:
        stat_res = results[stat]
        base_maes = stat_res.get("baseline", [])
        if not base_maes:
            per_stat_best_simple[stat] = "no_data"
            continue
        base_mean = float(np.mean(base_maes))
        best_cfg = "baseline"
        best_mean = base_mean
        for cfg in CONFIGS:
            if cfg == "baseline":
                continue
            cfg_maes = stat_res.get(cfg, [])
            if cfg_maes:
                cm = float(np.mean(cfg_maes))
                if cm < best_mean:
                    best_mean = cm
                    best_cfg = cfg
        per_stat_best_simple[stat] = best_cfg

    takeaway = "Best per-stat CV config: " + ", ".join(
        f"{stat}={per_stat_best_simple[stat]}" for stat in STATS
    )
    print(takeaway)

    # Save JSON results
    out_path = os.path.join(MODELS_DIR, "test_cv_isolated_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "cv_coverage": {
                    "total_rows": n,
                    "rows_with_cv": rows_with_cv,
                    "pct_covered": round(pct, 4),
                },
                "results": results,
                "per_stat_best": per_stat_best_simple,
                "takeaway": takeaway,
                "wall_time_s": round(time.time() - t_total, 1),
            },
            f,
            indent=2,
        )
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
