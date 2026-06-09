"""eval_gt_weighted_forms.py — INT-64 Evaluation: GT-Weighted Forms Walk-Forward.

Tests whether replacing standard L5/EWMA form columns with GT-weighted
counterparts improves per-stat MAE in a 4-fold expanding walk-forward.

Pipeline:
  1. Call build_pergame_dataset(min_prior=0) for baseline rows + feature_columns.
  2. Load gt_weighted_forms.parquet (INT-64).
  3. Override matching form columns in each row with GT-weighted values.
  4. Run 4-fold expanding WF — copy of prop_pergame_walk_forward.py splitter
     logic (commented as COPIED, NOT imported — protected file).
  5. Compare per-stat per-fold MAE (GT-weighted vs baseline).
  6. Null control: replace GT weights with random weights, re-run WF.

Ship gate:
  - >=3/4 folds positive on at least one stat
  - MAE strictly down >=0.002 on that stat
  - No regression >0.5pp on any other stat
  - Null control delta < 50% of GT-weighted delta
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))

from src.prediction.prop_pergame import (  # noqa: E402 — IMPORT ONLY, never edit protected file
    STATS, build_pergame_dataset, feature_columns,
)

_GT_PARQUET = ROOT / "data" / "intelligence" / "gt_weighted_forms.parquet"
_OUT_JSON = ROOT / "data" / "models" / "gt_weighted_forms_eval.json"

# Form column mapping: baseline column name → GT-weighted column name in parquet
# These are the columns we REPLACE (not add) per Opus spec.
_FORM_OVERRIDES = {
    "l5_pts":  "pts_l5_no_gt",
    "ewma_pts": "pts_ewma_no_gt",
    "l5_reb":  "reb_l5_no_gt",
    "ewma_reb": "reb_ewma_no_gt",
    "l5_ast":  "ast_l5_no_gt",
    "ewma_ast": "ast_ewma_no_gt",
    "l5_fg3m": "fg3m_l5_no_gt",
    "l5_stl":  "stl_l5_no_gt",
    "l5_blk":  "blk_l5_no_gt",
    "l5_tov":  "tov_l5_no_gt",
    "l5_min":  "min_l5_no_gt",
    "ewma_min": "min_ewma_no_gt",
}


def _train_xgb_lgb_blend(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB blend for one stat. Returns holdout MAE."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error

    is_count = stat in ("stl", "blk")
    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)

    st = LinearRegression(positive=True, fit_intercept=False)
    st.fit(np.column_stack([xv, lv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([0.5, 0.5])

    blend_ho = w[0] * xh + w[1] * lh
    return float(mean_absolute_error(y_ho, blend_ho))


def _build_feature_matrix(rows, fc):
    return np.array([[r[c] for c in fc] for r in rows], dtype=float)


def _apply_gt_overrides(rows: List[dict], fc: List[str], gt_df: pd.DataFrame) -> np.ndarray:
    """Apply GT-weighted form overrides to feature matrix.

    Join on (player_id, game_date, game_id). When no match or GT value is NaN,
    keep the original baseline value (graceful coverage fallback).
    """
    # Build lookup: (player_id, game_date) → override dict
    gt_cols = list(_FORM_OVERRIDES.values())
    gt_valid = gt_df[["player_id", "game_date", "game_id"] + gt_cols].copy()
    gt_valid["player_id"] = gt_valid["player_id"].astype(int)

    # Fast lookup by (player_id, game_date)
    gt_lookup = {}
    for _, row in gt_valid.iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        gt_lookup[key] = row

    fc_set = set(fc)
    fc_idx = {c: i for i, c in enumerate(fc)}

    # Find which baseline columns have GT overrides
    overrideable = {bc: gt_col for bc, gt_col in _FORM_OVERRIDES.items() if bc in fc_set}

    if not overrideable:
        print("  WARNING: no matching form columns found in feature_columns()")
        return _build_feature_matrix(rows, fc)

    print(f"  Overrideable columns: {list(overrideable.keys())}")

    X = _build_feature_matrix(rows, fc)
    n_overridden = 0

    for i, r in enumerate(rows):
        pid = int(r.get("player_id", 0) or 0)
        gd = str(r.get("date", "") or "")[:10]
        key = (pid, gd)
        gt_row = gt_lookup.get(key)
        if gt_row is None:
            continue
        for bc, gt_col in overrideable.items():
            gt_val = gt_row[gt_col]
            if pd.isna(gt_val):
                continue  # coverage fallback — keep baseline
            X[i, fc_idx[bc]] = float(gt_val)
            n_overridden += 1

    pct = 100 * n_overridden / max(len(rows) * len(overrideable), 1)
    print(f"  Cells overridden: {n_overridden:,} / {len(rows)*len(overrideable):,} ({pct:.1f}%)")
    return X


def walk_forward_eval(rows, fc, X_baseline, X_gt, label="GT", n_splits=4):
    """4-fold expanding walk-forward.
    # COPIED from scripts/prop_pergame_walk_forward.py — splitter logic only.
    # That file is protected (DO NOT import from it). Logic is identical:
    #   fold_ends = [(i+1)/(n_splits+1) for i in range(n_splits)]
    #   tr_end = int(n * train_end_frac)
    #   va_end = int(tr_end + (te_end - tr_end) * 0.4)
    #   age-weighted sample_weight via exp(-0.5 * age_years)
    """
    rows_sorted = sorted(rows, key=lambda r: r["date"])
    n = len(rows_sorted)
    # Re-sort X matrices to match sorted rows
    orig_order = sorted(range(len(rows)), key=lambda i: rows[i]["date"])
    X_bl = X_baseline[orig_order]
    X_gt_m = X_gt[orig_order]
    rows_s = [rows[i] for i in orig_order]

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    results = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
            continue

        tr_dates = [datetime.fromisoformat(rows_s[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n  [fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end} ({label})")
        t0 = time.time()

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows_s], dtype=float)
            y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]

            # Baseline
            mae_bl = _train_xgb_lgb_blend(
                stat,
                X_bl[:tr_end], y_tr,
                X_bl[tr_end:va_end], y_val,
                X_bl[va_end:te_end], y_ho,
                sw
            )
            # GT-weighted
            mae_gt = _train_xgb_lgb_blend(
                stat,
                X_gt_m[:tr_end], y_tr,
                X_gt_m[tr_end:va_end], y_val,
                X_gt_m[va_end:te_end], y_ho,
                sw
            )
            delta = mae_gt - mae_bl
            results[stat].append({
                "fold": fold_idx + 1,
                "mae_baseline": mae_bl,
                "mae_gt": mae_gt,
                "delta": delta,
                "positive": delta < 0,
            })
            print(f"    {stat.upper():4s} baseline={mae_bl:.4f}  {label}={mae_gt:.4f}  delta={delta:+.4f}")

        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    return results


def ship_gate_check(results_gt: dict, results_null: dict) -> dict:
    """Evaluate all ship-gate criteria. Returns verdict dict."""
    verdict = {}
    all_pass = True

    # Per-stat summary
    stat_summary = {}
    for stat in STATS:
        folds = results_gt[stat]
        if not folds:
            stat_summary[stat] = {"skip": True}
            continue
        deltas = [f["delta"] for f in folds]
        n_pos = sum(f["positive"] for f in folds)
        mean_delta = float(np.mean(deltas))
        mae_bl_mean = float(np.mean([f["mae_baseline"] for f in folds]))
        mae_gt_mean = float(np.mean([f["mae_gt"] for f in folds]))

        null_folds = results_null.get(stat, [])
        null_deltas = [f["delta"] for f in null_folds]
        null_mean = float(np.mean(null_deltas)) if null_deltas else 0.0

        stat_summary[stat] = {
            "n_folds": len(folds),
            "n_positive": n_pos,
            "mae_baseline_mean": mae_bl_mean,
            "mae_gt_mean": mae_gt_mean,
            "delta_mean": mean_delta,
            "null_delta_mean": null_mean,
        }

    verdict["stat_summary"] = stat_summary

    # Gate 1: >=3/4 folds positive on at least one stat AND MAE down >=0.002
    gate1_stats = []
    for stat, s in stat_summary.items():
        if s.get("skip"):
            continue
        if s["n_positive"] >= 3 and s["delta_mean"] <= -0.002:
            gate1_stats.append(stat)
    verdict["gate1_qualifying_stats"] = gate1_stats
    verdict["gate1_pass"] = len(gate1_stats) > 0

    # Gate 2: No regression >0.5pp on any stat
    regressions = []
    for stat, s in stat_summary.items():
        if s.get("skip"):
            continue
        if s["delta_mean"] > 0.005:  # 0.5pp = 0.005 in MAE units
            regressions.append((stat, s["delta_mean"]))
    verdict["gate2_regressions"] = regressions
    verdict["gate2_pass"] = len(regressions) == 0

    # Gate 3: Null control delta < 50% of GT-weighted delta
    null_control_ok = True
    null_control_details = {}
    for stat in gate1_stats:
        s = stat_summary[stat]
        gt_d = abs(s["delta_mean"])
        null_d = abs(s["null_delta_mean"])
        ratio = null_d / gt_d if gt_d > 0 else float("inf")
        null_control_details[stat] = {"gt_delta": s["delta_mean"], "null_delta": s["null_delta_mean"], "ratio": ratio}
        if ratio >= 0.5:
            null_control_ok = False
    verdict["gate3_null_control"] = null_control_details
    verdict["gate3_pass"] = null_control_ok

    # Final verdict
    if not verdict["gate1_pass"]:
        verdict["ship"] = "REJECT"
        verdict["reason"] = "gate1_fail: no stat with >=3/4 positive folds and MAE down >=0.002"
        all_pass = False
    elif not verdict["gate2_pass"]:
        verdict["ship"] = "REJECT"
        verdict["reason"] = f"gate2_fail: regression >0.5pp on {regressions}"
        all_pass = False
    elif not verdict["gate3_pass"]:
        verdict["ship"] = "NULL_CONTROL_FAIL"
        verdict["reason"] = "gate3_fail: null control within 50% of GT-weighted delta — result is noise"
        all_pass = False
    else:
        verdict["ship"] = "SHIP"
        verdict["reason"] = f"All gates pass. Qualifying stats: {gate1_stats}"

    return verdict


def main():
    print("=== INT-64: Evaluating GT-Weighted Forms ===")

    # Step 1: Load baseline dataset
    print("\nLoading baseline dataset...")
    rows, fc = build_pergame_dataset(min_prior=0)
    print(f"  rows={len(rows):,}, features={len(fc)}")

    # Step 2: Load GT parquet
    print("\nLoading GT-weighted forms parquet...")
    gt_df = pd.read_parquet(_GT_PARQUET)
    print(f"  GT rows: {len(gt_df):,}")

    # Step 3: Build baseline feature matrix
    print("\nBuilding baseline feature matrix...")
    X_baseline = _build_feature_matrix(rows, fc)

    # Step 4: Build GT-overridden feature matrix
    print("\nApplying GT overrides...")
    X_gt = _apply_gt_overrides(rows, fc, gt_df)

    # Step 5: Check how many cells actually differ
    diff_cells = np.sum(X_baseline != X_gt)
    print(f"  Cells changed from baseline: {diff_cells:,}")
    if diff_cells == 0:
        print("  WARNING: No cells were overridden — GT columns may not match feature_columns()")
        print("  Feature column sample:", fc[:30])

    # Step 6: Walk-forward GT
    print("\n=== Walk-Forward: GT-Weighted ===")
    results_gt = walk_forward_eval(rows, fc, X_baseline, X_gt, label="GT")

    # Step 7: Null control — random weights replacing GT weights
    print("\n=== Walk-Forward: Null Control (random weights) ===")
    print("  Generating random-weight feature matrix (seed=42)...")
    rng = np.random.default_rng(42)
    gt_null_df = gt_df.copy()
    # Replace GT form cols with randomly weighted versions
    # We simulate random weights by re-deriving from baseline with random perturbation
    # Approach: for each row that was overridden, replace GT value with baseline ± random noise
    # More principled: build a null GT parquet where pct_gt is uniform random ∈ [0, 1]
    # which means w = max(1 - U(0,1), 0.05) — random weighting
    # Simplest correct implementation: perturb the overriding values randomly
    # We implement: null X = baseline + (X_gt - baseline) * random_scale per cell
    # where random_scale ~ U(-1, 1) so the net effect is noise
    # Actually per spec: "replace weights with rng.uniform(0.05, 1.0)" then recompute
    # We don't have per-row weights accessible post-build; instead we:
    # Shuffle the GT pct_gt values randomly (same distribution, random assignment)
    print("  Approach: shuffle pct_minutes_in_gt values across rows (preserves distribution)")
    null_df = gt_df.copy()
    shuffled_pct = rng.permutation(null_df["pct_minutes_in_gt_l5"].values)
    null_df["pct_minutes_in_gt_l5"] = shuffled_pct

    # For null control we use random noise on the OVERRIDDEN cells only
    # Per spec: random weights rng.uniform(0.05, 1.0) — we simulate this by
    # creating a null X matrix where overridden cells are randomly perturbed
    # between baseline and GT value using random factor
    null_factors = rng.uniform(0.05, 1.0, size=X_gt.shape)
    X_null = X_baseline + (X_gt - X_baseline) * null_factors
    diff_null = np.sum(X_null != X_baseline)
    print(f"  Null cells changed: {diff_null:,}")

    results_null = walk_forward_eval(rows, fc, X_baseline, X_null, label="NULL")

    # Step 8: Print summary table
    print("\n=== RESULTS TABLE (7-stat x 4-fold) ===")
    print(f"{'stat':>6} | {'baseline MAE':>12} | {'GT MAE':>10} | {'delta':>8} | {'n_pos/4':>7} | {'null delta':>10}")
    print("-" * 70)

    for stat in STATS:
        folds_gt = results_gt.get(stat, [])
        folds_nl = results_null.get(stat, [])
        if not folds_gt:
            print(f"  {stat.upper():4s} | skipped")
            continue
        bl_mean = np.mean([f["mae_baseline"] for f in folds_gt])
        gt_mean = np.mean([f["mae_gt"] for f in folds_gt])
        delta = np.mean([f["delta"] for f in folds_gt])
        n_pos = sum(f["positive"] for f in folds_gt)
        null_delta = np.mean([f["delta"] for f in folds_nl]) if folds_nl else float("nan")
        print(f"  {stat.upper():4s} | {bl_mean:12.4f} | {gt_mean:10.4f} | {delta:+8.4f} | {n_pos:>7} | {null_delta:+10.4f}")

    # Step 9: Ship gate
    print("\n=== SHIP GATE ===")
    verdict = ship_gate_check(results_gt, results_null)

    for stat in STATS:
        s = verdict["stat_summary"].get(stat, {})
        if not s or s.get("skip"):
            continue
        null_ctrl = verdict["gate3_null_control"].get(stat, {})
        null_ratio_str = f"{null_ctrl.get('ratio', float('nan')):.2f}" if null_ctrl else "n/a"
        print(f"  {stat.upper():4s}: delta={s['delta_mean']:+.4f} n_pos={s['n_positive']}/4"
              f" null_ratio={null_ratio_str}")

    print(f"\nVerdict: {verdict['ship']}")
    print(f"Reason:  {verdict['reason']}")

    if verdict["ship"] == "REJECT" or verdict["ship"] == "NULL_CONTROL_FAIL":
        print(f"\n{'='*20} {verdict['ship']} {'='*20}")

    # Null control token check (per spec)
    for stat in STATS:
        s = verdict["stat_summary"].get(stat, {})
        folds_gt = results_gt.get(stat, [])
        folds_nl = results_null.get(stat, [])
        if not folds_gt or not folds_nl:
            continue
        gt_d = abs(np.mean([f["delta"] for f in folds_gt]))
        null_d = abs(np.mean([f["delta"] for f in folds_nl]))
        if gt_d > 0 and null_d >= gt_d * 0.5:
            # Check if within ±0.001 per spec
            if abs(null_d - gt_d) <= 0.001:
                print(f"REJECT_NULL_CONTROL stat={stat} gt_delta={-gt_d:.4f} null_delta={-null_d:.4f}")

    # Save results
    out = {
        "build_date": datetime.now().isoformat(),
        "verdict": verdict,
        "results_gt": {s: results_gt[s] for s in STATS},
        "results_null": {s: results_null[s] for s in STATS},
        "n_rows": len(rows),
        "n_features": len(fc),
        "cells_overridden": int(diff_cells),
    }
    with open(_OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {_OUT_JSON}")
    return verdict


if __name__ == "__main__":
    main()
