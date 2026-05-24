"""probe_q50_variants.py — three quantile variants in one 4-fold WF probe.

For each of the 7 stats, train and compare:
  baseline_xgb_q50    : current cycle-27 production (XGB-q50)
  hgb_q50             : sklearn HistGradientBoostingRegressor quantile
  bag5_xgb_q50        : 5-seed XGB-q50 ensemble (bagged predictions)
  shift_xgb_q45       : XGB quantile at q=0.45 (slightly under-median)
  shift_xgb_q55       : XGB quantile at q=0.55 (slightly over-median)

Reports per-stat per-variant 4-fold MAE delta vs the baseline.
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
    STATS, _LOG_TRANSFORM_STATS, _SQRT_HUBER_STATS,
    build_pergame_dataset, feature_columns,
)
import xgboost as xgb
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error


def _tx(s, y):
    if s in _SQRT_HUBER_STATS:
        return np.sqrt(y)
    if s in _LOG_TRANSFORM_STATS:
        return np.log1p(y)
    return y


def _inv(s, v):
    if s in _SQRT_HUBER_STATS:
        return np.clip(v, 0.0, None) ** 2
    if s in _LOG_TRANSFORM_STATS:
        return np.clip(np.expm1(v), 0.0, None)
    return np.clip(v, 0.0, None)


def _xgb_q(stat, X_tr, yt_tr, X_val, yt_val, sw, q=0.5, seed=42):
    p = {
        "pts":  dict(md=6, lr=0.025, mcw=20, rl=4.0, ra=2.0, g=0.2, ne=800, ss=0.8, cs=0.9),
        "reb":  dict(md=3, lr=0.025, mcw=30, rl=4.0, ra=0.5, g=0.3, ne=800, ss=0.7, cs=0.9),
        "ast":  dict(md=5, lr=0.025, mcw=20, rl=5.0, ra=0.5, g=0.2, ne=800, ss=0.7, cs=0.8),
        "fg3m": dict(md=4, lr=0.025, mcw=15, rl=8.0, ra=0.5, g=0.0, ne=600, ss=0.7, cs=0.8),
        "stl":  dict(md=2, lr=0.06,  mcw=40, rl=6.0, ra=0.25,g=0.6, ne=400, ss=0.9, cs=0.8),
        "blk":  dict(md=3, lr=0.06,  mcw=25, rl=4.0, ra=0.5, g=0.4, ne=800, ss=0.8, cs=1.0),
        "tov":  dict(md=3, lr=0.025, mcw=30, rl=6.0, ra=0.5, g=0.4, ne=700, ss=0.8, cs=0.8),
    }[stat]
    m = xgb.XGBRegressor(
        n_estimators=p["ne"], max_depth=p["md"], learning_rate=p["lr"],
        subsample=p["ss"], colsample_bytree=p["cs"],
        min_child_weight=p["mcw"], reg_lambda=p["rl"], reg_alpha=p["ra"],
        gamma=p["g"], random_state=int(seed),
        objective="reg:quantileerror", quantile_alpha=q,
        eval_metric="mae", early_stopping_rounds=40,
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    return m


def main():
    rows, fc = build_pergame_dataset(min_prior=0)
    rows.sort(key=lambda r: r["date"])
    n = len(rows)
    X_all = np.array([[r[c] for c in fc] for r in rows], dtype=float)
    dates_all = [datetime.fromisoformat(r["date"]) for r in rows]
    print(f"n={n} features={len(fc)}", flush=True)

    fold_ends = [(i + 1) / 5 for i in range(4)]
    variants = ["baseline_xgb_q50", "hgb_q50", "bag5_xgb_q50",
                "shift_xgb_q45", "shift_xgb_q55"]
    out = {s: {v: [] for v in variants} for s in STATS}
    SEEDS = (1, 7, 42, 100, 2024)

    for fi, train_end_frac in enumerate(fold_ends):
        tr_end = int(n * train_end_frac)
        te_end = n if fi == 3 else int(n * fold_ends[fi+1])
        va_end = int(tr_end + (te_end - tr_end) * 0.4)
        if tr_end < 5000:
            continue
        age = np.array([(max(dates_all[:tr_end]) - d).days / 365.0 for d in dates_all[:tr_end]])
        sw = np.exp(-0.5 * age)
        X_tr, X_val, X_ho = X_all[:tr_end], X_all[tr_end:va_end], X_all[va_end:te_end]

        for stat in STATS:
            y = np.array([r[f"target_{stat}"] for r in rows], dtype=float)
            y_tr, y_val, y_ho = y[:tr_end], y[tr_end:va_end], y[va_end:te_end]
            yt_tr, yt_val = _tx(stat, y_tr), _tx(stat, y_val)

            # baseline
            m_base = _xgb_q(stat, X_tr, yt_tr, X_val, yt_val, sw, q=0.5, seed=42)
            base_pred = _inv(stat, m_base.predict(X_ho))
            out[stat]["baseline_xgb_q50"].append(mean_absolute_error(y_ho, base_pred))

            # HGB quantile median
            try:
                hgb = HistGradientBoostingRegressor(
                    loss="quantile", quantile=0.5,
                    learning_rate=0.05, max_iter=400, max_depth=6,
                    min_samples_leaf=40, l2_regularization=2.0,
                    early_stopping=True, validation_fraction=0.15,
                    n_iter_no_change=20, random_state=42,
                )
                hgb.fit(X_tr, yt_tr, sample_weight=sw)
                hgb_pred = _inv(stat, hgb.predict(X_ho))
                out[stat]["hgb_q50"].append(mean_absolute_error(y_ho, hgb_pred))
            except Exception as e:
                out[stat]["hgb_q50"].append(None)

            # 5-seed XGB-q50 bagging
            preds = []
            for s_ in SEEDS:
                m_s = _xgb_q(stat, X_tr, yt_tr, X_val, yt_val, sw, q=0.5, seed=s_)
                preds.append(_inv(stat, m_s.predict(X_ho)))
            bag_pred = np.mean(preds, axis=0)
            out[stat]["bag5_xgb_q50"].append(mean_absolute_error(y_ho, bag_pred))

            # q=0.45 / q=0.55
            for q, key in [(0.45, "shift_xgb_q45"), (0.55, "shift_xgb_q55")]:
                m_s = _xgb_q(stat, X_tr, yt_tr, X_val, yt_val, sw, q=q, seed=42)
                p_s = _inv(stat, m_s.predict(X_ho))
                out[stat][key].append(mean_absolute_error(y_ho, p_s))
        print(f"  fold {fi+1} done", flush=True)

    print()
    print("== per-stat MAE deltas vs baseline_xgb_q50 (4-fold WF) ==")
    for stat in STATS:
        base = np.array(out[stat]["baseline_xgb_q50"])
        print(f"\n  --- {stat.upper()} (baseline mean={base.mean():.4f}) ---")
        for v in variants[1:]:
            arr = np.array([x for x in out[stat][v] if x is not None])
            if len(arr) < len(base):
                print(f"    {v:18s}: incomplete")
                continue
            dm = arr - base
            n_pos = int((dm < 0).sum())
            pf = " ".join(f"{x:+.4f}" for x in dm)
            print(f"    {v:18s}: d_mae={dm.mean():+.4f}+-{dm.std():.4f}  folds_negative={n_pos}/4  per-fold mae=[{pf}]")


if __name__ == "__main__":
    main()
