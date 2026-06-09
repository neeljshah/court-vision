"""prop_pergame_walk_forward_shot_types.py — INT-115 walk-forward sidecar test.

Tests CV shot-type features (catch_and_shoot, pull_up, drive_finish, step_back)
as sidecar features for prop_pergame predictions.

IMPORTANT: This script includes a G1 (coverage) kill switch. If fold-4 holdout
coverage < 10%, it will print a DEFER message and exit without running WF.

Architecture mirrors prop_pergame_walk_forward_built_no_mlp.py (XGB+LGB 2-way only).

Run:
    python scripts/prop_pergame_walk_forward_shot_types.py --mode all
    python scripts/prop_pergame_walk_forward_shot_types.py --mode baseline
    python scripts/prop_pergame_walk_forward_shot_types.py --mode isolation
    python scripts/prop_pergame_walk_forward_shot_types.py --mode null
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


# Module-level device (set by main())
_XGB_DEVICE: str = "cpu"

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)

# ---------------------------------------------------------------------------
# Sidecar signal definitions
# ---------------------------------------------------------------------------
SIDECAR_PATH = os.path.join(PROJECT_DIR, "data", "intelligence",
                             "cv_shot_type_features_sidecar.parquet")

SIGNAL_COLS: Dict[str, List[str]] = {
    "shot_types": [
        "shot_type_cs_rate_l5",
        "shot_type_pu_rate_l5",
        "shot_type_drive_rate_l5",
        "shot_type_sb_rate_l5",
        "shot_type_cs_rate_l10",
        "shot_type_pu_rate_l10",
        "shot_type_drive_rate_l10",
        "shot_type_sb_rate_l10",
    ],
}

# Restrict to FG3M, AST, PTS per INT-115 spec
RESTRICTED_STATS = ["fg3m", "ast", "pts"]

# G1 threshold
G1_COVERAGE_THRESHOLD = 0.10


def _load_sidecar() -> pd.DataFrame:
    """Load the sidecar parquet keyed on (player_id, game_date)."""
    df = pd.read_parquet(SIDECAR_PATH)
    df["player_id"] = df["player_id"].astype(int)
    df["game_date"] = df["game_date"].astype(str).str[:10]
    return df


def _attach_sidecar(rows: list, sidecar: pd.DataFrame,
                    signal_groups: List[str]) -> tuple:
    """Attach sidecar columns to rows."""
    extra_cols = []
    for g in signal_groups:
        extra_cols.extend(SIGNAL_COLS[g])

    subset_cols = [c for c in extra_cols if c in sidecar.columns]
    lookup: Dict[tuple, Dict[str, float]] = {}
    for _, row in sidecar[["player_id", "game_date"] + subset_cols].iterrows():
        key = (int(row["player_id"]), str(row["game_date"])[:10])
        lookup[key] = {c: row[c] for c in subset_cols}

    augmented = []
    for r in rows:
        nr = dict(r)
        key = (int(r["player_id"]), str(r["date"])[:10])
        vals = lookup.get(key, {})
        for c in extra_cols:
            nr[c] = vals.get(c, np.nan)
        augmented.append(nr)

    return augmented, extra_cols


def _check_g1_coverage(rows: list, extra_cols: list, fold_idx: int,
                        n_splits: int, n: int) -> float:
    """Compute G1 coverage for fold holdout."""
    fold_ends = [(i + 1) / (n_splits + 1) for i in range(n_splits)]
    tr_end = int(n * fold_ends[fold_idx])
    te_end = n if fold_idx == n_splits - 1 else int(n * fold_ends[fold_idx + 1])
    va_end = int(tr_end + (te_end - tr_end) * 0.4)
    ho_rows = rows[va_end:te_end]
    if not ho_rows or not extra_cols:
        return 0.0
    first_col = extra_cols[0]
    cov = np.mean([0 if np.isnan(float(r.get(first_col, np.nan) or np.nan)) else 1
                   for r in ho_rows])
    return float(cov)


# ---------------------------------------------------------------------------
# Training helper — XGB + LGB ONLY (mirrors INT-102)
# ---------------------------------------------------------------------------
def _train_one_stat_no_mlp(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
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
    return {"two_way": {"mae": mae2, "r2": r2_2, "w": [float(x) for x in w2]}}


def _impute_fold(X_tr, X_val, X_ho, base_n_cols):
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
# Walk-forward engine
# ---------------------------------------------------------------------------
def walk_forward(
    n_splits: int = 4,
    signal_groups: List[str] | None = None,
    null_shuffle: bool = False,
    null_seed: int = 0,
    mode_label: str = "baseline",
    stats_to_test: List[str] | None = None,
) -> dict:
    print(f"\n{'='*60}")
    print(f"MODE: {mode_label}  signals={signal_groups}  null={null_shuffle}  [INT-115]")
    print(f"{'='*60}")

    active_stats = stats_to_test or RESTRICTED_STATS

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
    per_stat_fold_metrics: dict = {s: [] for s in active_stats}

    for fold_idx, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        if fold_idx == n_splits - 1:
            te_end = n
        else:
            te_end = int(n * fold_ends[fold_idx + 1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000 or (te_end - va_end) < 2000:
            print(f"  fold {fold_idx+1}: too small -- skip")
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
            ho_rows_sub = rows[va_end:te_end]
            cov = np.mean([1 if not np.isnan(r.get(extra_cols[0], np.nan)) else 0
                           for r in ho_rows_sub])
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end} sidecar_cov={cov:.3f}", flush=True)

            # G1 kill switch on fold 4
            if fold_idx == n_splits - 1 and cov < G1_COVERAGE_THRESHOLD and not null_shuffle:
                print(f"\n[KILL SWITCH G1] Fold {fold_idx+1} sidecar coverage "
                      f"{cov:.3f} < {G1_COVERAGE_THRESHOLD} -- DEFER")
                return {
                    "mode": mode_label, "status": "DEFER",
                    "reason": f"G1 fold-{fold_idx+1} coverage={cov:.4f} < {G1_COVERAGE_THRESHOLD}",
                    "signal_groups": signal_groups or [],
                }
        else:
            print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} "
                  f"ho={te_end-va_end}", flush=True)

        t0 = time.time()
        for stat in active_stats:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat_no_mlp(stat, X_tr, y[:tr_end],
                                          X_val, y[tr_end:va_end],
                                          X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            print(f"  {stat.upper():4s} 2way={res['two_way']['mae']:.4f}", flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    print(f"\n=== SUMMARY [{mode_label}] (INT-115) ===")
    summary: dict = {
        "mode": mode_label,
        "signal_groups": signal_groups or [],
        "null_shuffle": null_shuffle,
        "architecture": "XGB+LGB_2way_no_mlp",
        "folds_per_stat": per_stat_fold_metrics,
        "by_stat": {},
    }
    for stat in active_stats:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        mae2 = [f["two_way"]["mae"] for f in folds]
        summary["by_stat"][stat] = {
            "mae_2way_mean": float(np.mean(mae2)),
            "mae_2way_std": float(np.std(mae2)),
            "per_fold_mae2": mae2,
        }
        print(f"  {stat.upper():4s} mae={np.mean(mae2):.4f}+/-{np.std(mae2):.4f}")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="INT-115: CV shot-type sidecar WF test")
    ap.add_argument("--splits", type=int, default=4)
    ap.add_argument("--mode", choices=["baseline", "isolation", "null", "all"],
                    default="all")
    ap.add_argument("--stats", nargs="+", default=RESTRICTED_STATS,
                    help="Stats to test (default: fg3m ast pts)")
    ap.add_argument("--device", default="auto",
                    help="XGB device: 'cuda', 'cpu', or 'auto' (default: auto-detect)")
    args = ap.parse_args()

    global _XGB_DEVICE
    _XGB_DEVICE = _resolve_device(args.device)
    print(f"[INT-115] XGB device: {_XGB_DEVICE}")

    results: Dict[str, Any] = {}

    if args.mode in ("baseline", "all"):
        results["baseline"] = walk_forward(args.splits, signal_groups=None,
                                           mode_label="baseline_int115",
                                           stats_to_test=args.stats)

    if args.mode in ("isolation", "all"):
        results["isolation_shot_types"] = walk_forward(
            args.splits, signal_groups=["shot_types"],
            mode_label="isolation_shot_types",
            stats_to_test=args.stats)
        if results["isolation_shot_types"].get("status") == "DEFER":
            print("\n[INT-115] G1 kill switch fired. Skipping null + comparison.")
            _save_results(results, args.mode)
            return

    if args.mode in ("null", "all"):
        results["null_shot_types"] = walk_forward(
            args.splits, signal_groups=["shot_types"],
            null_shuffle=True, null_seed=0,
            mode_label="null_shot_types",
            stats_to_test=args.stats)

    _save_results(results, args.mode)


def _save_results(results: dict, mode: str):
    out_path = os.path.join(PROJECT_DIR, "data", "models",
                            "prop_pergame_walk_forward_shot_types.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {out_path}")

    # Summary table
    print("\n=== INT-115 GATE SUMMARY ===")
    base = results.get("baseline", {}).get("by_stat", {})
    aug  = results.get("isolation_shot_types", {}).get("by_stat", {})

    for stat in ["fg3m", "ast", "pts"]:
        if stat in base and stat in aug:
            delta = aug[stat]["mae_2way_mean"] - base[stat]["mae_2way_mean"]
            pct = 100 * delta / base[stat]["mae_2way_mean"]
            print(f"  {stat.upper():4s} base={base[stat]['mae_2way_mean']:.4f} "
                  f"aug={aug[stat]['mae_2way_mean']:.4f} delta={delta:+.4f} ({pct:+.2f}%)")


if __name__ == "__main__":
    main()
