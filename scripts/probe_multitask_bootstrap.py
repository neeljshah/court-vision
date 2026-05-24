"""probe_multitask_bootstrap.py — bootstrapped multitask MLP for AST + STL.

Cycle 23 shipped the 7-output multitask MLP for AST + STL with 5 SEEDS over
the SAME training data (random_state varies, samples don't). Cycle 40 probed
ast-stack q50 variants and rejected.

This probe tests whether per-seed BOOTSTRAP sampling (80% with replacement
per seed) adds real variance reduction on top of the seed averaging. The
hypothesis: with 5 same-data seeds the ensemble has only weight-init
diversity; bootstrap adds data diversity which is a stronger decorrelator
for MLPs on noisy targets.

Two variants:
  prod_multitask  — current ship: 5-seed 7-output multitask, same data each seed
  boot_multitask  — 5-seed 7-output multitask, each seed sees 80% bootstrap

Scored against current production on 4-fold walk-forward + production
single-split for AST and STL. Ship gate is dual: 4/4 WF folds positive
AND production single-split MAE strictly down.

Run:
    python scripts/probe_multitask_bootstrap.py
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
    build_pergame_dataset, STATS,
    _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS, _MLP_SEEDS,
)
import xgboost as xgb
import lightgbm as lgb
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score


EVAL_STATS = ["ast", "stl"]


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


def _fit_mt_ensemble(X_tr, Y_tr, bootstrap: bool):
    """Fit 5-seed multitask MLP. If bootstrap, each seed sees 80% with replacement."""
    rng_base = np.random.default_rng(20260524)
    models = []
    n = X_tr.shape[0]
    for s in _MLP_SEEDS:
        m = MLPRegressor(
            hidden_layer_sizes=(128, 64), activation="relu", solver="adam",
            learning_rate_init=1e-3, alpha=1e-4, batch_size=512,
            max_iter=80, random_state=int(s), early_stopping=True,
            validation_fraction=0.15, n_iter_no_change=10,
        )
        if bootstrap:
            # Per-seed deterministic bootstrap: derive a child rng from
            # (base, seed) so the probe reproduces.
            rng = np.random.default_rng((20260524, int(s)))
            idx = rng.choice(n, size=int(0.80 * n), replace=True)
            m.fit(X_tr[idx], Y_tr[idx])
        else:
            m.fit(X_tr, Y_tr)
        models.append(m)
    return models


def _predict_mt(models, X):
    return np.mean([m.predict(X) for m in models], axis=0)


def _trees(stat, X_tr, yt_tr, X_val, yt_val, sw):
    use_log = stat in _LOG_TRANSFORM_STATS
    use_sqrt = stat in _SQRT_HUBER_STATS
    if use_sqrt:
        xgb_obj, lgb_obj = "reg:pseudohubererror", "huber"
    elif use_log:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    else:
        xgb_obj, lgb_obj = "reg:squarederror", "regression"
    # Per-stat HP from prop_pergame._STAT_PARAMS — only the two stats we score.
    p = {
        "ast":  dict(md=5, lr=0.025, mcw=20, rl=5.0, ra=0.5, g=0.2, ne=800, ss=0.7, cs=0.8),
        "stl":  dict(md=2, lr=0.06,  mcw=40, rl=6.0, ra=0.25,g=0.6, ne=400, ss=0.9, cs=0.8),
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


def _stack_and_score(stat, xgb_val, lgb_val, mv, xgb_ho, lgb_ho, mh, y_val, y_ho):
    """3-way NNLS stack on val (raw scale), score on holdout."""
    st = LinearRegression(positive=True, fit_intercept=False).fit(
        np.column_stack([xgb_val, lgb_val, mv]), y_val)
    w = st.coef_
    if not (0.5 <= w.sum() <= 1.5):
        w = np.array([1/3, 1/3, 1/3])
    pred = np.clip(w[0]*xgb_ho + w[1]*lgb_ho + w[2]*mh, 0.0, None)
    return mean_absolute_error(y_ho, pred), r2_score(y_ho, pred)


def _run_split(X_all, Y_raw, dates_all, tr_end, va_end, te_end):
    """Train both variants on a single (tr/val/holdout) split and return
    per-variant per-stat (mae, r2)."""
    age = np.array([(max(dates_all[:tr_end]) - d).days / 365.0
                    for d in dates_all[:tr_end]])
    sw = np.exp(-0.5 * age)
    X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]
    sc = StandardScaler()
    Xts = sc.fit_transform(X_tr); Xvs = sc.transform(X_val); Xhs = sc.transform(X_ho)

    # Build the full 7-output transformed target matrix for ALL stats.
    Y_tr_mt = np.column_stack([_transform(s, Y_raw[s][:tr_end]) for s in STATS])

    # Train both ensemble variants ONCE on the full multitask matrix.
    models_prod = _fit_mt_ensemble(Xts, Y_tr_mt, bootstrap=False)
    models_boot = _fit_mt_ensemble(Xts, Y_tr_mt, bootstrap=True)

    mt_val_prod = _predict_mt(models_prod, Xvs)
    mt_ho_prod  = _predict_mt(models_prod, Xhs)
    mt_val_boot = _predict_mt(models_boot, Xvs)
    mt_ho_boot  = _predict_mt(models_boot, Xhs)

    out = {"prod": {}, "boot": {}}
    for stat in EVAL_STATS:
        si = STATS.index(stat)
        yt_tr  = _transform(stat, Y_raw[stat][:tr_end])
        yt_val = _transform(stat, Y_raw[stat][tr_end:va_end])
        y_val  = Y_raw[stat][tr_end:va_end]
        y_ho   = Y_raw[stat][va_end:te_end]
        xgb_m, lgb_m = _trees(stat, X_tr, yt_tr, X_val, yt_val, sw)
        xgb_val = _inverse(stat, xgb_m.predict(X_val))
        lgb_val = _inverse(stat, lgb_m.predict(X_val))
        xgb_ho  = _inverse(stat, xgb_m.predict(X_ho))
        lgb_ho  = _inverse(stat, lgb_m.predict(X_ho))
        mv_prod = _inverse(stat, mt_val_prod[:, si])
        mh_prod = _inverse(stat, mt_ho_prod[:, si])
        mv_boot = _inverse(stat, mt_val_boot[:, si])
        mh_boot = _inverse(stat, mt_ho_boot[:, si])
        out["prod"][stat] = _stack_and_score(stat, xgb_val, lgb_val, mv_prod,
                                             xgb_ho, lgb_ho, mh_prod, y_val, y_ho)
        out["boot"][stat] = _stack_and_score(stat, xgb_val, lgb_val, mv_boot,
                                             xgb_ho, lgb_ho, mh_boot, y_val, y_ho)
    return out


def main():
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    dates_all = [datetime.fromisoformat(r["date"]) for r in rows]
    Y_raw = {s: np.array([r[f"target_{s}"] for r in rows], dtype=float) for s in STATS}
    print(f"n={n} features={len(fc)}", flush=True)

    # === Walk-forward 4 folds ===
    fold_ends = [(i + 1) / 5 for i in range(4)]
    wf = {"prod": {s: {"mae": [], "r2": []} for s in EVAL_STATS},
          "boot": {s: {"mae": [], "r2": []} for s in EVAL_STATS}}

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000:
            continue
        res = _run_split(X_all, Y_raw, dates_all, tr_end, va_end, te_end)
        for v in ("prod", "boot"):
            for s in EVAL_STATS:
                mae, r2 = res[v][s]
                wf[v][s]["mae"].append(mae)
                wf[v][s]["r2"].append(r2)
        line = "  WF fold %d: " % (fi + 1)
        for s in EVAL_STATS:
            dm = res["boot"][s][0] - res["prod"][s][0]
            line += f"{s.upper()} dm={dm:+.4f}  "
        print(line, flush=True)

    # === Production single-split (80/20 with 0.4 of holdout used as val) ===
    print("\n  running production single-split (80/20)...", flush=True)
    tr_end = int(n * 0.8)
    te_end = n
    va_end = int(tr_end + (te_end - tr_end) * 0.4)
    ss = _run_split(X_all, Y_raw, dates_all, tr_end, va_end, te_end)

    # === Report ===
    print("\n=== Walk-forward 4-fold (lower MAE better) ===")
    for s in EVAL_STATS:
        pm = np.array(wf["prod"][s]["mae"])
        bm = np.array(wf["boot"][s]["mae"])
        dm = bm - pm
        n_pos = int((dm < 0).sum())  # boot beats prod
        print(f"  {s.upper()}: prod mae={pm.mean():.4f}+-{pm.std():.4f}  "
              f"boot mae={bm.mean():.4f}+-{bm.std():.4f}  "
              f"d={dm.mean():+.4f}  boot_wins={n_pos}/4  per_fold_d=[{' '.join(f'{x:+.4f}' for x in dm)}]")

    print("\n=== Production single-split ===")
    for s in EVAL_STATS:
        pm, pr = ss["prod"][s]
        bm, br = ss["boot"][s]
        print(f"  {s.upper()}: prod mae={pm:.4f} r2={pr:.4f}  |  "
              f"boot mae={bm:.4f} r2={br:.4f}  |  d_mae={bm-pm:+.4f}  d_r2={br-pr:+.4f}")

    print("\n=== Ship gate (dual: WF 4/4 AND single-split MAE strictly down) ===")
    for s in EVAL_STATS:
        pm = np.array(wf["prod"][s]["mae"])
        bm = np.array(wf["boot"][s]["mae"])
        wf_pass = int((bm < pm).sum()) == 4
        ss_pass = ss["boot"][s][0] < ss["prod"][s][0]
        verdict = "SHIP" if (wf_pass and ss_pass) else "REJECT"
        print(f"  {s.upper()}: wf 4/4 = {wf_pass}, single-split strictly down = {ss_pass} -> {verdict}")


if __name__ == "__main__":
    main()
