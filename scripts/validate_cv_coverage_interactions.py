"""validate_cv_coverage_interactions.py — INT-60 walk-forward validation + 3 null controls.

Walk-forward: 4 temporal folds. Measures PTS MAE delta when adding interaction features.
Null controls:
  NULL-A: random coverage gate (Uniform(0,20))
  NULL-B: zero CV features before interaction
  NULL-C: permuted player_id on parquet

Ship gate:
  1. >= 3/4 WF folds positive on PTS (delta < 0)
  2. PTS MAE delta <= -0.002 absolute
  3. All 3 null controls within +-0.001 of zero delta
  4. Seed stability: re-run seeds 1,2,3 — gain persists on >= 2/3

Run:
    python scripts/validate_cv_coverage_interactions.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.build_cv_coverage_interactions import (
    load_cv_wide,
    build_interactions_fast,
    SELECTED_FEATURES,
)
from src.prediction.prop_pergame import build_pergame_dataset, STATS

INTERACTION_COLS = [f"{f}_x_coverage" for f in SELECTED_FEATURES]
STAT = "pts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join_interactions(rows: list[dict], interactions: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Join interaction columns onto prop_pergame rows dict list.
    Returns (augmented_rows, new_feature_names).
    """
    int_lookup: dict[tuple[int, str], dict] = {}
    for _, r in interactions.iterrows():
        key = (int(r["player_id"]), str(r["game_date"].date()))
        int_lookup[key] = {c: (float(r[c]) if pd.notna(r[c]) else 0.0) for c in INTERACTION_COLS}

    new_cols = list(INTERACTION_COLS)
    augmented = []
    for row in rows:
        pid = int(row["player_id"])
        date_str = str(pd.to_datetime(row["date"]).date())
        extras = int_lookup.get((pid, date_str), {c: 0.0 for c in INTERACTION_COLS})
        augmented.append({**row, **extras})

    return augmented, new_cols


def _wf_pts_mae(rows: list[dict], feature_cols: list[str], n_splits: int = 4) -> tuple[float, list[float]]:
    """Walk-forward MAE for PTS using XGBoost. Returns (mean_mae, per_fold_maes)."""
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    rows_sorted = sorted(rows, key=lambda r: r["date"])
    n = len(rows_sorted)
    X_all = np.array([[r.get(c, 0.0) for c in feature_cols] for r in rows_sorted], dtype=np.float32)
    y_all = np.array([r["target_pts"] for r in rows_sorted], dtype=np.float32)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    fold_maes = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 1000:
            continue

        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
        y_tr, y_val, y_ho = y_all[:tr_end], y_all[tr_end:va_end], y_all[va_end:te_end]

        # Recency weighting
        dates_tr = [pd.to_datetime(rows_sorted[i]["date"]) for i in range(tr_end)]
        max_d = max(dates_tr)
        age = np.array([(max_d - d).days / 365.0 for d in dates_tr], dtype=float)
        sw = np.exp(-0.5 * age)

        m = xgb.XGBRegressor(
            n_estimators=300, max_depth=4,
            learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
            min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5,
            random_state=42,
            early_stopping_rounds=30, eval_metric="mae",
            verbosity=0,
        )
        m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
        preds = m.predict(X_ho)
        mae = float(mean_absolute_error(y_ho, preds))
        fold_maes.append(mae)
        print(f"    Fold {fold_idx+1}: tr={tr_end}, ho={te_end-va_end}, MAE={mae:.4f}", flush=True)

    mean_mae = float(np.mean(fold_maes)) if fold_maes else np.nan
    return mean_mae, fold_maes


def run_wf_comparison(
    rows: list[dict],
    base_fc: list[str],
    interactions: pd.DataFrame,
    label: str = "real",
) -> dict:
    """Run baseline WF + augmented WF. Return delta summary."""
    print(f"\n--- {label} ---")

    print("  Baseline WF (PTS)...")
    t0 = time.time()
    base_mae, base_folds = _wf_pts_mae(rows, base_fc)
    print(f"  Baseline mean MAE: {base_mae:.4f} ({time.time()-t0:.0f}s)")

    print("  Augmented WF (PTS + interactions)...")
    aug_rows, new_cols = _join_interactions(rows, interactions)
    aug_fc = base_fc + new_cols
    t0 = time.time()
    aug_mae, aug_folds = _wf_pts_mae(aug_rows, aug_fc)
    print(f"  Augmented mean MAE: {aug_mae:.4f} ({time.time()-t0:.0f}s)")

    delta = aug_mae - base_mae
    positive_folds = sum(1 for a, b in zip(aug_folds, base_folds) if a < b)
    fold_deltas = [a - b for a, b in zip(aug_folds, base_folds)]

    print(f"  Delta: {delta:+.4f} | Positive folds: {positive_folds}/{len(base_folds)}")
    print(f"  Per-fold deltas: {[f'{d:+.4f}' for d in fold_deltas]}")

    return {
        "label": label,
        "base_mae": base_mae,
        "aug_mae": aug_mae,
        "delta_mae": delta,
        "positive_folds": positive_folds,
        "total_folds": len(base_folds),
        "base_folds": base_folds,
        "aug_folds": aug_folds,
        "fold_deltas": fold_deltas,
    }


