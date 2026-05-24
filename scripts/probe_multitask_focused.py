"""probe_multitask_focused.py — focused multitask MLP variants.

Cycle 23 shipped a 7-output multitask MLP and ship-gated AST + STL (only
4/4 WF folds positive). This probe tests two refinements that might
generalize better for those stats AND check whether TOV (3/4 folds last
time) crosses the threshold under either:

  variant A — 2-output (ast+stl only): smaller output head, focused on
              the two winning stats. Less gradient pressure from PTS/REB.
  variant B — 3-output (ast+stl+tov): adds TOV (was 3/4 in cycle 23).
              Tests whether ast/stl/tov as a triplet share structure.
  variant C — 4-output (ast+stl+tov+pts): adds PTS (cycle 23 was 2/4 but
              the structure-sharing might help if isolated from REB/FG3M/BLK
              which actively regressed).

Compares each variant's per-fold MAE/R² to the current production:
  - For AST/STL: production = cycle-23 7-output multitask
  - For TOV/PTS: production = independent _MLPSeedEnsemble
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


VARIANTS = {
    "indep":      ["__SINGLE__"],          # placeholder: independent per stat
    "7out":       list(STATS),
    "2out_as":    ["ast", "stl"],
    "3out_ast":   ["ast", "stl", "tov"],
    "4out_pasts": ["pts", "ast", "stl", "tov"],
}


def _transform(stat, y):
    if stat in _SQRT_HUBER_STATS:
        return np.sqrt(y)
    if stat in _LOG_TRANSFORM_STATS:
        return np.log1p(y)
    return y


def _inverse(stat, v):
    if stat in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if stat in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return v


def _make_ensemble():
    return [
        MLPRegressor(
            hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
            learning_rate_init=1e-3, alpha=1e-4, batch_size=512,
            max_iter=80, random_state=int(s), early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=10,
        )
        for s in _MLP_SEEDS
    ]


def _trees(stat, X_tr, yt_tr, X_val, yt_val, sw):
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
    Y_raw = {s: np.array([r[f"target_{s}"] for r in rows], dtype=float) for s in STATS}
    print(f"n={n} features={len(fc)}", flush=True)

    fold_ends = [(i + 1) / 5 for i in range(4)]
    # Per-stat per-fold MAE/R² for each variant
    results = {v: {s: {"mae": [], "r2": []} for s in ["pts", "ast", "stl", "tov"]} for v in VARIANTS}

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

        # Pre-train independent MLP per evaluated stat (baseline)
        indep_val = {}; indep_ho = {}
        for stat in ["pts", "ast", "stl", "tov"]:
            yt_tr = _transform(stat, Y_raw[stat][:tr_end])
            ensemble = _make_ensemble()
            for m in ensemble:
                m.fit(Xts, yt_tr)
            indep_val[stat] = np.mean([m.predict(Xvs) for m in ensemble], axis=0)
            indep_ho[stat]  = np.mean([m.predict(Xhs) for m in ensemble], axis=0)

        # Pre-train multitask MLPs at each variant size
        mt_val = {}; mt_ho = {}
        for v_name, v_stats in VARIANTS.items():
            if v_name == "indep":
                continue
            Y_tr_v = np.column_stack([_transform(s, Y_raw[s][:tr_end]) for s in v_stats])
            ens = _make_ensemble()
            for m in ens:
                m.fit(Xts, Y_tr_v)
            mt_val[v_name] = np.mean([m.predict(Xvs) for m in ens], axis=0)
            mt_ho[v_name]  = np.mean([m.predict(Xhs) for m in ens], axis=0)

        for stat in ["pts", "ast", "stl", "tov"]:
            yt_tr = _transform(stat, Y_raw[stat][:tr_end])
            yt_val = _transform(stat, Y_raw[stat][tr_end:va_end])
            y_val = Y_raw[stat][tr_end:va_end]
            y_ho  = Y_raw[stat][va_end:te_end]
            xgb_m, lgb_m = _trees(stat, X_tr, yt_tr, X_val, yt_val, sw)
            xgb_val = _inverse(stat, xgb_m.predict(X_val))
            lgb_val = _inverse(stat, lgb_m.predict(X_val))
            xgb_ho  = _inverse(stat, xgb_m.predict(X_ho))
            lgb_ho  = _inverse(stat, lgb_m.predict(X_ho))
            for v_name, v_stats in VARIANTS.items():
                if v_name == "indep":
                    mv_t, mh_t = indep_val[stat], indep_ho[stat]
                else:
                    if stat not in v_stats:
                        continue
                    idx = v_stats.index(stat)
                    raw_val = mt_val[v_name]; raw_ho = mt_ho[v_name]
                    if raw_val.ndim == 1:
                        mv_t, mh_t = raw_val, raw_ho
                    else:
                        mv_t, mh_t = raw_val[:, idx], raw_ho[:, idx]
                mv = _inverse(stat, mv_t); mh = _inverse(stat, mh_t)
                st = LinearRegression(positive=True, fit_intercept=False).fit(
                    np.column_stack([xgb_val, lgb_val, mv]), y_val)
                w = st.coef_
                if not (0.5 <= w.sum() <= 1.5):
                    w = np.array([1/3, 1/3, 1/3])
                blend = np.clip(w[0]*xgb_ho + w[1]*lgb_ho + w[2]*mh, 0.0, None)
                results[v_name][stat]["mae"].append(mean_absolute_error(y_ho, blend))
                results[v_name][stat]["r2"].append(r2_score(y_ho, blend))
        print(f"  fold {fi+1} complete", flush=True)

    print()
    print("== Per-stat MAE deltas vs INDEP baseline (4-fold WF) ==")
    for stat in ["pts", "ast", "stl", "tov"]:
        bmae = np.array(results["indep"][stat]["mae"])
        br2  = np.array(results["indep"][stat]["r2"])
        print(f"\n  --- {stat.upper()} (indep mean MAE={bmae.mean():.4f}) ---")
        for v_name in ["7out", "2out_as", "3out_ast", "4out_pasts"]:
            if stat not in VARIANTS[v_name]:
                print(f"    {v_name}: (not in variant)")
                continue
            mae = np.array(results[v_name][stat]["mae"])
            r2  = np.array(results[v_name][stat]["r2"])
            dm = mae - bmae; dr = r2 - br2
            pf = " ".join(f"{x:+.4f}" for x in dm)
            n_pos = int((dm < 0).sum())
            print(f"    {v_name:12s}: d_mae={dm.mean():+.4f}+-{dm.std():.4f}  d_r2={dr.mean():+.4f}+-{dr.std():.4f}  "
                  f"folds_negative={n_pos}/4  per-fold mae=[{pf}]")


if __name__ == "__main__":
    main()
