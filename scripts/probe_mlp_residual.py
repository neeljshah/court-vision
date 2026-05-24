"""probe_mlp_residual.py — MLP architecture experiment for PTS.

Tests two structural changes to the 3-way stack vs the current cycle-18
baseline (XGB+LGB+independent-MLP NNLS-blended). All on PTS only, the
highest-volume / highest-leverage stat:

  baseline:   independent MLP predicts sqrt(y) — current production
  residual:   MLP predicts sqrt(y) - mean(XGB, LGB) — corrects what trees miss
  augmented:  MLP sees [X, xgb_pred, lgb_pred] as features, predicts sqrt(y)

Compares per-fold MAE / R² on 4-fold walk-forward.
"""
from __future__ import annotations

import os
import sys
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    build_pergame_dataset, feature_columns, _MLPSeedEnsemble,
)
import xgboost as xgb
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score


def _trees(X_tr, yt_tr, X_val, yt_val, sw):
    xgb_m = xgb.XGBRegressor(
        n_estimators=800, max_depth=6, learning_rate=0.025,
        subsample=0.8, colsample_bytree=0.9,
        min_child_weight=20, reg_lambda=4.0, reg_alpha=2.0, gamma=0.2,
        random_state=42, objective="reg:pseudohubererror",
        eval_metric="mae", early_stopping_rounds=40,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=800, max_depth=6, learning_rate=0.025,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.9,
        min_child_samples=40, reg_lambda=4.0, reg_alpha=2.0,
        random_state=42, objective="huber", n_jobs=-1, verbosity=-1,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
         callbacks=[lgb.early_stopping(40, verbose=False)])
    return xgb_m, lgb_m


def main():
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    dates_all = [datetime.fromisoformat(r["date"]) for r in rows]
    y = np.array([r["target_pts"] for r in rows], dtype=float)
    print(f"n={n} features={len(fc)}", flush=True)

    fold_ends = [(i + 1) / 5 for i in range(4)]
    out = {m: {"mae": [], "r2": []} for m in ["baseline", "residual", "augmented"]}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000:
            continue
        age = np.array([(max(dates_all[:tr_end]) - d).days / 365.0 for d in dates_all[:tr_end]])
        sw = np.exp(-0.5 * age)
        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
        y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]
        yt_tr, yt_val = np.sqrt(y_tr), np.sqrt(y_val)

        # Trees on sqrt target (same for all 3 modes)
        xgb_m, lgb_m = _trees(X_tr, yt_tr, X_val, yt_val, sw)
        xgb_tr = xgb_m.predict(X_tr); lgb_tr = lgb_m.predict(X_tr)
        xgb_val = xgb_m.predict(X_val); lgb_val = lgb_m.predict(X_val)
        xgb_ho = xgb_m.predict(X_ho);   lgb_ho = lgb_m.predict(X_ho)
        tree_avg_tr  = (xgb_tr + lgb_tr) / 2
        tree_avg_val = (xgb_val + lgb_val) / 2
        tree_avg_ho  = (xgb_ho + lgb_ho) / 2

        # --- MODE: baseline (independent MLP on sqrt y) ---
        sc = StandardScaler()
        Xts = sc.fit_transform(X_tr); Xvs = sc.transform(X_val); Xhs = sc.transform(X_ho)
        mlp_base = _MLPSeedEnsemble().fit(Xts, yt_tr)
        mv = mlp_base.predict(Xvs); mh = mlp_base.predict(Xhs)
        # 3-way NNLS on sqrt -> invert
        st = LinearRegression(positive=True, fit_intercept=False).fit(
            np.column_stack([xgb_val, lgb_val, mv]), np.sqrt(y_val))
        w = st.coef_
        if not (0.5 <= w.sum() <= 1.5):
            w = np.array([1/3, 1/3, 1/3])
        blend = np.clip(w[0]*xgb_ho + w[1]*lgb_ho + w[2]*mh, 0.0, None) ** 2
        out["baseline"]["mae"].append(mean_absolute_error(y_ho, blend))
        out["baseline"]["r2"].append(r2_score(y_ho, blend))

        # --- MODE: residual MLP (predicts sqrt(y) - tree_avg) ---
        residual_tr = yt_tr - tree_avg_tr
        mlp_res = _MLPSeedEnsemble().fit(Xts, residual_tr)
        # Inference: tree_avg + mlp_residual
        mv_res = mlp_res.predict(Xvs); mh_res = mlp_res.predict(Xhs)
        # NNLS over [tree_avg, mlp_residual_corrected]
        # Two-way: tree-avg + alpha * mlp_residual; let NNLS fit alpha
        st_r = LinearRegression(positive=True, fit_intercept=False).fit(
            np.column_stack([tree_avg_val, mv_res]), np.sqrt(y_val))
        wr = st_r.coef_
        # Allow alpha outside [0.5,1.5] for residuals (can be 0..1)
        blend_r = np.clip(wr[0]*tree_avg_ho + wr[1]*mh_res, 0.0, None) ** 2
        out["residual"]["mae"].append(mean_absolute_error(y_ho, blend_r))
        out["residual"]["r2"].append(r2_score(y_ho, blend_r))

        # --- MODE: input-augmented (MLP sees X + xgb_pred + lgb_pred) ---
        X_tr_aug  = np.column_stack([X_tr,  xgb_tr,  lgb_tr])
        X_val_aug = np.column_stack([X_val, xgb_val, lgb_val])
        X_ho_aug  = np.column_stack([X_ho,  xgb_ho,  lgb_ho])
        sc_a = StandardScaler()
        Xts_a = sc_a.fit_transform(X_tr_aug); Xvs_a = sc_a.transform(X_val_aug); Xhs_a = sc_a.transform(X_ho_aug)
        mlp_aug = _MLPSeedEnsemble().fit(Xts_a, yt_tr)
        mv_a = mlp_aug.predict(Xvs_a); mh_a = mlp_aug.predict(Xhs_a)
        # 3-way NNLS same as baseline
        st_a = LinearRegression(positive=True, fit_intercept=False).fit(
            np.column_stack([xgb_val, lgb_val, mv_a]), np.sqrt(y_val))
        wa = st_a.coef_
        if not (0.5 <= wa.sum() <= 1.5):
            wa = np.array([1/3, 1/3, 1/3])
        blend_a = np.clip(wa[0]*xgb_ho + wa[1]*lgb_ho + wa[2]*mh_a, 0.0, None) ** 2
        out["augmented"]["mae"].append(mean_absolute_error(y_ho, blend_a))
        out["augmented"]["r2"].append(r2_score(y_ho, blend_a))

        print(f"  fold {fi+1}: "
              f"base={out['baseline']['mae'][-1]:.4f}/{out['baseline']['r2'][-1]:.4f}  "
              f"res={out['residual']['mae'][-1]:.4f}/{out['residual']['r2'][-1]:.4f}  "
              f"aug={out['augmented']['mae'][-1]:.4f}/{out['augmented']['r2'][-1]:.4f}",
              flush=True)

    print()
    bmae = np.array(out["baseline"]["mae"]); br2 = np.array(out["baseline"]["r2"])
    for mode in ["residual", "augmented"]:
        dm = np.array(out[mode]["mae"]) - bmae
        dr = np.array(out[mode]["r2"]) - br2
        pf = " ".join(f"{x:+.4f}" for x in dm)
        print(f"  PTS {mode:9s}  d_mae={dm.mean():+.4f}+-{dm.std():.4f}  "
              f"d_r2={dr.mean():+.4f}+-{dr.std():.4f}  per-fold mae=[{pf}]")


if __name__ == "__main__":
    main()
