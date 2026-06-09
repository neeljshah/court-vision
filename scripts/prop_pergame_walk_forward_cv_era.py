"""prop_pergame_walk_forward_cv_era.py — INT-127: CV-era-restricted WF protocol.

Re-tests INT-118 (CV pace) and INT-91 (team atlas) with folds restricted to
dates where CV-derived sidecars have actual coverage (>= CV_ERA_START).

Background:
  Standard 4-fold WF spans 2022-2026, but CV sidecars only have data from
  2025-04-11 onward.  Folds 1-3 had 0% sidecar coverage, making the gate
  structurally impossible to pass — not a signal quality failure.

  This driver restricts the dataset to [CV_ERA_START, latest] so ALL folds
  are within the CV coverage window.

Architecture:
  - XGB + LGB 2-way blend (no MLP) — mirrors prop_pergame_walk_forward_built_no_mlp.py
  - NaN imputation: per-fold training medians only (no leakage)
  - 4 folds within CV-era date range
  - Gates: G2 (isolation WF >=3/4 pos on >=1 stat), G4 (null control ratio>=1.5),
           G5 (no >0.003 regression), G6 (per-stat consistency, not one-fold spike)

Run:
    python scripts/prop_pergame_walk_forward_cv_era.py \\
        --sidecar-path data/intelligence/cv_pace_features_sidecar.parquet \\
        --stats pts,fg3m

    python scripts/prop_pergame_walk_forward_cv_era.py \\
        --sidecar-path data/intelligence/atlas_features_sidecar.parquet \\
        --stats pts,reb,fg3m

    python scripts/prop_pergame_walk_forward_cv_era.py --mode baseline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Dict, Any, Optional

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

from src.prediction.prop_pergame import (  # noqa: E402
    STATS as ALL_STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# CV_ERA_START — max(earliest_pace_non_null, earliest_atlas_non_null)
# pace: 2025-01-25, atlas: 2025-04-11 → max = 2025-04-11
# ---------------------------------------------------------------------------
CV_ERA_START = "2025-04-11"

# Minimum rows kill switch
MIN_CV_ERA_ROWS = 2000

# Minimum sidecar coverage per fold for a fold to be considered meaningful
MIN_FOLD_COVERAGE = 0.10


# ---------------------------------------------------------------------------
# Sidecar loading — generic, handles both pace and atlas key conventions
# ---------------------------------------------------------------------------
def _load_sidecar_generic(sidecar_path: str) -> tuple[pd.DataFrame, List[str]]:
    """Load sidecar parquet; detect date column name; return (df, signal_cols)."""
    df = pd.read_parquet(sidecar_path)
    df["player_id"] = df["player_id"].astype(int)

    # Detect date column
    if "game_date" in df.columns:
        df = df.rename(columns={"game_date": "date"})
    df["date"] = df["date"].astype(str).str[:10]

    # Signal columns = everything except player_id + date
    signal_cols = [c for c in df.columns if c not in ("player_id", "date")]
    print(f"  Sidecar: {os.path.basename(sidecar_path)}, rows={len(df)}, "
          f"signal_cols={signal_cols}")
    return df, signal_cols


def _attach_sidecar(rows: list, sidecar: pd.DataFrame,
                    signal_cols: List[str]) -> tuple[list, List[str]]:
    """Attach sidecar columns to rows via (player_id, date) key."""
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "date"] + signal_cols].iterrows():
        key = (int(row["player_id"]), str(row["date"])[:10])
        lookup[key] = {c: float(row[c]) if pd.notna(row[c]) else np.nan
                       for c in signal_cols}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in signal_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, signal_cols


# ---------------------------------------------------------------------------
# Training: XGB + LGB 2-way (no MLP) — identical to no_mlp template
# ---------------------------------------------------------------------------
def _train_one_stat(stat: str, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """2-way XGB+LGB blend; return holdout MAE/R²."""
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
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)
    except Exception:
        _xgb_kwargs.pop("device", None)
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.8, min_child_samples=20,
        reg_lambda=2.0, reg_alpha=0.5, random_state=42,
        objective="poisson" if is_count else "regression",
        n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
              sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])

    xv, lv = xgb_m.predict(X_val), lgb_m.predict(X_val)
    xh, lh = xgb_m.predict(X_ho), lgb_m.predict(X_ho)

    def _blend(preds, y_arr):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_arr)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([0.5, 0.5])
        return w

    w = _blend([xv, lv], y_val)
    b = w[0] * xh + w[1] * lh
    mae = float(mean_absolute_error(y_ho, b))
    r2 = float(r2_score(y_ho, b))
    return {"mae": mae, "r2": r2, "w": [float(x) for x in w]}


# ---------------------------------------------------------------------------
# NaN imputation (per-fold training medians — no leakage)
# ---------------------------------------------------------------------------
def _impute_fold(X_tr: np.ndarray, X_val: np.ndarray, X_ho: np.ndarray,
                 base_n_cols: int) -> tuple:
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho
    for col_i in range(base_n_cols, X_tr.shape[1]):
        train_col = X_tr[:, col_i]
        non_nan = train_col[~np.isnan(train_col)]
        median = float(np.median(non_nan)) if len(non_nan) > 0 else 0.0
        for arr in (X_tr, X_val, X_ho):
            mask = np.isnan(arr[:, col_i])
            arr[mask, col_i] = median
    return X_tr, X_val, X_ho


# ---------------------------------------------------------------------------
# CV-era walk-forward engine
# ---------------------------------------------------------------------------
def walk_forward_cv_era(
    n_splits: int = 4,
    signal_cols: Optional[List[str]] = None,
    sidecar_df: Optional[pd.DataFrame] = None,
    eval_stats: Optional[List[str]] = None,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  CV_ERA_START={CV_ERA_START}  null={null_shuffle}")
    print(f"{'='*60}")

    # Load full dataset, sort, restrict to CV era
    print("Loading pergame dataset ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n_total = len(rows)

    rows = [r for r in rows if r["date"] >= CV_ERA_START]
    n = len(rows)
    base_n_cols = len(fc)
    print(f"  Total rows: {n_total} -> CV-era rows: {n} (>= {CV_ERA_START})")

    # KILL SWITCH
    if n < MIN_CV_ERA_ROWS:
        print(f"  [KILL SWITCH] CV-era rows {n} < {MIN_CV_ERA_ROWS} — ABORT")
        return {"error": "kill_switch_too_few_rows", "n_cv_era": n}

    stats_to_eval = eval_stats or ALL_STATS

    # Attach sidecar if provided
    extra_cols: List[str] = []
    if signal_cols and sidecar_df is not None:
        rows, extra_cols = _attach_sidecar(rows, sidecar_df, signal_cols)
        print(f"  Extra sidecar cols: {extra_cols}")

    all_cols = fc + extra_cols
    X_all = np.array([[r.get(c, np.nan) for c in all_cols] for r in rows], dtype=float)

    # Build 4-fold cutoffs within CV era
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in stats_to_eval}
    fold_coverage_info = []

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)

        # Minimum size guard: at least 500 train, 200 holdout (relaxed vs full-corpus)
        if tr_end < 500 or (te_end - va_end) < 200:
            print(f"  fold {fold_idx+1}: too small (tr={tr_end} ho={te_end-va_end}) — skip")
            continue

        X_tr = X_all[:tr_end].copy()
        X_val = X_all[tr_end:va_end].copy()
        X_ho = X_all[va_end:te_end].copy()
        X_tr, X_val, X_ho = _impute_fold(X_tr, X_val, X_ho, base_n_cols)

        # Null shuffle: permute sidecar columns
        if null_shuffle and extra_cols:
            rng = np.random.default_rng(null_seed)
            for col_i in range(base_n_cols, X_all.shape[1]):
                combined = np.concatenate([X_tr[:, col_i], X_val[:, col_i], X_ho[:, col_i]])
                rng.shuffle(combined)
                X_tr[:, col_i] = combined[:tr_end]
                X_val[:, col_i] = combined[tr_end:tr_end + (va_end - tr_end)]
                X_ho[:, col_i] = combined[tr_end + (va_end - tr_end):]

        # Coverage in holdout
        cov = 0.0
        if extra_cols and not null_shuffle:
            ho_rows = rows[va_end:te_end]
            cov = float(np.mean([
                1 if not np.isnan(r.get(extra_cols[0], np.nan)) else 0
                for r in ho_rows
            ]))
        fold_coverage_info.append({"fold": fold_idx + 1, "coverage": cov})

        # Sample weights (recency decay)
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
              f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)

        t0 = time.time()
        for stat in stats_to_eval:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat(stat, X_tr, y[:tr_end],
                                  X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            res["coverage"] = cov
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} mae={res['mae']:.4f} r2={res['r2']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    # Summaries
    print(f"\n=== SUMMARY [{mode_label}] ===")
    summary: dict = {
        "mode": mode_label,
        "cv_era_start": CV_ERA_START,
        "n_cv_era_rows": n,
        "signal_cols": extra_cols,
        "null_shuffle": null_shuffle,
        "fold_coverage": fold_coverage_info,
        "folds_per_stat": per_stat_fold_metrics,
        "by_stat": {},
    }
    for stat in stats_to_eval:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        maes = [f["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_mean": float(np.mean(maes)),
            "mae_std": float(np.std(maes)),
            "per_fold_mae": maes,
        }
        print(f"  {stat.upper():4s} mae={np.mean(maes):.4f}±{np.std(maes):.4f}")

    return summary


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------
def _evaluate_gates(base_results: dict, aug_results: dict,
                    null_results: dict, eval_stats: List[str]) -> dict:
    """Apply G2/G3/G5/G6 gates to CV-era WF results."""
    gates: dict = {}

    base_by = base_results.get("by_stat", {})
    aug_by = aug_results.get("by_stat", {})
    null_by = null_results.get("by_stat", {})

    print("\n=== G2: CV-ERA ISOLATION DELTAS (aug - base per fold) ===")
    g2_pass = False
    g2_detail: dict = {}
    for stat in eval_stats:
        if stat not in base_by or stat not in aug_by:
            continue
        base_folds = base_results["folds_per_stat"].get(stat, [])
        aug_folds = aug_results["folds_per_stat"].get(stat, [])
        per_fold_d = [a["mae"] - b["mae"]
                      for a, b in zip(aug_folds, base_folds)]
        n_neg = sum(1 for d in per_fold_d if d < 0)
        mean_d = float(np.mean(per_fold_d)) if per_fold_d else float("nan")
        g2_detail[stat] = {
            "per_fold_delta": per_fold_d,
            "n_neg": n_neg,
            "mean_delta": mean_d,
        }
        fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(per_fold_d))
        print(f"  {stat.upper():4s}: {fold_str}  neg={n_neg}/4  mean={mean_d:+.4f}")
        if n_neg >= 3:
            g2_pass = True
    print(f"\n  G2 result: {'PASS' if g2_pass else 'FAIL'} (>=3/4 neg folds on >=1 eval stat)")

    print("\n=== G3: NULL CONTROL ===")
    g3_pass = False
    g3_detail: dict = {}
    core_ratios = []
    for stat in eval_stats:
        if stat not in base_by or stat not in aug_by or stat not in null_by:
            continue
        real_d = aug_by[stat]["mae_mean"] - base_by[stat]["mae_mean"]
        null_d = null_by[stat]["mae_mean"] - base_by[stat]["mae_mean"]
        ratio = abs(real_d) / abs(null_d) if abs(null_d) > 1e-6 else (
            float("inf") if real_d < 0 else 0.0)
        g3_detail[stat] = {"real_delta": real_d, "null_delta": null_d, "ratio": ratio}
        core_ratios.append(ratio)
        print(f"  {stat.upper():4s}: real={real_d:+.4f}  null={null_d:+.4f}  ratio={ratio:.2f}")
    mean_ratio = float(np.mean(core_ratios)) if core_ratios else 0.0
    g3_pass = mean_ratio >= 1.5
    print(f"\n  G3 mean_ratio={mean_ratio:.2f} — {'PASS' if g3_pass else 'FAIL'} (need >=1.5)")

    print("\n=== G5: NO-REGRESSION (non-primary stats) ===")
    g5_pass = True
    g5_detail: dict = {}
    non_primary = [s for s in ALL_STATS if s in base_by and s in aug_by]
    for stat in non_primary:
        b = base_by[stat]["mae_mean"]
        a = aug_by[stat]["mae_mean"]
        delta = a - b
        flag = "FAIL" if delta > 0.003 else "OK"
        if delta > 0.003:
            g5_pass = False
        g5_detail[stat] = {"base": b, "aug": a, "delta": delta}
        print(f"  {stat.upper():3s}: base={b:.4f} aug={a:.4f} delta={delta:+.4f} [{flag}]")
    print(f"\n  G5 result: {'PASS' if g5_pass else 'FAIL'} (no >0.003 regression)")

    print("\n=== G6: CONSISTENCY (not single-fold spike) ===")
    g6_pass = True
    g6_detail: dict = {}
    for stat in eval_stats:
        if stat not in g2_detail:
            continue
        deltas = g2_detail[stat]["per_fold_delta"]
        n_neg = g2_detail[stat]["n_neg"]
        # Passes if improvement is in >=2 folds AND no single fold is >0.1 worse
        max_regress = max(deltas) if deltas else 0.0
        consistent = (n_neg >= 2) and (max_regress <= 0.1)
        g6_detail[stat] = {"n_neg": n_neg, "max_regress": max_regress, "pass": consistent}
        if not consistent:
            g6_pass = False
        print(f"  {stat.upper():4s}: n_neg={n_neg}/4 max_regress={max_regress:+.4f} "
              f"[{'OK' if consistent else 'FAIL'}]")
    print(f"\n  G6 result: {'PASS' if g6_pass else 'FAIL'} (>=2 neg folds + no spike >0.1)")

    overall = g2_pass and g3_pass and g5_pass and g6_pass
    print(f"\n=== GATE SCOREBOARD ===")
    print(f"  G2 (isolation WF >=3/4):   {'PASS' if g2_pass else 'FAIL'}")
    print(f"  G3 (null control >=1.5):   {'PASS' if g3_pass else 'FAIL'}")
    print(f"  G5 (no regression >0.003): {'PASS' if g5_pass else 'FAIL'}")
    print(f"  G6 (consistency >=2 folds): {'PASS' if g6_pass else 'FAIL'}")
    print(f"\n  VERDICT: {'PROMOTE' if overall else 'REJECT'}  ({sum([g2_pass, g3_pass, g5_pass, g6_pass])}/4 gates)")

    return {
        "g2_pass": g2_pass, "g2_detail": g2_detail,
        "g3_pass": g3_pass, "g3_detail": g3_detail, "g3_mean_ratio": mean_ratio,
        "g5_pass": g5_pass, "g5_detail": g5_detail,
        "g6_pass": g6_pass, "g6_detail": g6_detail,
        "overall_pass": overall,
        "verdict": "PROMOTE" if overall else "REJECT",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="INT-127: CV-era-restricted WF protocol")
    ap.add_argument("--sidecar-path", default=None,
                    help="Path to sidecar parquet (relative to project root or absolute)")
    ap.add_argument("--stats", default=None,
                    help="Comma-separated stats to evaluate (default: all)")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"],
                    default="all")
    ap.add_argument("--out-json", default=None,
                    help="Output JSON path (default: auto)")
    args = ap.parse_args()

    eval_stats = args.stats.split(",") if args.stats else ALL_STATS
    print(f"Eval stats: {eval_stats}")
    print(f"CV_ERA_START: {CV_ERA_START}")

    # Resolve sidecar path
    sidecar_df: Optional[pd.DataFrame] = None
    signal_cols: Optional[List[str]] = None
    if args.sidecar_path:
        sp = args.sidecar_path
        if not os.path.isabs(sp):
            sp = os.path.join(PROJECT_DIR, sp)
        print(f"Sidecar: {sp}")
        sidecar_df, signal_cols = _load_sidecar_generic(sp)

    results: Dict[str, Any] = {}

    # BASELINE
    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward_cv_era(
            n_splits=args.splits,
            eval_stats=eval_stats,
            mode_label="cv_era_baseline",
        )
        if "error" in results["baseline"]:
            print("[ABORT] Kill switch fired on baseline.")
            return results

    # ISOLATION (with sidecar)
    if args.mode in ("isolation", "all") and sidecar_df is not None:
        results["isolation"] = walk_forward_cv_era(
            n_splits=args.splits,
            signal_cols=signal_cols,
            sidecar_df=sidecar_df,
            eval_stats=eval_stats,
            mode_label="cv_era_isolation",
        )

    # NULL CONTROL
    if args.mode in ("null", "all") and sidecar_df is not None:
        results["null"] = walk_forward_cv_era(
            n_splits=args.splits,
            signal_cols=signal_cols,
            sidecar_df=sidecar_df,
            eval_stats=eval_stats,
            null_shuffle=True,
            null_seed=0,
            mode_label="cv_era_null",
        )

    # Gate evaluation
    gate_result: dict = {}
    if ("baseline" in results and "isolation" in results and "null" in results
            and sidecar_df is not None):
        gate_result = _evaluate_gates(
            results["baseline"], results["isolation"], results["null"],
            eval_stats=eval_stats,
        )

    # Determine output path
    if args.out_json:
        out_path = args.out_json
        if not os.path.isabs(out_path):
            out_path = os.path.join(PROJECT_DIR, out_path)
    else:
        # Auto-name based on sidecar
        if args.sidecar_path and "atlas" in args.sidecar_path:
            fname = "cv_era_wf_int91_metrics.json"
        elif args.sidecar_path and "cv_pace" in args.sidecar_path:
            fname = "cv_era_wf_int118_metrics.json"
        else:
            fname = "cv_era_wf_baseline_metrics.json"
        out_path = os.path.join(PROJECT_DIR, "data", "models", fname)

    out = {
        "int_id": "INT-127",
        "cv_era_start": CV_ERA_START,
        "n_cv_era_rows": results.get("baseline", {}).get("n_cv_era_rows"),
        "eval_stats": eval_stats,
        "sidecar": args.sidecar_path,
        "results": results,
        "gates": gate_result,
        "verdict": gate_result.get("verdict", "BASELINE_ONLY"),
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return out


if __name__ == "__main__":
    main()
