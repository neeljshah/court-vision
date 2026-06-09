"""prop_pergame_walk_forward_atlas.py — walk-forward validating 4 team atlas features.

INT-91: Wires C1+C2 (team_tempo_z, team_spacing_z), C3 (opp_def_intensity_z),
C4 (opp_paint_allowance_z) from atlas_features_sidecar.parquet into prop_pergame
rows and compares baseline 2-way (XGB+LGB) vs atlas-augmented 2-way.

NOTE: mx_ (matchup_grid) features are DROPPED — kill switch triggered at 14.4% coverage
(< 20% threshold required per INT-91 spec).

DO NOT MODIFY: scripts/prop_pergame_walk_forward.py, src/prediction/*.py

Run:
    python scripts/prop_pergame_walk_forward_atlas.py
    python scripts/prop_pergame_walk_forward_atlas.py --splits 4 --no-null-control
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import warnings
from datetime import datetime
from typing import List

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd


def _resolve_device(device_arg: str) -> str:
    """Resolve 'auto' to 'cuda' if available, else 'cpu'."""
    if device_arg == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return device_arg


# Module-level device (set by main())
_XGB_DEVICE: str = "cpu"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import build_pergame_dataset  # noqa: E402

# INT-91: top-line stats only; skip MLP blend to halve runtime
STATS = ["pts", "reb", "fg3m"]
ATLAS_FEATS = [
    "team_tempo_z",
    "team_spacing_z",
    "opp_def_intensity_z",
    "opp_paint_allowance_z",
]
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "atlas_features_sidecar.parquet")


def _load_sidecar(shuffle_teams: bool = False) -> dict:
    """Load sidecar parquet, return dict keyed by (player_id, date_str)."""
    df = pd.read_parquet(SIDECAR_PATH)
    if shuffle_teams:
        # G5 null control: shuffle atlas values independently per feature
        rng = np.random.RandomState(99)
        for col in ATLAS_FEATS:
            vals = df[col].values.copy()
            non_null_idx = np.where(~np.isnan(vals))[0]
            rng.shuffle(non_null_idx)
            shuffled_vals = vals.copy()
            shuffled_vals[~np.isnan(vals)] = vals[non_null_idx]
            df[col] = shuffled_vals
    result = {}
    for _, row in df.iterrows():
        result[(int(row["player_id"]), str(row["date"]))] = row
    return result


def _inject_atlas(rows: list, sidecar: dict) -> tuple[list, list]:
    """Inject atlas features into rows list. Returns augmented rows + atlas feature names."""
    augmented = []
    for r in rows:
        new_r = dict(r)
        iso_date = r["date"][:10]
        sd = sidecar.get((int(r["player_id"]), iso_date), {})
        for feat in ATLAS_FEATS:
            val = sd.get(feat, np.nan) if isinstance(sd, dict) else getattr(sd, feat, np.nan)
            new_r[feat] = float(val) if (val is not None and not (isinstance(val, float) and np.isnan(val))) else np.nan
        augmented.append(new_r)
    return augmented, ATLAS_FEATS


def _train_one_stat(stat: str, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB 2-way blend for one stat."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    is_count = stat in ("stl", "blk")
    _xgb_kwargs = dict(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    if _XGB_DEVICE == "cuda":
        _xgb_kwargs["device"] = "cuda"
    try:
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kwargs.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
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

    def _blend(preds, y_val_arr):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_val_arr)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([1.0 / len(preds)] * len(preds))
        return w

    w2 = _blend([xv, lv], y_val)
    b2 = w2[0] * xh + w2[1] * lh
    mae = float(mean_absolute_error(y_ho, b2))
    r2 = float(r2_score(y_ho, b2))
    return {"mae": mae, "r2": r2, "w": [float(x) for x in w2]}


def _run_wf(rows_base: list, fc_base: list, sidecar: dict, label: str, n_splits: int) -> dict:
    """Run walk-forward; returns per-stat fold metrics."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    # Inject atlas features
    rows, atlas_fc = _inject_atlas(rows_base, sidecar)
    fc = fc_base + atlas_fc

    # Impute atlas NaN with 0 (mean-ish for z-scores)
    rows_sorted = sorted(rows, key=lambda r: r["date"])
    n = len(rows_sorted)
    print(f"  rows={n}, features={len(fc)}")

    X_all = np.array([[r.get(c, 0.0) if not (isinstance(r.get(c, 0.0), float) and np.isnan(r.get(c, 0.0))) else 0.0
                       for c in fc] for r in rows_sorted], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in STATS}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small — skip")
            continue
        X_tr = X_all[:tr_end]
        X_val = X_all[tr_end:va_end]
        X_ho = X_all[va_end:te_end]
        tr_dates = [datetime.fromisoformat(rows_sorted[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end}", flush=True)
        t0 = time.time()
        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows_sorted], dtype=float)
            res = _train_one_stat(
                stat, X_tr, y[:tr_end], X_val, y[tr_end:va_end], X_ho, y[va_end:te_end], sw
            )
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} mae={res['mae']:.4f} r2={res['r2']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    return per_stat_fold_metrics


def _summarise(metrics: dict) -> dict:
    summary = {}
    for stat, folds in metrics.items():
        if not folds:
            continue
        maes = [f["mae"] for f in folds]
        r2s = [f["r2"] for f in folds]
        summary[stat] = {
            "mae_mean": float(np.mean(maes)),
            "mae_std": float(np.std(maes)),
            "r2_mean": float(np.mean(r2s)),
            "per_fold_mae": maes,
        }
    return summary


def walk_forward(n_splits: int = 4, run_null_control: bool = True) -> dict:
    print("Loading dataset...")
    rows_base, fc_base = build_pergame_dataset(min_prior=0)
    rows_base.sort(key=lambda r: r["date"])
    print(f"  {len(rows_base)} rows, {len(fc_base)} base features")

    print("\nLoading sidecar...")
    sidecar_real = _load_sidecar(shuffle_teams=False)

    # Baseline: atlas features imputed to 0 (no signal)
    baseline_metrics = _run_wf(rows_base, fc_base, {}, "BASELINE (no atlas)", n_splits)

    # Atlas-augmented
    atlas_metrics = _run_wf(rows_base, fc_base, sidecar_real, "ATLAS-AUGMENTED (4 features)", n_splits)

    # Per-fold delta
    print("\n=== PER-FOLD DELTA (atlas - baseline) ===")
    print(f"{'stat':6s} | " + " | ".join(f"fold{i+1:d}    " for i in range(n_splits)) + " | mean_delta")
    print("-" * 70)

    g4_results: dict = {}
    all_results: dict = {}

    for stat in STATS:
        bf = [f["mae"] for f in baseline_metrics[stat]]
        af = [f["mae"] for f in atlas_metrics[stat]]
        if not bf or not af:
            continue
        n_folds = min(len(bf), len(af))
        deltas = [af[i] - bf[i] for i in range(n_folds)]
        neg_folds = sum(1 for d in deltas if d < 0)
        mean_delta = float(np.mean(deltas))
        fold_str = " | ".join(f"{d:+.4f}" for d in deltas)
        print(f"  {stat.upper():4s} | {fold_str} | {mean_delta:+.4f} ({neg_folds}/{n_folds} neg)")
        g4_results[stat] = {"neg_folds": neg_folds, "n_folds": n_folds, "mean_delta": mean_delta, "deltas": deltas}
        all_results[stat] = {"baseline_mae": np.mean(bf), "atlas_mae": np.mean(af), "delta": mean_delta, "deltas": deltas}

    # G4: >= 3/4 folds negative on at least one top-line stat
    g4_pass = any(v["neg_folds"] >= 3 for v in g4_results.values())
    print(f"\nG4 gate: {'PASS' if g4_pass else 'FAIL'}")
    for stat, v in g4_results.items():
        print(f"  {stat.upper()}: {v['neg_folds']}/{v['n_folds']} neg folds, mean_delta={v['mean_delta']:+.5f}")

    # G6: no stat regresses > 0.005 on aggregate
    g6_pass = all(abs(v["mean_delta"]) <= 0.005 or v["mean_delta"] < 0 for v in g4_results.values())
    print(f"\nG6 gate: {'PASS' if g6_pass else 'FAIL (regression > 0.005)'}")
    for stat, v in g4_results.items():
        regress = v["mean_delta"] > 0.005
        print(f"  {stat.upper()}: delta={v['mean_delta']:+.5f} {'REGRESSES' if regress else 'OK'}")

    # G5 null control
    null_result = None
    if run_null_control:
        print("\n--- G5 NULL CONTROL (shuffled atlas mapping) ---")
        sidecar_null = _load_sidecar(shuffle_teams=True)
        null_metrics = _run_wf(rows_base, fc_base, sidecar_null, "NULL CONTROL (shuffled)", n_splits)
        null_deltas = {}
        for stat in STATS:
            bf = [f["mae"] for f in baseline_metrics[stat]]
            nf = [f["mae"] for f in null_metrics[stat]]
            if not bf or not nf:
                continue
            n_folds = min(len(bf), len(nf))
            null_d = [abs(nf[i] - bf[i]) for i in range(n_folds)]
            real_d = [abs(g4_results[stat]["deltas"][i]) for i in range(n_folds)]
            mean_null = float(np.mean(null_d))
            mean_real = float(np.mean(real_d)) if real_d else 0.0
            ratio = mean_null / mean_real if mean_real > 0 else float("inf")
            g5_ok = ratio < 0.5
            print(f"  {stat.upper()}: null_delta={mean_null:.5f} real_delta={mean_real:.5f} ratio={ratio:.2f} [{'PASS' if g5_ok else 'FAIL-ESCALATE'}]")
            null_deltas[stat] = {"mean_null": mean_null, "mean_real": mean_real, "ratio": ratio, "g5_pass": g5_ok}
        null_result = null_deltas

    # Verdict
    verdict = "SHIP" if g4_pass else "NO_SHIP"
    print(f"\n{'='*60}")
    print(f"  VERDICT: {verdict}")
    if not g4_pass:
        print("  Reason: atlas WF-negative (G4 failed all top-line stats)")
    print(f"{'='*60}")

    out_data = {
        "run_timestamp": datetime.now().isoformat(),
        "n_splits": n_splits,
        "stats": STATS,
        "atlas_features": ATLAS_FEATS,
        "kill_switch": "mx_ features dropped (matchup_grid coverage 14.4% < 20%)",
        "g4_pass": g4_pass,
        "g6_pass": g6_pass,
        "verdict": verdict,
        "per_stat": all_results,
        "g4_detail": g4_results,
        "g5_null_control": null_result,
    }

    out_path = os.path.join(PROJECT_DIR, "data", "models", "prop_pergame_walk_forward_atlas.json")
    with open(out_path, "w") as f:
        json.dump(out_data, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return out_data


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--no-null-control", action="store_true", help="Skip G5 null control")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()
    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-91] XGB device: {_XGB_DEVICE}")
    walk_forward(n_splits=args.splits, run_null_control=not args.no_null_control)
