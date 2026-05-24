"""probe_multitask_mlp.py — multitask MLP vs independent per-stat MLPs.

Builds the 7-stat target matrix (with per-stat transform applied) and trains
a SINGLE 5-seed multi-output MLPRegressor on all stats jointly. Compares
per-stat WF MAE / R² to the current per-stat-independent baseline.

Ships per-stat where multitask wins both gates (4/4 WF folds + production
single-split MAE strictly down).
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
    build_pergame_dataset, feature_columns, STATS,
    _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS, _MLP_SEEDS,
)
import xgboost as xgb
import lightgbm as lgb
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score


class _IndependentMLPEnsemble:
    """5-seed MLP per stat — mirrors production _MLPSeedEnsemble for one target."""

    def __init__(self):
        self.models = [
            MLPRegressor(
                hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                learning_rate_init=1e-3, alpha=1e-4, batch_size=512,
                max_iter=80, random_state=int(s), early_stopping=True,
                validation_fraction=0.15, n_iter_no_change=10,
            )
            for s in _MLP_SEEDS
        ]

    def fit(self, X, y):
        for m in self.models:
            m.fit(X, y)
        return self

    def predict(self, X):
        return np.mean([m.predict(X) for m in self.models], axis=0)


class _MultitaskMLPEnsemble:
    """5-seed multi-output MLP — sklearn handles y as (n_samples, n_targets)."""

    def __init__(self, n_outputs):
        self.n_outputs = n_outputs
        self.models = [
            MLPRegressor(
                hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
                learning_rate_init=1e-3, alpha=1e-4, batch_size=512,
                max_iter=80, random_state=int(s), early_stopping=True,
                validation_fraction=0.15, n_iter_no_change=10,
            )
            for s in _MLP_SEEDS
        ]

    def fit(self, X, Y):
        # Y shape: (n_samples, n_outputs)
        for m in self.models:
            m.fit(X, Y)
        return self

    def predict(self, X):
        # Returns (n_samples, n_outputs)
        return np.mean([m.predict(X) for m in self.models], axis=0)


def _transform(stat, y):
    """Apply per-stat target transform."""
    if stat in _SQRT_HUBER_STATS:
        return np.sqrt(y)
    if stat in _LOG_TRANSFORM_STATS:
        return np.log1p(y)
    return y


def _inverse(stat, v):
    """Invert per-stat target transform with non-negative clip."""
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _trees(stat, X_tr, yt_tr, X_val, yt_val, sw):
    """Same tree training as production prop_pergame.train_pergame_models."""
    use_log = stat in _LOG_TRANSFORM_STATS
    use_sqrt = stat in _SQRT_HUBER_STATS
    is_count = stat in ("stl", "blk")
    if use_sqrt:
        xgb_obj, lgb_obj = "reg:pseudohubererror", "huber"
    elif use_log:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    elif is_count:
        xgb_obj, lgb_obj = "count:poisson", "poisson"
    else:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    # Use production-ish HPs per stat (matches _STAT_PARAMS).
    p = {
        "pts":  dict(md=6, lr=0.025, mcw=20, rl=4.0, ra=2.0, g=0.2, ne=800, ss=0.8, cs=0.9),
        "reb":  dict(md=3, lr=0.025, mcw=30, rl=4.0, ra=0.5, g=0.3, ne=800, ss=0.7, cs=0.9),
        "ast":  dict(md=5, lr=0.025, mcw=20, rl=5.0, ra=0.5, g=0.2, ne=800, ss=0.7, cs=0.8),
        "fg3m": dict(md=4, lr=0.025, mcw=15, rl=8.0, ra=0.5, g=0.0, ne=600, ss=0.7, cs=0.8),
        "stl":  dict(md=2, lr=0.06,  mcw=40, rl=6.0, ra=0.25,g=0.6, ne=400, ss=0.9, cs=0.8),
        "blk":  dict(md=3, lr=0.06,  mcw=25, rl=4.0, ra=0.5, g=0.4, ne=800, ss=0.8, cs=1.0),
        "tov":  dict(md=3, lr=0.025, mcw=30, rl=6.0, ra=0.5, g=0.4, ne=700, ss=0.8, cs=0.8),
    }[stat]
    xgb_m = xgb.XGBRegressor(
        n_estimators=p["ne"], max_depth=p["md"], learning_rate=p["lr"],
        subsample=p["ss"], colsample_bytree=p["cs"],
        min_child_weight=p["mcw"], reg_lambda=p["rl"], reg_alpha=p["ra"],
        gamma=p["g"], random_state=42, objective=xgb_obj,
        eval_metric="mae", early_stopping_rounds=40,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    lgb_m = lgb.LGBMRegressor(
        n_estimators=p["ne"], max_depth=p["md"], learning_rate=p["lr"],
        subsample=p["ss"], subsample_freq=1, colsample_bytree=p["cs"],
        min_child_samples=max(20, p["mcw"]*2), reg_lambda=p["rl"], reg_alpha=p["ra"],
        random_state=42, objective=lgb_obj, n_jobs=-1, verbosity=-1,
    ).fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
         callbacks=[lgb.early_stopping(40, verbose=False)])
    return xgb_m, lgb_m


def main():
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    dates_all = [datetime.fromisoformat(r["date"]) for r in rows]
    Y_all_raw = {s: np.array([r[f"target_{s}"] for r in rows], dtype=float) for s in STATS}
    print(f"n={n} features={len(fc)}", flush=True)

    fold_ends = [(i + 1) / 5 for i in range(4)]
    # Per-stat per-fold MAE/R² for INDEPENDENT-MLP (baseline) and MULTITASK-MLP
    out = {s: {"indep_mae": [], "indep_r2": [], "multi_mae": [], "multi_r2": []} for s in STATS}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000:
            continue
        age = np.array([(max(dates_all[:tr_end]) - d).days / 365.0 for d in dates_all[:tr_end]])
        sw = np.exp(-0.5 * age)
        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
        sc = StandardScaler()
        Xts = sc.fit_transform(X_tr); Xvs = sc.transform(X_val); Xhs = sc.transform(X_ho)

        # Build 7-column transformed target matrix for multitask training
        Y_tr_t = np.column_stack([
            _transform(s, Y_all_raw[s][:tr_end]) for s in STATS
        ])
        # Train ONE multitask 5-seed MLP ensemble for all stats jointly
        mt = _MultitaskMLPEnsemble(n_outputs=len(STATS))
        mt.fit(Xts, Y_tr_t)
        mt_val_preds = mt.predict(Xvs)   # (n_val, 7)
        mt_ho_preds  = mt.predict(Xhs)   # (n_ho, 7)

        for si, stat in enumerate(STATS):
            y_tr = Y_all_raw[stat][:tr_end]
            y_val = Y_all_raw[stat][tr_end:va_end]
            y_ho = Y_all_raw[stat][va_end:te_end]
            yt_tr = _transform(stat, y_tr)
            yt_val = _transform(stat, y_val)

            # Trees (same for both modes)
            xgb_m, lgb_m = _trees(stat, X_tr, yt_tr, X_val, yt_val, sw)
            xgb_val_t = xgb_m.predict(X_val); lgb_val_t = lgb_m.predict(X_val)
            xgb_ho_t  = xgb_m.predict(X_ho);  lgb_ho_t  = lgb_m.predict(X_ho)
            xgb_val = _inverse(stat, xgb_val_t); lgb_val = _inverse(stat, lgb_val_t)
            xgb_ho  = _inverse(stat, xgb_ho_t);  lgb_ho  = _inverse(stat, lgb_ho_t)

            # INDEP MODE: single-stat MLP ensemble (production baseline)
            indep_mlp = _IndependentMLPEnsemble().fit(Xts, yt_tr)
            mv_t = indep_mlp.predict(Xvs); mh_t = indep_mlp.predict(Xhs)
            mv = _inverse(stat, mv_t); mh = _inverse(stat, mh_t)
            st = LinearRegression(positive=True, fit_intercept=False).fit(
                np.column_stack([xgb_val, lgb_val, mv]), y_val)
            w = st.coef_
            if not (0.5 <= w.sum() <= 1.5):
                w = np.array([1/3, 1/3, 1/3])
            blend = np.clip(w[0]*xgb_ho + w[1]*lgb_ho + w[2]*mh, 0.0, None)
            out[stat]["indep_mae"].append(mean_absolute_error(y_ho, blend))
            out[stat]["indep_r2"].append(r2_score(y_ho, blend))

            # MULTI MODE: extract this stat's column from multitask output
            mv_mt_t = mt_val_preds[:, si]; mh_mt_t = mt_ho_preds[:, si]
            mv_mt = _inverse(stat, mv_mt_t); mh_mt = _inverse(stat, mh_mt_t)
            st_mt = LinearRegression(positive=True, fit_intercept=False).fit(
                np.column_stack([xgb_val, lgb_val, mv_mt]), y_val)
            w_mt = st_mt.coef_
            if not (0.5 <= w_mt.sum() <= 1.5):
                w_mt = np.array([1/3, 1/3, 1/3])
            blend_mt = np.clip(w_mt[0]*xgb_ho + w_mt[1]*lgb_ho + w_mt[2]*mh_mt, 0.0, None)
            out[stat]["multi_mae"].append(mean_absolute_error(y_ho, blend_mt))
            out[stat]["multi_r2"].append(r2_score(y_ho, blend_mt))

            d_mae = blend_mt.mean() - blend.mean()  # not used — just see error
            print(f"  fold {fi+1} {stat.upper():4s}: indep mae={out[stat]['indep_mae'][-1]:.4f} r2={out[stat]['indep_r2'][-1]:.4f}  "
                  f"multi mae={out[stat]['multi_mae'][-1]:.4f} r2={out[stat]['multi_r2'][-1]:.4f}  "
                  f"d_mae={out[stat]['multi_mae'][-1]-out[stat]['indep_mae'][-1]:+.4f}  "
                  f"d_r2={out[stat]['multi_r2'][-1]-out[stat]['indep_r2'][-1]:+.4f}", flush=True)

    print()
    print("== PER-STAT MULTITASK vs INDEPENDENT (4-fold WF) ==")
    for stat in STATS:
        dm = np.array(out[stat]["multi_mae"]) - np.array(out[stat]["indep_mae"])
        dr = np.array(out[stat]["multi_r2"]) - np.array(out[stat]["indep_r2"])
        pf = " ".join(f"{x:+.4f}" for x in dm)
        n_pos = int((dm < 0).sum())
        print(f"  {stat.upper():4s} d_mae={dm.mean():+.4f}+-{dm.std():.4f}  d_r2={dr.mean():+.4f}+-{dr.std():.4f}  "
              f"folds_negative={n_pos}/4  per-fold mae=[{pf}]")


if __name__ == "__main__":
    main()
