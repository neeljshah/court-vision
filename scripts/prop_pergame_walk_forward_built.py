"""prop_pergame_walk_forward_built.py — INT-94 walk-forward sidecar test.

Tests built intelligence signals (INT-83 ft_rate, INT-79 opp_minutes) as
additional features on top of the standard prop_pergame feature set.

Architecture mirrors prop_pergame_walk_forward.py (READ-ONLY template) but
augments X_all with sidecar columns.  NaN imputation uses per-fold training
medians only (no leakage).

Run:
    python scripts/prop_pergame_walk_forward_built.py --mode baseline
    python scripts/prop_pergame_walk_forward_built.py --mode isolation --signal ft_rate
    python scripts/prop_pergame_walk_forward_built.py --mode null --signal ft_rate
    python scripts/prop_pergame_walk_forward_built.py --mode joint
    python scripts/prop_pergame_walk_forward_built.py --mode all
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


# Module-level device (set by main(); defaults to cpu for imports)
_XGB_DEVICE: str = "cpu"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# Sidecar signal definitions
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence", "built_signals_sidecar.parquet")

# Which sidecar columns belong to each signal group
SIGNAL_COLS: Dict[str, List[str]] = {
    "ft_rate": ["ft_rate_q50", "ft_rate_spread", "ft_n_prior"],
    # INT-79 dropped: G1 coverage 3.51% < 10% threshold
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

    # Build lookup: (player_id, game_date) -> {col: val}
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
# Training helper — mirrors prop_pergame_walk_forward.py exactly
# ---------------------------------------------------------------------------
def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB + MLP for one stat; return 2-way and 3-way holdout metrics."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
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

    sc = StandardScaler()
    X_tr_s = sc.fit_transform(X_tr)
    X_val_s = sc.transform(X_val)
    X_ho_s = sc.transform(X_ho)

    from src.prediction.prop_pergame import _MLPSeedEnsemble  # noqa: PLC0415
    mlp_m = _MLPSeedEnsemble().fit(X_tr_s, y_tr)

    xv, lv, mv = xgb_m.predict(X_val), lgb_m.predict(X_val), mlp_m.predict(X_val_s)
    xh, lh, mh = xgb_m.predict(X_ho), lgb_m.predict(X_ho), mlp_m.predict(X_ho_s)

    def _blend(preds, y_val_arr):
        st = LinearRegression(positive=True, fit_intercept=False)
        st.fit(np.column_stack(preds), y_val_arr)
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([1.0 / len(preds)] * len(preds))
        return w

    # 2-way
    w2 = _blend([xv, lv], y_val)
    b2 = w2[0] * xh + w2[1] * lh
    mae2 = float(mean_absolute_error(y_ho, b2))
    r2_2 = float(r2_score(y_ho, b2))

    # 3-way
    w3 = _blend([xv, lv, mv], y_val)
    b3 = w3[0] * xh + w3[1] * lh + w3[2] * mh
    mae3 = float(mean_absolute_error(y_ho, b3))
    r2_3 = float(r2_score(y_ho, b3))

    return {
        "two_way": {"mae": mae2, "r2": r2_2, "w": [float(x) for x in w2]},
        "three_way": {"mae": mae3, "r2": r2_3, "w": [float(x) for x in w3]},
    }


# ---------------------------------------------------------------------------
# Per-fold NaN imputation (training medians only — no leakage)
# ---------------------------------------------------------------------------
def _impute_fold(X_tr: np.ndarray, X_val: np.ndarray, X_ho: np.ndarray,
                 base_n_cols: int) -> tuple:
    """Fill NaN in sidecar columns using training-fold median only."""
    if X_tr.shape[1] == base_n_cols:
        return X_tr, X_val, X_ho  # no sidecar cols

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
# Walk-forward engine
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    signal_groups: List[str] | None = None,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  signals={signal_groups}  null={null_shuffle}")
    print(f"{'='*60}")

    print(f"Loading dataset (n_splits={n_splits}) ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    base_n_cols = len(fc)
    print(f"  rows={n}, base features={base_n_cols}")

    # Attach sidecar if requested
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

        # Per-fold imputation (training medians)
        X_tr, X_val, X_ho = _impute_fold(X_tr, X_val, X_ho, base_n_cols)

        # Null shuffle: shuffle the sidecar signal columns within the fold's training portion
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

        # Sidecar coverage in this fold's holdout
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
            res = _train_one_stat(stat, X_tr, y[:tr_end],
                                  X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            mae_d = res["three_way"]["mae"] - res["two_way"]["mae"]
            print(f"  {stat.upper():4s} 2way={res['two_way']['mae']:.4f} "
                  f"3way={res['three_way']['mae']:.4f} d_mae={mae_d:+.4f}",
                  flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    # Summarise
    print(f"\n=== SUMMARY [{mode_label}] ===")
    summary: dict = {
        "mode": mode_label,
        "signal_groups": signal_groups or [],
        "null_shuffle": null_shuffle,
        "folds_per_stat": per_stat_fold_metrics,
        "by_stat": {},
    }
    for stat in STATS:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        mae3 = [f["three_way"]["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_3way_mean": float(np.mean(mae3)),
            "mae_3way_std": float(np.std(mae3)),
            "per_fold_mae3": mae3,
        }
        print(f"  {stat.upper():4s} mae={np.mean(mae3):.4f}±{np.std(mae3):.4f}")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "joint", "all"],
                    default="all")
    ap.add_argument("--signal", choices=list(SIGNAL_COLS.keys()), default=None,
                    help="Signal group for isolation/null modes")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-94] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, signal_groups=None,
                                           mode_label="baseline")

    signals_to_test = list(SIGNAL_COLS.keys()) if args.mode == "all" else (
        [args.signal] if args.signal else list(SIGNAL_COLS.keys())
    )

    if args.mode in ("isolation", "all"):
        for sig in signals_to_test:
            results[f"isolation_{sig}"] = walk_forward(
                args.splits, signal_groups=[sig],
                mode_label=f"isolation_{sig}")

    if args.mode in ("null", "all"):
        for sig in signals_to_test:
            results[f"null_{sig}"] = walk_forward(
                args.splits, signal_groups=[sig],
                null_shuffle=True, null_seed=0,
                mode_label=f"null_{sig}")

    if args.mode in ("joint", "all") and len(SIGNAL_COLS) > 1:
        results["joint"] = walk_forward(
            args.splits, signal_groups=list(SIGNAL_COLS.keys()),
            mode_label="joint")
    elif args.mode == "joint" and len(SIGNAL_COLS) == 1:
        print("Only 1 signal in SIGNAL_COLS — joint == isolation. Skipping separate joint run.")

    # Delta computations vs baseline
    if "baseline" in results:
        base = results["baseline"]["by_stat"]
        print("\n=== DELTA vs BASELINE (3-way MAE) ===")
        for key, res in results.items():
            if key == "baseline":
                continue
            print(f"\n  [{key}]")
            for stat in STATS:
                if stat not in res.get("by_stat", {}):
                    continue
                b_mae = base.get(stat, {}).get("mae_3way_mean", np.nan)
                s_mae = res["by_stat"][stat]["mae_3way_mean"]
                delta = s_mae - b_mae
                sign = "-" if delta < 0 else "+"
                print(f"    {stat.upper():4s}: base={b_mae:.4f} → {s_mae:.4f} Δ={delta:+.4f}")

    # Save
    out_path = os.path.join(PROJECT_DIR, "data", "models", "prop_pergame_walk_forward_built.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return results


if __name__ == "__main__":
    main()