def main() -> None:
    print("=" * 60)
    print("INT-60: Validate CV × Coverage Interactions")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. Load dataset
    # -----------------------------------------------------------------------
    print("\n[1] Loading prop_pergame dataset...")
    rows, base_fc = build_pergame_dataset(min_prior=0)
    print(f"  Rows: {len(rows)}, features: {len(base_fc)}")

    # -----------------------------------------------------------------------
    # 2. Load real interactions parquet
    # -----------------------------------------------------------------------
    int_path = ROOT / "data" / "intelligence" / "cv_coverage_interactions.parquet"
    real_int = pd.read_parquet(int_path)
    real_int["game_date"] = pd.to_datetime(real_int["game_date"])
    print(f"\n[2] Real interactions: {len(real_int)} rows, "
          f"{real_int['player_id'].nunique()} players")

    # Non-null coverage
    for col in INTERACTION_COLS:
        nn = real_int[col].notna().sum()
        print(f"  {col}: {nn} non-null ({100*nn/len(real_int):.1f}%)")

    # -----------------------------------------------------------------------
    # 3. REAL walk-forward (seed=42)
    # -----------------------------------------------------------------------
    results: dict[str, dict] = {}
    real_result = run_wf_comparison(rows, base_fc, real_int, label="REAL_seed42")
    results["REAL_seed42"] = real_result

    # -----------------------------------------------------------------------
    # 4. NULL-A: Random coverage
    # -----------------------------------------------------------------------
    print("\n[4] NULL-A: random coverage gate...")
    cv_df = load_cv_wide()
    null_a_int = build_interactions_fast(
        cv_df, features=SELECTED_FEATURES, random_coverage=True, seed=42
    )
    null_a_int["game_date"] = pd.to_datetime(null_a_int["game_date"])
    null_a = run_wf_comparison(rows, base_fc, null_a_int, label="NULL_A_random_coverage")
    results["NULL_A"] = null_a

    # -----------------------------------------------------------------------
    # 5. NULL-B: Zero CV features
    # -----------------------------------------------------------------------
    print("\n[5] NULL-B: zero CV features before interaction...")
    null_b_int = build_interactions_fast(
        cv_df, features=SELECTED_FEATURES, zero_features=True, seed=42
    )
    null_b_int["game_date"] = pd.to_datetime(null_b_int["game_date"])
    null_b = run_wf_comparison(rows, base_fc, null_b_int, label="NULL_B_zero_features")
    results["NULL_B"] = null_b

    # -----------------------------------------------------------------------
    # 6. NULL-C: Permuted player_id
    # -----------------------------------------------------------------------
    print("\n[6] NULL-C: permuted player_id...")
    null_c_int = build_interactions_fast(
        cv_df, features=SELECTED_FEATURES, permute_player=True, seed=42
    )
    null_c_int["game_date"] = pd.to_datetime(null_c_int["game_date"])
    null_c = run_wf_comparison(rows, base_fc, null_c_int, label="NULL_C_permuted_player")
    results["NULL_C"] = null_c

    # -----------------------------------------------------------------------
    # 7. Seed stability (seeds 1, 2, 3 — vary XGB random_state)
    # -----------------------------------------------------------------------
    print("\n[7] Seed stability (seeds 1, 2, 3)...")
    seed_deltas = []
    for seed in [1, 2, 3]:
        print(f"  Seed {seed}:")
        # Re-run just the augmented WF with different XGB seed
        aug_rows, new_cols = _join_interactions(rows, real_int)
        aug_fc = base_fc + new_cols

        import xgboost as xgb
        from sklearn.metrics import mean_absolute_error

        rows_sorted = sorted(aug_rows, key=lambda r: r["date"])
        n = len(rows_sorted)
        X_all = np.array([[r.get(c, 0.0) for c in aug_fc] for r in rows_sorted], dtype=np.float32)
        y_all = np.array([r["target_pts"] for r in rows_sorted], dtype=np.float32)

        n_splits = 4
        fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
        seed_fold_maes = []

        for fold_idx, train_end_frac in enumerate(fold_ends):
            tr_end = int(n * train_end_frac)
            if fold_idx == n_splits - 1:
                te_end = n
            else:
                te_end = int(n * fold_ends[fold_idx + 1])
            va_end = int(tr_end + (te_end - tr_end) * 0.4)
            if tr_end < 5000 or (te_end - va_end) < 1000:
                continue

            X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
            y_tr, y_val, y_ho = y_all[:tr_end], y_all[tr_end:va_end], y_all[va_end:te_end]

            dates_tr = [pd.to_datetime(rows_sorted[i]["date"]) for i in range(tr_end)]
            max_d = max(dates_tr)
            age = np.array([(max_d - d).days / 365.0 for d in dates_tr], dtype=float)
            sw = np.exp(-0.5 * age)

            m = xgb.XGBRegressor(
                n_estimators=300, max_depth=4,
                learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5,
                random_state=seed,
                early_stopping_rounds=30, eval_metric="mae",
                verbosity=0,
            )
            m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
            preds = m.predict(X_ho)
            seed_fold_maes.append(float(mean_absolute_error(y_ho, preds)))

        seed_aug_mae = float(np.mean(seed_fold_maes))
        seed_delta = seed_aug_mae - real_result["base_mae"]
        seed_deltas.append(seed_delta)
        print(f"    seed={seed} aug_mae={seed_aug_mae:.4f} delta={seed_delta:+.4f}")

    results["seed_stability"] = {
        "seed_deltas": seed_deltas,
        "gains_persist": sum(1 for d in seed_deltas if d < real_result["delta_mae"] + 0.001),
    }

    # -----------------------------------------------------------------------
    # 8. Ship gate evaluation
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SHIP GATE EVALUATION")
    print("=" * 60)

    real_delta = real_result["delta_mae"]
    real_pos = real_result["positive_folds"]
    real_total = real_result["total_folds"]
    null_a_delta = null_a["delta_mae"]
    null_b_delta = null_b["delta_mae"]
    null_c_delta = null_c["delta_mae"]

    gate1 = real_pos >= 3 and real_total >= 3
    gate2 = real_delta <= -0.002
    gate3 = all(abs(d - 0.0) <= 0.001 for d in [null_a_delta, null_b_delta, null_c_delta])
    seed_pass = sum(1 for d in seed_deltas if d < 0.001) >= 2

    print(f"\nG1 (>=3/4 positive folds on PTS):   {real_pos}/{real_total}  -> {'PASS' if gate1 else 'FAIL'}")
    print(f"G2 (PTS MAE delta <= -0.002):        {real_delta:+.4f}     -> {'PASS' if gate2 else 'FAIL'}")
    print(f"G3a NULL-A |delta| <= 0.001:         {null_a_delta:+.4f}   -> {'PASS' if abs(null_a_delta) <= 0.001 else 'FAIL'}")
    print(f"G3b NULL-B |delta| <= 0.001:         {null_b_delta:+.4f}   -> {'PASS' if abs(null_b_delta) <= 0.001 else 'FAIL'}")
    print(f"G3c NULL-C |delta| <= 0.001:         {null_c_delta:+.4f}   -> {'PASS' if abs(null_c_delta) <= 0.001 else 'FAIL'}")
    print(f"G4 (seed stability >=2/3 persist):   {sum(1 for d in seed_deltas if d < 0.001)}/3 -> {'PASS' if seed_pass else 'FAIL'}")

    all_pass = gate1 and gate2 and gate3 and seed_pass
    print(f"\nVERDICT: {'SHIP' if all_pass else 'REJECT'}")

    if not all_pass:
        reasons = []
        if not gate1:
            reasons.append(f"G1 fail: only {real_pos}/{real_total} positive folds")
        if not gate2:
            reasons.append(f"G2 fail: delta={real_delta:+.4f} (need <= -0.002)")
        if abs(null_a_delta) > 0.001:
            reasons.append(f"NULL-A fired: delta={null_a_delta:+.4f} (gate is noise)")
        if abs(null_b_delta) > 0.001:
            reasons.append(f"NULL-B fired: delta={null_b_delta:+.4f} (pure regularization)")
        if abs(null_c_delta) > 0.001:
            reasons.append(f"NULL-C fired: delta={null_c_delta:+.4f} (not player-specific)")
        if not seed_pass:
            reasons.append(f"Seed instability: {seed_deltas}")
        print("Rejection reasons:")
        for r in reasons:
            print(f"  - {r}")

    # -----------------------------------------------------------------------
    # 9. Save results
    # -----------------------------------------------------------------------
    out_path = ROOT / "data" / "intelligence" / "int60_validation_results.json"
    with open(out_path, "w") as f:
        json.dump({
            "real": {k: (v if not isinstance(v, float) or not np.isnan(v) else None)
                     for k, v in real_result.items()},
            "null_a": null_a,
            "null_b": null_b,
            "null_c": null_c,
            "seed_stability": results["seed_stability"],
            "ship_gates": {
                "G1_pos_folds": gate1,
                "G2_mae_delta": gate2,
                "G3_null_controls": gate3,
                "G4_seed_stability": seed_pass,
                "VERDICT": "SHIP" if all_pass else "REJECT",
            },
        }, f, indent=2, default=str)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
