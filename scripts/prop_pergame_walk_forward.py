"""prop_pergame_walk_forward.py — walk-forward check of the 3-way prop stack.

Each fold trains both the 2-way (XGB+LGB) and 3-way (+MLP) blends on the
same temporal slice and reports the delta per stat. Confirms whether the
cycle-5 single-split MLP gain is real or split-specific noise. Mirrors
winprob_walk_forward.py.

Run:
    python scripts/prop_pergame_walk_forward.py
    python scripts/prop_pergame_walk_forward.py --splits 4
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import List

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS, build_pergame_dataset, feature_columns,
)


def _train_one_stat(stat, X_tr, y_tr, X_val, y_val, X_ho, y_ho, sw):
    """Train XGB + LGB + MLP for one stat and return both 2-way and 3-way
    holdout metrics with NNLS-fit weights."""
    import xgboost as xgb
    import lightgbm as lgb
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, r2_score

    is_count = stat in ("stl", "blk")
    xgb_m = xgb.XGBRegressor(
        n_estimators=600, max_depth=3 if is_count else 4,
        learning_rate=0.04, subsample=0.8, colsample_bytree=0.8,
        min_child_weight=10, reg_lambda=2.0, reg_alpha=0.5, gamma=0.2,
        random_state=42,
        objective="count:poisson" if is_count else "reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
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
    X_tr_s, X_val_s, X_ho_s = sc.fit_transform(X_tr), sc.transform(X_val), sc.transform(X_ho)
    # Cycle 11: 5-seed ensemble — averages predictions across seeds {1,7,42,100,2024}.
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

    # 2-way (xgb+lgb)
    w2 = _blend([xv, lv], y_val)
    b2 = w2[0] * xh + w2[1] * lh
    mae2 = float(mean_absolute_error(y_ho, b2))
    r2_2 = float(r2_score(y_ho, b2))

    # 3-way (xgb+lgb+mlp)
    w3 = _blend([xv, lv, mv], y_val)
    b3 = w3[0] * xh + w3[1] * lh + w3[2] * mh
    mae3 = float(mean_absolute_error(y_ho, b3))
    r2_3 = float(r2_score(y_ho, b3))

    return {
        "two_way": {"mae": mae2, "r2": r2_2, "w": [float(x) for x in w2]},
        "three_way": {"mae": mae3, "r2": r2_3, "w": [float(x) for x in w3]},
    }


def walk_forward(n_splits: int = 4) -> dict:
    print(f"Loading dataset (n_splits={n_splits}) ...")
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    print(f"  rows={n}, features={len(fc)}")
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)

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
            print(f"  fold {fold_idx+1}: too small (tr={tr_end}, te={te_end-tr_end}) — skip")
            continue
        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
        tr_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(tr_end)]
        max_d = max(tr_dates)
        age = np.array([(max_d - d).days / 365.0 for d in tr_dates], dtype=float)
        sw = np.exp(-0.5 * age)

        print(f"\n[fold {fold_idx+1}/{n_splits}] tr={tr_end} val={va_end-tr_end} ho={te_end-va_end}",
              flush=True)
        t0 = time.time()
        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            res = _train_one_stat(stat, X_tr, y[:tr_end],
                                  X_val, y[tr_end:va_end],
                                  X_ho, y[va_end:te_end], sw)
            res["fold"] = fold_idx + 1
            per_stat_fold_metrics[stat].append(res)
            mae_d = res["three_way"]["mae"] - res["two_way"]["mae"]
            r2_d = res["three_way"]["r2"] - res["two_way"]["r2"]
            print(f"  {stat.upper():4s} 2way r2={res['two_way']['r2']:.4f} mae={res['two_way']['mae']:.4f}  "
                  f"3way r2={res['three_way']['r2']:.4f} mae={res['three_way']['mae']:.4f}  "
                  f"d_mae={mae_d:+.4f} d_r2={r2_d:+.4f}  w_mlp={res['three_way']['w'][2]:.2f}",
                  flush=True)
        print(f"  fold {fold_idx+1} wall: {time.time()-t0:.0f}s")

    # Summarise per stat
    print("\n=== WALK-FORWARD SUMMARY (mean +- std across folds) ===")
    print(" stat | 2way mae           | 3way mae           | d_mae           | 2way r2            | 3way r2            | d_r2")
    print("------+--------------------+--------------------+----------------+--------------------+--------------------+---------------")
    summary: dict = {"folds_per_stat": per_stat_fold_metrics, "by_stat": {}}
    for stat in STATS:
        folds = per_stat_fold_metrics[stat]
        if not folds:
            continue
        mae2 = [f["two_way"]["mae"] for f in folds]
        mae3 = [f["three_way"]["mae"] for f in folds]
        r2_2 = [f["two_way"]["r2"] for f in folds]
        r2_3 = [f["three_way"]["r2"] for f in folds]
        dmae = [a - b for a, b in zip(mae3, mae2)]
        dr2  = [a - b for a, b in zip(r2_3, r2_2)]
        summary["by_stat"][stat] = {
            "mae_2way_mean": float(np.mean(mae2)), "mae_2way_std": float(np.std(mae2)),
            "mae_3way_mean": float(np.mean(mae3)), "mae_3way_std": float(np.std(mae3)),
            "r2_2way_mean":  float(np.mean(r2_2)), "r2_3way_mean":  float(np.mean(r2_3)),
            "delta_mae_mean": float(np.mean(dmae)), "delta_mae_std": float(np.std(dmae)),
            "delta_r2_mean":  float(np.mean(dr2)),  "delta_r2_std":  float(np.std(dr2)),
        }
        s = summary["by_stat"][stat]
        print(f"  {stat.upper():4s} | {s['mae_2way_mean']:.4f}+-{s['mae_2way_std']:.4f} "
              f"| {s['mae_3way_mean']:.4f}+-{s['mae_3way_std']:.4f} "
              f"| {s['delta_mae_mean']:+.4f}+-{s['delta_mae_std']:.4f} "
              f"| {s['r2_2way_mean']:.4f}            "
              f"| {s['r2_3way_mean']:.4f}            "
              f"| {s['delta_r2_mean']:+.4f}+-{s['delta_r2_std']:.4f}")

    out_path = os.path.join(PROJECT_DIR, "data", "models", "prop_pergame_walk_forward.json")
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nWrote {out_path}")
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", type=int, default=4)
    args = ap.parse_args()
    walk_forward(args.splits)
