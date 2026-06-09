"""validate_cv_coverage_gate.py — INT-53 E1 CV Coverage Gate validation.

Tests whether the xfg_shrunk_by_coverage signal from build_cv_coverage_gates.py
improves PTS prediction when blended post-hoc, and whether the improvement
survives a random-gate null control (X3a lesson).

Protocol (Opus spec):
1. Run prop_pergame_walk_forward.py UNMODIFIED to get baseline per-fold MAE.
   If data/models/prop_pergame_walk_forward.json already exists and is fresh,
   re-use it. Otherwise re-run with --splits=2 (faster).
2. Re-run same fold splits internally (mirror walk_forward.py logic exactly)
   to capture per-row holdout predictions for PTS.
3. Post-hoc blend:
     blended_pts = 0.85 * original_pts + 0.15 * xfg_shrunk * pts_scale
   where pts_scale = mean(pts_actual) / mean(xfg_shrunk) in training fold.
4. Null control: same blend with coverage_gate replaced by Uniform(0,1) seed=42.
5. Ship criteria (ALL required):
   - >= 3/4 folds positive on PTS MAE delta
   - No regression > 0.5pp on any other stat
   - Mean delta MAE PTS <= -0.003 absolute
   - delta_real - delta_null < -0.0015 (gate signal > noise)

Usage:
    python scripts/validate_cv_coverage_gate.py
    python scripts/validate_cv_coverage_gate.py --splits 2  # faster
    python scripts/validate_cv_coverage_gate.py --rerun-wf   # force WF re-run
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

STATS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
GATE_MIX = 0.15      # xfg blend weight
BASE_MIX = 0.85      # original prediction weight
NULL_SEED = 42       # random gate seed

# Ship criteria thresholds
SHIP_FOLDS_POSITIVE = 3        # out of 4 (or 2 for 2-split)
SHIP_MEAN_DELTA_MAX = -0.003   # PTS MAE absolute threshold
SHIP_NULL_GAP = 0.0015         # delta_real - delta_null must be < -this
SHIP_MAX_REGRESSION_OTHER = 0.005  # max MAE regression on non-PTS stats


def _load_gates() -> pd.DataFrame:
    """Load cv_coverage_gates parquet."""
    p = ROOT / "data" / "intelligence" / "cv_coverage_gates.parquet"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found — run scripts/build_cv_coverage_gates.py first"
        )
    return pd.read_parquet(p)


def _get_baseline_wf(n_splits: int, force_rerun: bool) -> dict:
    """Load or re-run prop_pergame_walk_forward.py baseline."""
    wf_path = ROOT / "data" / "models" / "prop_pergame_walk_forward.json"
    if wf_path.exists() and not force_rerun:
        with open(wf_path) as f:
            wf = json.load(f)
        n_folds_cached = len(next(iter(wf["folds_per_stat"].values())))
        if n_folds_cached >= n_splits:
            print(f"Re-using cached walk_forward.json ({n_folds_cached} folds)")
            return wf
        print(f"Cached WF has {n_folds_cached} folds; need {n_splits} — re-running")

    print(f"Running prop_pergame_walk_forward.py --splits {n_splits} ...")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prop_pergame_walk_forward.py"),
         "--splits", str(n_splits)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    elapsed = time.time() - t0
    if result.returncode != 0:
        print("STDERR:", result.stderr[-500:])
        raise RuntimeError("prop_pergame_walk_forward.py failed")
    print(f"  walk_forward done in {elapsed:.0f}s")

    with open(wf_path) as f:
        return json.load(f)


def _mirror_fold_splits(rows: list, n_splits: int):
    """Mirror exact fold split logic from walk_forward.py.

    Yields (fold_idx, tr_slice, val_slice, ho_slice) tuples.
    tr_slice / val_slice / ho_slice are index ranges (start, end).
    """
    n = len(rows)
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
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
        yield fold_idx, (0, tr_end), (tr_end, va_end), (va_end, te_end)


def _train_pts_fold(X_tr, y_tr, X_val, y_val, X_ho, sw):
    """Train XGB + LGB 2-way blend for PTS only (mirrors walk_forward logic).
    Returns (holdout_predictions, 2way_mae, 2way_r2).
    """
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import r2_score

    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)

    def _blend(preds, y_v):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_v)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([0.5, 0.5])
        return w

    w2 = _blend([xv, lv], y_val)
    preds_ho = w2[0] * xh + w2[1] * lh
    mae = float(mean_absolute_error(y_val[:0], preds_ho[:0]) if len(preds_ho) == 0
                else mean_absolute_error(
                    np.concatenate([y_val, np.zeros(len(preds_ho))]),
                    np.concatenate([w2[0]*xv + w2[1]*lv, preds_ho])
                ))
    # Recompute holdout MAE only
    return preds_ho, w2


def _run_gate_validation(n_splits: int, force_rerun: bool) -> dict:
    """Core validation logic. Returns full results dict."""
    from src.prediction.prop_pergame import build_pergame_dataset, feature_columns, STATS as WF_STATS

    # 1. Load baseline WF (may re-run)
    baseline_wf = _get_baseline_wf(n_splits, force_rerun)
    baseline_pts = baseline_wf["by_stat"]["pts"]
    print(f"\nBaseline PTS (2way): MAE={baseline_pts['mae_2way_mean']:.4f} +- {baseline_pts['mae_2way_std']:.4f}")

    # 2. Load gates parquet
    gates = _load_gates()
    gates["game_date_ts"] = pd.to_datetime(gates["game_date"])
    gates["nba_player_id_int"] = gates["nba_player_id"].astype("Int64")

    # 3. Load pergame dataset (same as walk_forward)
    print(f"\nLoading pergame dataset for {n_splits}-fold gate validation...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  rows={n}, features={len(fc)}")
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    pts_idx = WF_STATS.index("pts")  # 0

    # Build lookup: (player_id, date) -> gate row
    # We need to match holdout rows to gates by (nba_player_id, game_date)
    gate_lookup: dict[tuple, dict] = {}
    for _, grow in gates.iterrows():
        pid = int(grow["nba_player_id_int"]) if pd.notna(grow["nba_player_id_int"]) else None
        if pid is None:
            continue
        gd = pd.Timestamp(grow["game_date_ts"]).date()
        gate_lookup[(pid, str(gd))] = {
            "xfg_shrunk": float(grow["xfg_shrunk_by_coverage"]) if pd.notna(grow["xfg_shrunk_by_coverage"]) else np.nan,
            "gate": float(grow["coverage_gate"]),
        }

    # 4. Per-fold PTS validation with gate blend and null control
    fold_results = []
    rng = np.random.default_rng(NULL_SEED)

    for fold_idx, (tr_s, tr_e), (va_s, va_e), (ho_s, ho_e) in _mirror_fold_splits(rows, n_splits):
        tr_end, va_end, te_end = tr_e, va_e, ho_e
        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end}")

        X_tr = X_all[:tr_end]
        X_val = X_all[tr_end:va_end]
        X_ho = X_all[va_end:te_end]

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        y_pts = np.array([r["target_pts"] for r in rows], dtype=float)
        y_tr = y_pts[:tr_end]
        y_val_pts = y_pts[tr_end:va_end]
        y_ho_pts = y_pts[va_end:te_end]

        t0 = time.time()
        ho_preds_2way, w2 = _train_pts_fold(X_tr, y_tr, X_val, y_val_pts, X_ho, sw)
        train_wall = time.time() - t0
        baseline_ho_mae = float(mean_absolute_error(y_ho_pts, ho_preds_2way))
        print(f"  PTS baseline 2way holdout MAE={baseline_ho_mae:.4f}  wall={train_wall:.0f}s")

        # Build gate values and null gate for holdout rows
        ho_rows = rows[va_end:te_end]
        xfg_shrunk_ho = []
        gate_vals_ho = []
        for r in ho_rows:
            pid = r.get("player_id")
            gd = str(r["date"][:10]) if len(r["date"]) > 10 else r["date"]
            key = (int(pid), gd) if pid else None
            gval = gate_lookup.get(key) if key else None
            if gval and not np.isnan(gval["xfg_shrunk"]):
                xfg_shrunk_ho.append(gval["xfg_shrunk"])
                gate_vals_ho.append(gval["gate"])
            else:
                xfg_shrunk_ho.append(np.nan)
                gate_vals_ho.append(np.nan)

        xfg_arr = np.array(xfg_shrunk_ho, dtype=float)
        gate_arr = np.array(gate_vals_ho, dtype=float)
        gate_valid = ~np.isnan(xfg_arr)

        n_gate_valid = gate_valid.sum()
        print(f"  Gate coverage in holdout: {n_gate_valid}/{len(ho_rows)} rows ({100*n_gate_valid/len(ho_rows):.1f}%)")

        # pts_scale_factor: ratio mean(pts_actual_tr) / mean(xfg_tr_valid) in training fold
        # xfg_shrunk is in [0,1] range; pts is in [0,50+] range
        # Scale: use mean(pts_actual_ho) / mean(xfg_valid_ho) as in-fold estimate
        if n_gate_valid > 0:
            pts_ho_mean = float(np.mean(y_ho_pts[gate_valid]))
            xfg_ho_mean = float(np.nanmean(xfg_arr[gate_valid]))
            pts_scale = pts_ho_mean / xfg_ho_mean if xfg_ho_mean > 0 else float(np.mean(y_ho_pts))
            # Use training fold scale to avoid data leakage
            tr_gate_vals = []
            tr_pts_vals = []
            for i, r in enumerate(rows[:tr_end]):
                pid = r.get("player_id")
                gd = str(r["date"][:10]) if len(r["date"]) > 10 else r["date"]
                key = (int(pid), gd) if pid else None
                gval = gate_lookup.get(key) if key else None
                if gval and not np.isnan(gval["xfg_shrunk"]):
                    tr_gate_vals.append(gval["xfg_shrunk"])
                    tr_pts_vals.append(y_pts[i])
            if len(tr_gate_vals) > 5:
                pts_scale = float(np.mean(tr_pts_vals)) / float(np.mean(tr_gate_vals))
            print(f"  pts_scale_factor={pts_scale:.2f}")
        else:
            pts_scale = float(np.mean(y_ho_pts))
            print(f"  No gate coverage — pts_scale={pts_scale:.2f} (fallback)")

        # REAL gate blend
        blended_real = ho_preds_2way.copy()
        if n_gate_valid > 0:
            blended_real[gate_valid] = (
                BASE_MIX * ho_preds_2way[gate_valid] +
                GATE_MIX * xfg_arr[gate_valid] * pts_scale
            )
        mae_real = float(mean_absolute_error(y_ho_pts, blended_real))
        delta_real = mae_real - baseline_ho_mae

        # NULL control: replace gate values with Uniform(0,1)
        blended_null = ho_preds_2way.copy()
        if n_gate_valid > 0:
            null_gates = rng.uniform(0, 1, size=n_gate_valid).astype(float)
            # Recompute xfg_shrunk with null gate: prior + null_gate * (raw - prior)
            # We use same xfg_shrunk values (they already have gate baked in)
            # To isolate gate effect: reconstruct xfg_shrunk with null gate
            # xfg_shrunk = prior + gate * (raw - prior)
            # We don't have raw/prior separately in the lookup, so use the gate ratio:
            # null_xfg ~ xfg_baseline_prior + null_gate * (xfg_shrunk - xfg_baseline_prior) / gate
            # Simpler: use xfg_shrunk at null gate weight directly
            # Since gate is [0,1] and null_gate is [0,1], substitute null_gate for gate_arr
            # xfg_null = prior + null_gate * (raw - prior)
            # We have: xfg_shrunk = prior + gate * (raw - prior)
            # So: raw - prior = (xfg_shrunk - prior) / gate   [when gate > 0]
            # Approximate: use xfg_shrunk / gate * null_gate (ignoring prior offset)
            gate_valid_vals = gate_arr[gate_valid]
            xfg_valid_vals = xfg_arr[gate_valid]
            # For rows where gate > 0, compute null_xfg = xfg_valid * null_gate / gate
            # For gate = 0 (n_prior=0): null gate can't improve/hurt either -> use xfg_shrunk
            safe_gate = np.where(gate_valid_vals > 0.05, gate_valid_vals, 0.119)  # floor at n=0 sigmoid
            null_xfg = xfg_valid_vals * null_gates / safe_gate
            null_xfg = np.clip(null_xfg, 0, 1)
            blended_null[gate_valid] = (
                BASE_MIX * ho_preds_2way[gate_valid] +
                GATE_MIX * null_xfg * pts_scale
            )
        mae_null = float(mean_absolute_error(y_ho_pts, blended_null))
        delta_null = mae_null - baseline_ho_mae

        print(f"  PTS: baseline={baseline_ho_mae:.4f}  real_gate={mae_real:.4f}  "
              f"null_gate={mae_null:.4f}")
        print(f"  delta_real={delta_real:+.4f}  delta_null={delta_null:+.4f}  "
              f"gap={delta_real-delta_null:+.4f}")

        fold_results.append({
            "fold": fold_idx + 1,
            "n_holdout": len(ho_rows),
            "n_gate_valid": int(n_gate_valid),
            "gate_coverage_pct": float(100 * n_gate_valid / len(ho_rows)),
            "pts_scale_factor": float(pts_scale),
            "baseline_mae": float(baseline_ho_mae),
            "gated_mae": float(mae_real),
            "null_mae": float(mae_null),
            "delta_real": float(delta_real),
            "delta_null": float(delta_null),
            "null_gap": float(delta_real - delta_null),
            "real_positive": bool(delta_real < 0),
        })

    # 5. Other-stat regression check (from cached WF baseline)
    other_stat_max_regression = 0.0
    other_stat_regressions = {}
    print("\n=== Other-stat regression check (from cached WF baseline) ===")
    for stat in STATS:
        if stat == "pts":
            continue
        s = baseline_wf["by_stat"].get(stat, {})
        mae_2way = s.get("mae_2way_mean", 0.0)
        # The gate blend is PTS-only; other stats are unmodified
        # So other-stat MAE = baseline 2way MAE (no change)
        other_stat_regressions[stat] = 0.0
        print(f"  {stat.upper()}: baseline_mae={mae_2way:.4f}  no-change (gate is PTS-only)")

    # 6. Summarize
    print("\n=== INT-53 E1 CV COVERAGE GATE VALIDATION RESULTS ===")
    n_folds_run = len(fold_results)
    if n_folds_run == 0:
        print("FATAL: No folds ran (dataset too small?)")
        return {"verdict": "REJECT", "reason": "no_folds_ran"}

    delta_reals = [f["delta_real"] for f in fold_results]
    delta_nulls = [f["delta_null"] for f in fold_results]
    n_positive = sum(1 for f in fold_results if f["real_positive"])
    mean_delta_real = float(np.mean(delta_reals))
    mean_delta_null = float(np.mean(delta_nulls))
    mean_null_gap = float(np.mean([f["null_gap"] for f in fold_results]))
    mean_gate_cov = float(np.mean([f["gate_coverage_pct"] for f in fold_results]))

    # Threshold adjustment for 2 folds (n_splits=2)
    min_pos_thresh = max(2, int(np.ceil(n_folds_run * 0.6)))  # 60% of folds

    print(f"\nFolds run: {n_folds_run}")
    print(f"Gate coverage in holdout: {mean_gate_cov:.1f}% mean")
    print(f"\nPer-fold results:")
    print(f"{'Fold':>5} {'N_ho':>6} {'Gate%':>6} {'Base':>7} {'Real':>7} {'Null':>7} {'dReal':>7} {'dNull':>7} {'Gap':>7} {'Pos?':>5}")
    for fr in fold_results:
        print(f"  {fr['fold']:>3}  {fr['n_holdout']:>6}  {fr['gate_coverage_pct']:>5.1f}%  "
              f"{fr['baseline_mae']:>7.4f}  {fr['gated_mae']:>7.4f}  {fr['null_mae']:>7.4f}  "
              f"{fr['delta_real']:>+7.4f}  {fr['delta_null']:>+7.4f}  {fr['null_gap']:>+7.4f}  "
              f"{'YES' if fr['real_positive'] else 'NO':>5}")

    print(f"\nSummary:")
    print(f"  Mean delta_real PTS  : {mean_delta_real:+.4f}")
    print(f"  Mean delta_null PTS  : {mean_delta_null:+.4f}")
    print(f"  Mean null_gap        : {mean_null_gap:+.4f}  (real - null; must be < -0.0015)")
    print(f"  Folds positive       : {n_positive}/{n_folds_run}  (need >= {min_pos_thresh})")
    print(f"  Other-stat regressions: all zero (gate is PTS-only blend)")

    # Ship criteria evaluation
    c1 = n_positive >= min_pos_thresh
    c2 = other_stat_max_regression <= SHIP_MAX_REGRESSION_OTHER
    c3 = mean_delta_real <= SHIP_MEAN_DELTA_MAX
    c4 = mean_null_gap < -SHIP_NULL_GAP  # delta_real - delta_null < -0.0015

    print(f"\nShip criteria:")
    print(f"  C1 folds positive ({n_positive}>={min_pos_thresh})            : {'PASS' if c1 else 'FAIL'}")
    print(f"  C2 no other-stat regression                : {'PASS' if c2 else 'FAIL'}")
    print(f"  C3 mean delta PTS <= {SHIP_MEAN_DELTA_MAX}            : {'PASS' if c3 else 'FAIL'} ({mean_delta_real:+.4f})")
    print(f"  C4 null_gap < -{SHIP_NULL_GAP} (real beats random)  : {'PASS' if c4 else 'FAIL'} ({mean_null_gap:+.4f})")

    if all([c1, c2, c3, c4]):
        verdict = "SHIP"
    elif c3 and c4 and not c1:
        verdict = "MARGINAL"
    else:
        verdict = "REJECT"

    print(f"\n*** VERDICT: {verdict} ***")
    if verdict == "REJECT":
        reasons = []
        if not c1:
            reasons.append(f"folds_positive={n_positive}<{min_pos_thresh}")
        if not c3:
            reasons.append(f"mean_delta={mean_delta_real:+.4f}>={SHIP_MEAN_DELTA_MAX}")
        if not c4:
            reasons.append(f"null_gap={mean_null_gap:+.4f}>=-{SHIP_NULL_GAP} "
                           f"(gate indistinguishable from random blend — regularization artifact)")
        print(f"Reject reason(s): {', '.join(reasons)}")
        if not c4:
            print("\nX3a pattern detected: gate improvement is consistent with random blending.")
            print("  The coverage_gate likely captures 'is_star' variance already in")
            print("  the model's minutes/usage features. The 15% xfg blend is equivalent")
            print("  to adding a random regularization term toward the prior, not a")
            print("  discriminative signal. Do NOT ship.")

    results = {
        "verdict": verdict,
        "n_splits_run": n_folds_run,
        "mean_gate_coverage_pct": mean_gate_cov,
        "mean_delta_real_pts": mean_delta_real,
        "mean_delta_null_pts": mean_delta_null,
        "mean_null_gap_pts": mean_null_gap,
        "n_folds_positive": n_positive,
        "criteria": {"c1_folds": c1, "c2_no_regression": c2, "c3_delta": c3, "c4_null": c4},
        "fold_details": fold_results,
        "baseline_wf_pts_2way": baseline_pts,
        "other_stat_regressions": other_stat_regressions,
    }

    out_path = ROOT / "data" / "models" / "cv_coverage_gate_validation.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--splits", type=int, default=2,
                    help="Number of walk-forward splits (default 2; 4 for full)")
    ap.add_argument("--rerun-wf", action="store_true",
                    help="Force re-run of prop_pergame_walk_forward.py")
    args = ap.parse_args()
    _run_gate_validation(n_splits=args.splits, force_rerun=args.rerun_wf)
