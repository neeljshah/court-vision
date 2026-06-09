"""
test_cv_null_control.py — X3a Null Control for CV Feature Hypothesis.

Tests whether the REB SHIP at -0.0034 MAE is a regularization artifact
or genuine CV signal. Runs 5 null configurations × 5 random seeds each.

Run:
    python scripts/test_cv_null_control.py
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

TIER1_5 = [
    "potential_assists",
    "touches_per_game",
    "paint_dwell_pct",
    "defender_approach_speed",
    "preshot_velocity_peak",
]

# Reference benchmarks from prior agent runs
REFERENCE_BASELINE = 1.8768
REFERENCE_TIER1 = 1.8734   # delta -0.0034, 4/4 folds
REFERENCE_ALL_CV = 1.8741  # delta -0.0027, 4/4 folds

# Seeds to run per null config
SEEDS = [42, 1, 7, 100, 2024]

# REB only (the stat we're testing)
TARGET_STAT = "reb"

N_SPLITS = 4


# ---------------------------------------------------------------------------
# Dataset loading helpers (same as test_cv_isolated.py)
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
# Core training function (identical to test_cv_isolated.py)
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
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    preds = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, preds))


# ---------------------------------------------------------------------------
# Null column generators
# ---------------------------------------------------------------------------
def _generate_null_columns(
    null_config: str,
    cv_n_games: np.ndarray,
    cv_matrix: np.ndarray,
    seed: int,
) -> np.ndarray:
    """
    Generate 5 null columns + 1 coverage column (cv_n_games_cv).

    Returns array of shape (n, 6) = 5 null cols + 1 count col.
    """
    rng = np.random.RandomState(seed)
    n = len(cv_n_games)
    has_cv_mask = cv_n_games > 0  # Boolean mask: rows with CV data

    if null_config == "null_a":
        # Random Gaussian, same sparsity pattern as CV
        # N(0,1) for rows with cv_n_games_cv > 0, else 0
        cols = np.zeros((n, 5), dtype=float)
        has_cv_idx = np.where(has_cv_mask)[0]
        if len(has_cv_idx) > 0:
            cols[has_cv_idx, :] = rng.randn(len(has_cv_idx), 5)

    elif null_config == "null_b":
        # Random Gaussian, FULL coverage (no sparsity)
        cols = rng.randn(n, 5)

    elif null_config == "null_c":
        # All zeros — absolute null
        cols = np.zeros((n, 5), dtype=float)

    elif null_config == "null_d":
        # Repeat cv_n_games_cv 5 times
        ng_col = cv_n_games.reshape(-1, 1).astype(float)
        cols = np.repeat(ng_col, 5, axis=1)

    elif null_config == "null_e":
        # Random permutation of actual CV Tier-1 features
        # Take the tier1 5 features, shuffle their row assignments
        # among rows that have CV data (preserves marginal distributions)
        feat_idx_map = {f: i for i, f in enumerate(ALL_CV_COLS)}
        tier1_indices = [feat_idx_map[f] for f in TIER1_5 if f in feat_idx_map]
        cols = np.zeros((n, 5), dtype=float)

        has_cv_idx = np.where(has_cv_mask)[0]
        if len(has_cv_idx) > 0 and len(tier1_indices) >= 5:
            # Extract tier1 values for rows with CV
            tier1_vals = cv_matrix[np.ix_(has_cv_idx, tier1_indices[:5])]  # (k, 5)
            # Shuffle row assignments (destroy row-level structure)
            shuffled_idx = rng.permutation(len(has_cv_idx))
            cols[has_cv_idx, :] = tier1_vals[shuffled_idx, :]
        elif len(has_cv_idx) > 0 and len(tier1_indices) > 0:
            # Fewer than 5 tier1 features available, repeat what we have
            tier1_vals = cv_matrix[np.ix_(has_cv_idx, tier1_indices)]
            shuffled_idx = rng.permutation(len(has_cv_idx))
            shuffled_vals = tier1_vals[shuffled_idx, :]
            for col_i in range(5):
                src_col = col_i % len(tier1_indices)
                cols[has_cv_idx, col_i] = shuffled_vals[:, src_col]

    else:
        raise ValueError(f"Unknown null_config: {null_config}")

    # Append cv_n_games_cv (same as real CV configs)
    ng_col = cv_n_games.reshape(-1, 1).astype(float)
    return np.hstack([cols, ng_col])  # shape (n, 6)


# ---------------------------------------------------------------------------
# Walk-forward for a single stat + a single augmentation matrix
# ---------------------------------------------------------------------------
def _run_wf_single(
    rows: List[dict],
    X_base: np.ndarray,
    X_extra: np.ndarray,  # (n, k) or None
    stat: str,
) -> List[float]:
    """Run 4-fold WF for one stat with optional extra columns. Return per-fold MAEs."""
    n = len(rows)
    fold_ends = [(i + 1) / (N_SPLITS + 1) for i in range(N_SPLITS)]

    if X_extra is not None:
        X_aug = np.hstack([X_base, X_extra])
    else:
        X_aug = X_base

    fold_maes = []
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

        mae = _train_fold(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw)
        fold_maes.append(mae)

    return fold_maes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    t_total = time.time()

    print("=" * 70)
    print("X3a Null Control — Testing whether REB SHIP is a regularization artifact")
    print("=" * 70)

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
    print("\nStep 3: Loading CV feature data from DB ...")
    by_player = _load_cv_data(game_date_map)
    print(f"  {len(by_player)} distinct players have CV history")

    # ---- 4. Pre-compute CV augmentation matrix ----
    print("\nStep 4: Pre-computing CV augmentation matrix ...")
    t0 = time.time()
    cv_matrix, cv_n_games = _build_cv_matrix(rows, by_player)
    elapsed = time.time() - t0
    rows_with_cv = int((cv_n_games > 0).sum())
    pct_cv = 100.0 * rows_with_cv / n
    print(f"  Done in {elapsed:.1f}s")
    print(f"  Rows with cv_n > 0: {rows_with_cv} ({pct_cv:.2f}%)")

    # ---- 5. Build base feature matrix ----
    print("\nStep 5: Building base feature matrix ...")
    t0 = time.time()
    X_base = np.array([[r[c] for c in base_cols] for r in rows], dtype=float)
    print(f"  X_base shape: {X_base.shape}  ({time.time()-t0:.1f}s)")

    # ---- 6. Run baseline (no extra columns) ----
    print("\n" + "=" * 70)
    print("Step 6: Baseline run (no extra columns) ...")
    baseline_folds = _run_wf_single(rows, X_base, None, TARGET_STAT)
    baseline_mean = float(np.mean(baseline_folds))
    print(f"  Baseline {TARGET_STAT.upper()} MAE = {baseline_mean:.4f}  "
          f"(folds: {[f'{v:.4f}' for v in baseline_folds]})")
    print(f"  Reference baseline: {REFERENCE_BASELINE:.4f}")

    # ---- 7. Run 5 null configs × 5 seeds ----
    null_configs = ["null_a", "null_b", "null_c", "null_d", "null_e"]
    null_labels = {
        "null_a": "Random Gaussian, CV sparsity",
        "null_b": "Random Gaussian, full coverage",
        "null_c": "All zeros (5 columns)",
        "null_d": "cv_n_games_cv duplicated 5x",
        "null_e": "Shuffled CV Tier-1 values",
    }

    all_results: Dict[str, Dict] = {}

    for null_cfg in null_configs:
        print(f"\n{'='*70}")
        print(f"Null config: {null_cfg} — {null_labels[null_cfg]}")
        print("=" * 70)

        seed_maes = []
        seed_deltas = []
        seed_fold_details = []

        for seed in SEEDS:
            print(f"  Seed {seed}:", end=" ", flush=True)
            X_extra = _generate_null_columns(null_cfg, cv_n_games, cv_matrix, seed)
            fold_maes = _run_wf_single(rows, X_base, X_extra, TARGET_STAT)

            if not fold_maes:
                print("no valid folds")
                continue

            mean_mae = float(np.mean(fold_maes))
            delta = mean_mae - baseline_mean
            folds_better = sum(1 for fm, bm in zip(fold_maes, baseline_folds) if fm < bm)

            seed_maes.append(mean_mae)
            seed_deltas.append(delta)
            seed_fold_details.append({
                "seed": seed,
                "fold_maes": fold_maes,
                "mean_mae": round(mean_mae, 6),
                "delta": round(delta, 6),
                "folds_better": folds_better,
            })
            print(f"MAE={mean_mae:.4f}  delta={delta:+.4f}  folds_better={folds_better}/{len(fold_maes)}")

        if seed_maes:
            mean_delta = float(np.mean(seed_deltas))
            std_delta = float(np.std(seed_deltas))
            folds_better_mean = float(np.mean([d["folds_better"] for d in seed_fold_details]))
            print(f"\n  >> {null_cfg} summary: mean_delta={mean_delta:+.4f}  std={std_delta:.4f}  "
                  f"folds_better_mean={folds_better_mean:.1f}/{N_SPLITS}")
        else:
            mean_delta = float("nan")
            std_delta = float("nan")
            folds_better_mean = float("nan")

        all_results[null_cfg] = {
            "label": null_labels[null_cfg],
            "mean_delta": round(mean_delta, 6) if not np.isnan(mean_delta) else None,
            "std_delta": round(std_delta, 6) if not np.isnan(std_delta) else None,
            "folds_better_mean": round(folds_better_mean, 2) if not np.isnan(folds_better_mean) else None,
            "per_seed": seed_fold_details,
        }

    # ---- 8. Final report ----
    print("\n" + "=" * 70)
    print("X3a Null Control — Final Report")
    print("=" * 70)

    print(f"\nBaseline {TARGET_STAT.upper()} MAE = {baseline_mean:.4f}")
    print(f"Reference baseline:          {REFERENCE_BASELINE:.4f}")
    print(f"Reference tier1_only:        {REFERENCE_TIER1:.4f}  (delta {REFERENCE_TIER1 - REFERENCE_BASELINE:+.4f})")
    print(f"Reference all_cv_27:         {REFERENCE_ALL_CV:.4f}  (delta {REFERENCE_ALL_CV - REFERENCE_BASELINE:+.4f})")

    print("\n| null config | description | mean delta | std | folds_better_mean | vs real CV |")
    print("|-------------|-------------|-----------|-----|------------------|------------|")
    for null_cfg in null_configs:
        r = all_results[null_cfg]
        md = r["mean_delta"]
        sd = r["std_delta"]
        fb = r["folds_better_mean"]
        real_cv_delta = REFERENCE_TIER1 - REFERENCE_BASELINE  # -0.0034
        if md is not None:
            similarity = "MATCHES real CV" if abs(md - real_cv_delta) < 0.001 else (
                "close" if abs(md - real_cv_delta) < 0.002 else "different"
            )
            print(f"| {null_cfg} | {null_labels[null_cfg][:35]:35s} | {md:+.4f} | {sd:.4f} | "
                  f"{fb:.1f}/{N_SPLITS} | {similarity} |")
        else:
            print(f"| {null_cfg} | {null_labels[null_cfg][:35]:35s} | N/A | N/A | N/A | N/A |")

    # Interpret results
    print("\n--- VERDICT ---")
    null_a = all_results.get("null_a", {})
    null_c = all_results.get("null_c", {})
    null_e = all_results.get("null_e", {})

    real_cv_delta = REFERENCE_TIER1 - REFERENCE_BASELINE  # -0.0034

    na_md = null_a.get("mean_delta")
    nc_md = null_c.get("mean_delta")
    ne_md = null_e.get("mean_delta")

    if na_md is not None and abs(na_md - real_cv_delta) < 0.001:
        print("VERDICT: CV moat is ILLUSORY for prediction.")
        print(f"  Null A (random Gaussian w/ CV sparsity) delta={na_md:+.4f} ~ real CV delta={real_cv_delta:+.4f}")
        print("  Any 5 columns with this sparsity produce the same effect.")
        print("  The REB improvement is REGULARIZATION, not CV signal.")
    elif nc_md is not None and abs(nc_md - real_cv_delta) < 0.001:
        print("VERDICT: CV moat is a PURE BLEND ARTIFACT.")
        print(f"  Null C (all zeros) delta={nc_md:+.4f} ~ real CV delta={real_cv_delta:+.4f}")
        print("  Adding ANY 5 columns (even zeros) regularizes the blend the same way.")
    elif na_md is not None and na_md > -0.001:
        print("VERDICT: Real CV signal LIKELY EXISTS.")
        print(f"  Null A delta={na_md:+.4f} ~ 0  while real CV gives {real_cv_delta:+.4f}")
        print("  Random Gaussian with same sparsity does NOT replicate the improvement.")
        print("  Something in the CV feature VALUES is doing the work.")
    else:
        print(f"VERDICT: Ambiguous -- Null A delta={na_md}  vs real CV delta={real_cv_delta:+.4f}")

    if ne_md is not None and abs(ne_md - real_cv_delta) < 0.001:
        print(f"\nNOTE: Null E (shuffled CV) also ~ real CV (delta={ne_md:+.4f}).")
        print("  Column STATISTICS matter, not row-level relationships.")
    elif ne_md is not None and ne_md > -0.001:
        print(f"\nNOTE: Null E (shuffled CV) delta={ne_md:+.4f} ~ 0.")
        print("  Row-level structure (which values go with which row) is what matters.")

    # Save results
    out = {
        "hypothesis": "Is the REB SHIP at -0.0034 MAE a regularization artifact?",
        "reference_benchmarks": {
            "baseline": REFERENCE_BASELINE,
            "tier1_only_5_real_cv_features": REFERENCE_TIER1,
            "all_cv_27_real_cv_features": REFERENCE_ALL_CV,
            "real_cv_tier1_delta": round(real_cv_delta, 6),
        },
        "our_baseline": {
            "mean_mae": round(baseline_mean, 6),
            "fold_maes": baseline_folds,
        },
        "null_control_results": all_results,
        "stat_tested": TARGET_STAT,
        "seeds": SEEDS,
        "n_folds": N_SPLITS,
        "wall_time_s": round(time.time() - t_total, 1),
    }
    out_path = os.path.join(MODELS_DIR, "test_cv_null_control_results.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to: {out_path}")
    print(f"Total wall time: {time.time()-t_total:.1f}s")


if __name__ == "__main__":
    main()
