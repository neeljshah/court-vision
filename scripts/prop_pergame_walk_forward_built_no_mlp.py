"""prop_pergame_walk_forward_built_no_mlp.py — INT-102 walk-forward sidecar test (XGB+LGB only).

Re-tests INT-83 ft_rate sidecar features using a 2-way XGB+LGB blend ONLY,
bypassing MLP entirely.  INT-94 showed MLP median-imputation under partial
coverage caused distribution shift in F3+F4 that dominated the 3-way signal.
This driver isolates the XGB+LGB contribution.

Architecture:
  - Mirrors prop_pergame_walk_forward_built.py but _train_one_stat returns
    only the 2-way blend (no MLP fitted at all — saves wall time).
  - NaN imputation: per-fold training medians, same as INT-94.
  - All 5 gates applied: G1 (pre-pass), G2 isolation, G3 null, G4 (pre-pass), G5.

Run:
    python scripts/prop_pergame_walk_forward_built_no_mlp.py --mode all
    python scripts/prop_pergame_walk_forward_built_no_mlp.py --mode baseline
    python scripts/prop_pergame_walk_forward_built_no_mlp.py --mode isolation
    python scripts/prop_pergame_walk_forward_built_no_mlp.py --mode null
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List, Dict, Any

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


# Module-level device (set by main(); importable tests default to cpu)
_XGB_DEVICE: str = "cpu"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# Sidecar signal definitions (same as INT-94)
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "built_signals_sidecar.parquet")

SIGNAL_COLS: Dict[str, List[str]] = {
    "ft_rate": ["ft_rate_q50", "ft_rate_spread", "ft_n_prior"],
}


def _load_sidecar() -> pd.DataFrame:
    """Load the sidecar parquet keyed on (player_id, game_date)."""
    df = pd.read_parquet(SIDECAR_PATH)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    return df


def _attach_sidecar(rows: list, sidecar: pd.DataFrame, signal_groups: List[str]) -> tuple:
    """Attach sidecar columns to rows.  Returns (augmented rows, extra_cols list)."""
    extra_cols = []
    for g in signal_groups:
        extra_cols.extend(SIGNAL_COLS[g])

    subset_cols = extra_cols
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + [c for c in subset_cols if c in sidecar.columns]].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in subset_cols if c in sidecar.columns}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in extra_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, extra_cols


# ---------------------------------------------------------------------------
# Training helper — XGB + LGB ONLY (no MLP)
# ---------------------------------------------------------------------------
def _train_one_stat_no_mlp(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw,
                           xgb_device: str = "cpu"):
    """Train XGB + LGB only; return 2-way holdout metrics.  MLP NOT fitted."""
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
    if xgb_device == "cuda":
        _xgb_kwargs["device"] = "cuda"
    try:
        xgb_m = xgb.XGBRegressor(**_xgb_kwargs)
        xgb_m.fit(X_tr, y_tr, eval_set=[(X_val, y_val)],
                  sample_weight=sw, verbose=False)
    except Exception:
        # GPU init failed — fall back to CPU silently
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

    def _blend(preds, y_val_arr):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_val_arr)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([1.0 / len(preds)] * len(preds))
        return w

    w2 = _blend([xv, lv], y_val)
    b2 = w2[0] * xh + w2[1] * lh
    mae2 = float(mean_absolute_error(y_ho, b2))
    r2_2 = float(r2_score(y_ho, b2))

    return {
        "two_way": {"mae": mae2, "r2": r2_2, "w": [float(x) for x in w2]},
    }


# ---------------------------------------------------------------------------
# Per-fold NaN imputation (training medians only — no leakage)
# ---------------------------------------------------------------------------
def _impute_fold(X_tr: np.ndarray, X_val: np.ndarray, X_ho: np.ndarray,
                 base_n_cols: int) -> tuple:
    """Fill NaN in sidecar columns using training-fold median only."""
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho

    extra_start = base_n_cols
    for col_i in range(extra_start, X_tr.shape[1]):
        train_col = X_tr[:, col_i]
        non_nan = train_col[~np.isnan(train_col)]
        median = float(np.median(non_nan)) if len(non_nan) > 0 else 0.0
        for arr in (X_tr, X_val, X_ho):
            mask = np.isnan(arr[:, col_i])
            arr[mask, col_i] = median

    return X_tr, X_val, X_ho


# ---------------------------------------------------------------------------
# Walk-forward engine (2-way only)
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    signal_groups: List[str] | None = None,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  signals={signal_groups}  null={null_shuffle}  [NO-MLP]")
    print(f"{'='*60}")

    print(f"Loading dataset (n_splits={n_splits}) ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    base_n_cols = len(fc)
    print(f"  rows={n}, base features={base_n_cols}")

    extra_cols: List[str] = []
    if signal_groups:
        sidecar = _load_sidecar()
        rows, extra_cols = _attach_sidecar(rows, sidecar, signal_groups)
        print(f"  extra sidecar cols: {extra_cols}")

    all_cols = fc + extra_cols
    X_all = np.array([[r.get(c, np.nan) for c in all_cols] for r in rows], dtype=float)

    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    per_stat_fold_metrics: dict = {s: [] for s in STATS}

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

        X_tr = X_all[:tr_end].copy()
        X_val = X_all[tr_end:va_end].copy()
        X_ho = X_all[va_end:te_end].copy()

        X_tr, X_val, X_ho = _impute_fold(X_tr, X_val, X_ho, base_n_cols)

        if null_shuffle and extra_cols:
            rng = np.random.default_rng(null_seed)
            for col_i in range(base_n_cols, X_all.shape[1]):
                combined = np.concatenate([X_tr[:, col_i], X_val[:, col_i], X_ho[:, col_i]])
                rng.shuffle(combined)
                X_tr[:, col_i] = combined[:tr_end]
                X_val[:, col_i] = combined[tr_end:tr_end + (va_end - tr_end)]
                X_ho[:, col_i] = combined[tr_end + (va_end - tr_end):]

        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        if extra_cols and not null_shuffle:
            ho_rows = rows[va_end:te_end]
            cov = np.mean([1 if not np.isnan(r.get(extra_cols[0], np.nan)) else 0 for r in ho_rows])
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)
        else:
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end}", flush=True)

        t0 = time.time()
        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat_no_mlp(stat, X_tr, y[:tr_end],
                                         X_val, y[tr_end:va_end],
                                         X_ho, y[va_end:te_end], sw,
                                         xgb_device=_XGB_DEVICE)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} 2way={res['two_way']['mae']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    print(f"\n=== SUMMARY [{mode_label}] (NO-MLP) ===")
    summary: dict = {
        "mode": mode_label,
        "signal_groups": signal_groups or [],
        "null_shuffle": null_shuffle,
        "architecture": "XGB+LGB_2way_no_mlp",
        "folds_per_stat": per_stat_fold_metrics,
        "by_stat": {},
    }
    for stat in STATS:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        mae2 = [f["two_way"]["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_2way_mean": float(np.mean(mae2)),
            "mae_2way_std": float(np.std(mae2)),
            "per_fold_mae2": mae2,
        }
        print(f"  {stat.upper():4s} mae={np.mean(mae2):.4f}±{np.std(mae2):.4f}")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="INT-102: XGB+LGB only sidecar WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"],
                    default="all")
    ap.add_argument("--signal", choices=list(SIGNAL_COLS.keys()), default="ft_rate")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-102] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, signal_groups=None,
                                           mode_label="baseline_no_mlp")

    if args.mode in ("isolation", "all"):
        results["isolation_ft_rate"] = walk_forward(
            args.splits, signal_groups=["ft_rate"],
            mode_label="isolation_ft_rate_no_mlp")

    if args.mode in ("null", "all"):
        results["null_ft_rate"] = walk_forward(
            args.splits, signal_groups=["ft_rate"],
            null_shuffle=True, null_seed=0,
            mode_label="null_ft_rate_no_mlp")

    # ---------------------------------------------------------------------------
    # Kill switch: 2-way baseline vs 3-way (INT-94) baseline divergence check
    # ---------------------------------------------------------------------------
    int94_json = os.path.join(PROJECT_DIR, "data", "models",
                              "prop_pergame_walk_forward_built.json")
    kill_switch_fired = False
    if os.path.exists(int94_json):
        with open(int94_json) as f:
            int94 = json.load(f)
        int94_base = int94.get("baseline", {}).get("by_stat", {})
        print("\n=== KILL SWITCH CHECK: 2-way baseline vs INT-94 3-way baseline ===")
        max_div = 0.0
        for stat in ["pts", "reb", "ast", "fg3m"]:
            if stat not in int94_base:
                continue
            int94_mae = int94_base[stat].get("mae_3way_mean", float("nan"))
            no_mlp_mae = results.get("baseline_no_mlp", results.get("baseline", {})).get(
                "by_stat", {}).get(stat, {}).get("mae_2way_mean", float("nan"))
            if "baseline" in results:
                no_mlp_mae = results["baseline"]["by_stat"].get(stat, {}).get("mae_2way_mean", float("nan"))
            div = abs(no_mlp_mae - int94_mae)
            max_div = max(max_div, div)
            flag = "WARN" if div > 0.005 else "OK"
            print(f"  {stat.upper():4s}: INT-94_3way={int94_mae:.4f} no-mlp_2way={no_mlp_mae:.4f} "
                  f"div={div:.4f} [{flag}]")
        if max_div > 0.005:
            print(f"\n  [KILL SWITCH] max divergence {max_div:.4f} > 0.005 — HALTING augmentation eval")
            kill_switch_fired = True
        else:
            print(f"\n  [OK] max divergence {max_div:.4f} <= 0.005 — proceeding")

    # ---------------------------------------------------------------------------
    # G2 isolation delta table
    # ---------------------------------------------------------------------------
    print("\n=== G2 ISOLATION DELTAS (2-way aug vs 2-way baseline) ===")
    g2_pass = False
    g2_detail: dict = {}
    if "baseline" in results and "isolation_ft_rate" in results:
        base_by_stat = results["baseline"]["by_stat"]
        aug_by_stat = results["isolation_ft_rate"]["by_stat"]
        core_stats = ["pts", "reb", "ast", "fg3m"]
        for stat in STATS:
            if stat not in base_by_stat or stat not in aug_by_stat:
                continue
            base_folds = base_by_stat[stat].get("per_fold_mae2", [])
            aug_folds = aug_by_stat[stat].get("per_fold_mae2", [])
            per_fold_d = [a - b for a, b in zip(aug_folds, base_folds)]
            n_neg = sum(1 for d in per_fold_d if d < 0)
            mean_d = float(np.mean(per_fold_d)) if per_fold_d else float("nan")
            g2_detail[stat] = {"per_fold_delta": per_fold_d, "n_neg": n_neg, "mean_delta": mean_d}
            fold_str = "  ".join(f"F{i+1}:{d:+.4f}" for i, d in enumerate(per_fold_d))
            print(f"  {stat.upper():4s}: {fold_str}  neg={n_neg}/4  mean={mean_d:+.4f}")
            if stat in core_stats and n_neg >= 3:
                g2_pass = True
    print(f"\n  G2 result: {'PASS' if g2_pass else 'FAIL'} (>=3/4 neg on >=1 core stat)")

    # ---------------------------------------------------------------------------
    # G3 null control
    # ---------------------------------------------------------------------------
    print("\n=== G3 NULL CONTROL ===")
    g3_pass = False
    g3_detail: dict = {}
    if "baseline" in results and "isolation_ft_rate" in results and "null_ft_rate" in results:
        base_by_stat = results["baseline"]["by_stat"]
        aug_by_stat = results["isolation_ft_rate"]["by_stat"]
        null_by_stat = results["null_ft_rate"]["by_stat"]
        for stat in STATS:
            if stat not in base_by_stat or stat not in aug_by_stat or stat not in null_by_stat:
                continue
            real_delta = aug_by_stat[stat]["mae_2way_mean"] - base_by_stat[stat]["mae_2way_mean"]
            null_delta = null_by_stat[stat]["mae_2way_mean"] - base_by_stat[stat]["mae_2way_mean"]
            # ratio: |real| / |null| — want real improvement / null noise >= 1.5
            if abs(null_delta) > 1e-6 and real_delta < 0 and null_delta >= 0:
                ratio = abs(real_delta) / abs(null_delta)
            elif abs(null_delta) > 1e-6:
                ratio = abs(real_delta) / abs(null_delta)
            else:
                ratio = float("inf") if real_delta < 0 else 0.0
            g3_detail[stat] = {"real_delta": real_delta, "null_delta": null_delta, "ratio": ratio}
            print(f"  {stat.upper():4s}: real={real_delta:+.4f}  null={null_delta:+.4f}  ratio={ratio:.2f}")
        # G3 passes if mean ratio across core stats >= 1.5
        core = ["pts", "reb", "ast", "fg3m"]
        core_ratios = [g3_detail[s]["ratio"] for s in core if s in g3_detail]
        mean_ratio = float(np.mean(core_ratios)) if core_ratios else 0.0
        g3_pass = mean_ratio >= 1.5
        print(f"\n  G3 mean_ratio={mean_ratio:.2f} — {'PASS' if g3_pass else 'FAIL'} (need >=1.5)")

    # ---------------------------------------------------------------------------
    # G5 regression check (STL/BLK/TOV)
    # ---------------------------------------------------------------------------
    print("\n=== G5 NO-REGRESSION (STL/BLK/TOV) ===")
    g5_pass = True
    if "baseline" in results and "isolation_ft_rate" in results:
        for stat in ["stl", "blk", "tov"]:
            if stat not in results["baseline"]["by_stat"]:
                continue
            b = results["baseline"]["by_stat"][stat]["mae_2way_mean"]
            a = results["isolation_ft_rate"]["by_stat"].get(stat, {}).get("mae_2way_mean", b)
            delta = a - b
            flag = "FAIL" if delta > 0.003 else "OK"
            if delta > 0.003:
                g5_pass = False
            print(f"  {stat.upper():3s}: base={b:.4f} aug={a:.4f} delta={delta:+.4f} [{flag}]")
    print(f"\n  G5 result: {'PASS' if g5_pass else 'FAIL'} (no >0.003 regression)")

    # ---------------------------------------------------------------------------
    # Overall verdict
    # ---------------------------------------------------------------------------
    print("\n=== GATE SCOREBOARD ===")
    print(f"  G1 (coverage >=10%):     PRE-PASS (INT-94 verified 91% fold-4)")
    print(f"  G2 (isolation WF):       {'PASS' if g2_pass else 'FAIL'}")
    print(f"  G3 (null control >=1.5): {'PASS' if g3_pass else 'FAIL'}")
    print(f"  G4 (orthogonality):      PRE-PASS (INT-94 |r|<0.9 verified)")
    print(f"  G5 (no regression):      {'PASS' if g5_pass else 'FAIL'}")
    gates_passed = sum([True, g2_pass, g3_pass, True, g5_pass])
    verdict = "SHIP" if (g2_pass and g3_pass and g5_pass and not kill_switch_fired) else "REJECT"
    print(f"\n  VERDICT: {verdict}  ({gates_passed}/5 gates)")

    # ---------------------------------------------------------------------------
    # Save results
    # ---------------------------------------------------------------------------
    out = {
        "int_id": "INT-102",
        "description": "INT-83 ft_rate sidecar — XGB+LGB only (no MLP)",
        "kill_switch_fired": kill_switch_fired,
        "g2_pass": g2_pass,
        "g3_pass": g3_pass,
        "g5_pass": g5_pass,
        "verdict": verdict,
        "g2_detail": g2_detail,
        "g3_detail": g3_detail,
        "results": results,
    }
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_built_no_mlp.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return out


if __name__ == "__main__":
    main()
