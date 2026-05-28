"""retrain_iter46_per_opp_rolling.py — Iter-46 OOS retrain: per-opponent rolling-3.

Retrains all 6 stats that received a new per-stat per_opp_{stat}_l3 feature:
  PTS  (+1 col: per_opp_pts_l3)  → NNLS(XGB-sqrt+Huber + LGB-huber + MLP)
  REB  (+1 col: per_opp_reb_l3)  → LGB q50
  AST  (+1 col: per_opp_ast_l3)  → NNLS(XGB-log1p + LGB-log1p + MultitaskMLP)
  FG3M (+1 col: per_opp_fg3m_l3) → XGB q50
  STL  (+1 col: per_opp_stl_l3)  → XGB q50
  BLK  (+1 col: per_opp_blk_l3)  → XGB q50

All builds use feature_columns(stat) — the per-stat list — so the new column is
included. Same cutoff (2025-04-21), same recency-decay (0.5), same HPs as current
oos_pre_playoffs artifacts.

Usage:
    python scripts/retrain_iter46_per_opp_rolling.py [--stat <stat>]

Backup MUST be done before running.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_pergame import (
    build_pergame_dataset,
    feature_columns,
    _PER_OPP_ROLLING_KEYS,
    _LOG_TRANSFORM_STATS,
    _SQRT_HUBER_STATS,
    _USE_MULTITASK_MLP_STATS,
    _MLP_SEEDS,
    _MLPSeedEnsemble,
    _MultitaskMLPEnsemble,
    _MultitaskMLPProxy,
    STATS,
    _RECENCY_DECAY,
)
from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params

import xgboost as xgb
import lightgbm as lgb
import joblib
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score

CUTOFF_DATE = "2025-04-21"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")

# Model dispatch
_LGB_Q50_STATS = {"reb"}
_XGB_Q50_STATS = {"fg3m", "stl", "blk"}
_PTS_STATS = {"pts"}
_AST_STATS = {"ast"}

_ALL_ITER46_STATS = sorted({"pts", "reb", "ast", "fg3m", "stl", "blk"})


# ── common helpers ─────────────────────────────────────────────────────────────

def _load_rows() -> List[dict]:
    rows, _ = build_pergame_dataset(None)
    return rows


def _filter_and_sort(rows: List[dict], cutoff: datetime) -> List[dict]:
    pre = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre.sort(key=lambda r: r["date"])
    return pre


def _build_X(rows: List[dict], fcols: List[str]) -> np.ndarray:
    """Build feature matrix; NaN for per_opp missing → tree handles natively."""
    out = np.zeros((len(rows), len(fcols)), dtype=float)
    for i, r in enumerate(rows):
        for j, c in enumerate(fcols):
            v = r.get(c)
            if v is None:
                out[i, j] = float("nan")
            else:
                try:
                    out[i, j] = float(v)
                except (TypeError, ValueError):
                    out[i, j] = 0.0
    return out


def _impute_nan_for_mlp(X: np.ndarray) -> np.ndarray:
    """Column-mean imputation so sklearn MLP can handle NaN per_opp values.

    Trees (XGB/LGB) receive the raw NaN array and handle missing natively.
    MLP needs dense input — impute missing with training-column mean (or 0
    for all-NaN columns). Applied ONLY on the scaled X before MLP.fit/predict.
    """
    out = X.copy()
    col_means = np.nanmean(out, axis=0)
    nan_cols = np.isnan(col_means)
    col_means[nan_cols] = 0.0
    idxs = np.where(np.isnan(out))
    out[idxs[0], idxs[1]] = col_means[idxs[1]]
    return out


def _sample_weights(rows: List[dict], train_end: int, decay: float = _RECENCY_DECAY) -> np.ndarray:
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    return np.exp(-decay * age) if decay > 0 else np.ones(train_end)


def _nnls_weights(preds_tr: List[np.ndarray], y_tr: np.ndarray) -> np.ndarray:
    from scipy.optimize import nnls
    A = np.column_stack(preds_tr)
    w, _ = nnls(A, y_tr)
    s = w.sum()
    return w / s if s > 0 else np.ones(len(w)) / len(w)


def _top10(model, fcols: List[str]) -> List[Tuple[str, float]]:
    try:
        imps = model.feature_importances_
    except AttributeError:
        return []
    return sorted(zip(fcols, imps), key=lambda x: x[1], reverse=True)[:10]


# ── PTS retrain (NNLS sqrt+Huber) ─────────────────────────────────────────────

def retrain_pts(rows: List[dict]) -> dict:
    stat = "pts"
    fcols = feature_columns(stat)
    opp_key = f"per_opp_{stat}_l3"
    print(f"\n  [iter-46] {stat}: {len(fcols)} cols  new_key={opp_key}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}", flush=True)

    holdout_frac, val_frac = 0.2, 0.15
    train_end = int(n_pre * (1 - holdout_frac - val_frac))
    val_end   = int(n_pre * (1 - holdout_frac))

    X_all = _build_X(pre, fcols)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{stat}"] for r in pre], dtype=float)
    y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
    y_tr_t, y_val_t = np.sqrt(y_tr), np.sqrt(y_val)

    params = {
        "max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
        "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
        "colsample_bytree": 0.9, "reg_alpha": 2.0, "subsample": 0.8,
    }
    t0 = time.time()

    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:pseudohubererror",
        early_stopping_rounds=40, eval_metric="mae", enable_categorical=False,
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(xgb_m.predict(X_tr), 0, None) ** 2
    xgb_pred_ho = np.clip(xgb_m.predict(X_ho), 0, None) ** 2

    lgb_m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"], subsample=params["subsample"],
        subsample_freq=1, colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=42, objective="huber", n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])
    lgb_pred_tr = np.clip(lgb_m.predict(X_tr), 0, None) ** 2
    lgb_pred_ho = np.clip(lgb_m.predict(X_ho), 0, None) ** 2

    scaler = StandardScaler()
    # Impute NaN before scaling (MLP cannot handle NaN; trees handle it natively above).
    X_tr_imp = _impute_nan_for_mlp(X_tr)
    X_ho_imp = _impute_nan_for_mlp(X_ho)
    Xs_tr = scaler.fit_transform(X_tr_imp)
    Xs_val = scaler.transform(_impute_nan_for_mlp(X_val))
    Xs_ho  = scaler.transform(X_ho_imp)
    mlp = _MLPSeedEnsemble()
    mlp.fit(Xs_tr, y_tr_t)
    mlp_pred_tr = np.clip(mlp.predict(Xs_tr), 0, None) ** 2
    mlp_pred_ho = np.clip(mlp.predict(Xs_ho), 0, None) ** 2

    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}", flush=True)

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)", flush=True)

    top10_xgb = _top10(xgb_m, fcols)
    for rank, (name, imp) in enumerate(top10_xgb, 1):
        marker = " <-- NEW" if name == opp_key else ""
        print(f"    #{rank:2d}  {name:<40}  {imp:.4f}{marker}", flush=True)

    xgb_m.save_model(os.path.join(OOS_DIR, f"props_pg_{stat}.json"))
    joblib.dump(lgb_m, os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"))
    joblib.dump(mlp, os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"))
    joblib.dump(scaler, os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"))

    _update_meta_weights(OOS_DIR, stat, w_xgb, w_lgb, w_mlp)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre, "n_train": train_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10_xgb": [(n, float(v)) for n, v in top10_xgb],
    }


# ── AST retrain (NNLS log1p + MultitaskMLP) ───────────────────────────────────

def retrain_ast(rows: List[dict]) -> dict:
    stat = "ast"
    fcols = feature_columns(stat)
    opp_key = f"per_opp_{stat}_l3"
    print(f"\n  [iter-46] {stat}: {len(fcols)} cols  new_key={opp_key}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}", flush=True)

    holdout_frac, val_frac = 0.2, 0.15
    train_end = int(n_pre * (1 - holdout_frac - val_frac))
    val_end   = int(n_pre * (1 - holdout_frac))

    X_all = _build_X(pre, fcols)
    X_tr, X_val, X_ho = X_all[:train_end], X_all[train_end:val_end], X_all[val_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{stat}"] for r in pre], dtype=float)
    y_tr, y_val, y_ho = y[:train_end], y[train_end:val_end], y[val_end:]
    y_tr_t, y_val_t = np.log1p(y_tr), np.log1p(y_val)

    params = {
        "max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
        "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
        "subsample": 0.7, "colsample_bytree": 0.8, "reg_alpha": 0.5,
    }
    t0 = time.time()

    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae", enable_categorical=False,
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(np.expm1(xgb_m.predict(X_tr)), 0, None)
    xgb_pred_ho = np.clip(np.expm1(xgb_m.predict(X_ho)), 0, None)

    lgb_m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"], subsample=params["subsample"],
        subsample_freq=1, colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=42, objective="regression", n_jobs=-1, verbosity=-1,
    )
    lgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw,
              callbacks=[lgb.early_stopping(40, verbose=False)])
    lgb_pred_tr = np.clip(np.expm1(lgb_m.predict(X_tr)), 0, None)
    lgb_pred_ho = np.clip(np.expm1(lgb_m.predict(X_ho)), 0, None)

    scaler = StandardScaler()
    # Impute NaN before scaling for MLP (trees handle NaN natively above).
    X_tr_imp = _impute_nan_for_mlp(X_tr)
    X_ho_imp = _impute_nan_for_mlp(X_ho)
    Xs_tr = scaler.fit_transform(X_tr_imp)
    Xs_ho  = scaler.transform(X_ho_imp)

    Y_tr_mt = np.zeros((train_end, len(STATS)), dtype=float)
    for i, s in enumerate(STATS):
        ys = np.array([r[f"target_{s}"] for r in pre[:train_end]], dtype=float)
        if s in _SQRT_HUBER_STATS:
            Y_tr_mt[:, i] = np.sqrt(ys)
        elif s in _LOG_TRANSFORM_STATS:
            Y_tr_mt[:, i] = np.log1p(ys)
        else:
            Y_tr_mt[:, i] = ys

    mt_ensemble = _MultitaskMLPEnsemble().fit(Xs_tr, Y_tr_mt)
    ast_idx = STATS.index(stat)
    mlp_proxy = _MultitaskMLPProxy(mt_ensemble, ast_idx)
    mlp_pred_tr = np.clip(np.expm1(mlp_proxy.predict(Xs_tr)), 0, None)
    mlp_pred_ho = np.clip(np.expm1(mlp_proxy.predict(Xs_ho)), 0, None)

    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}", flush=True)

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)", flush=True)

    top10_xgb = _top10(xgb_m, fcols)
    for rank, (name, imp) in enumerate(top10_xgb, 1):
        marker = " <-- NEW" if name == opp_key else ""
        print(f"    #{rank:2d}  {name:<40}  {imp:.4f}{marker}", flush=True)

    xgb_m.save_model(os.path.join(OOS_DIR, f"props_pg_{stat}.json"))
    joblib.dump(lgb_m, os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"))
    joblib.dump(mlp_proxy, os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"))
    joblib.dump(scaler, os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"))

    _update_meta_weights(OOS_DIR, stat, w_xgb, w_lgb, w_mlp)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre, "n_train": train_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10_xgb": [(n, float(v)) for n, v in top10_xgb],
    }


# ── REB retrain (LGB q50) ──────────────────────────────────────────────────────

def retrain_reb(rows: List[dict]) -> dict:
    stat = "reb"
    fcols = feature_columns(stat)
    opp_key = f"per_opp_{stat}_l3"
    print(f"\n  [iter-46] {stat}: {len(fcols)} cols  new_key={opp_key}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}", flush=True)

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = _build_X(pre, fcols)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{stat}"] for r in pre], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)

    params = _per_stat_xgb_params(stat)
    t0 = time.time()
    m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"], subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=42, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    fit_secs = time.time() - t0

    pred_val = _inverse(stat, np.array(m.predict(X_val), dtype=float))
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val), -0.5 * (y_val - pred_val))))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    print(f"  {stat}: val_pinball={val_pinball:.4f}  val_MAE={val_mae:.4f}  ({fit_secs:.1f}s)", flush=True)

    top10_lgb = _top10(m, fcols)
    for rank, (name, imp) in enumerate(top10_lgb, 1):
        marker = " <-- NEW" if name == opp_key else ""
        print(f"    #{rank:2d}  {name:<40}  {imp:.1f}{marker}", flush=True)

    joblib.dump(m, os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl"))

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre, "n_train": train_end,
        "val_pinball": val_pinball, "val_mae": val_mae,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10": [(n, float(v)) for n, v in top10_lgb],
    }


# ── q50 retrain (XGB, for FG3M / STL / BLK) ──────────────────────────────────

def retrain_q50_xgb(rows: List[dict], stat: str) -> dict:
    fcols = feature_columns(stat)
    opp_key = f"per_opp_{stat}_l3"
    print(f"\n  [iter-46] {stat}: {len(fcols)} cols  new_key={opp_key}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all, n_pre = len(rows), len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}", flush=True)

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = _build_X(pre, fcols)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    sw = _sample_weights(pre, train_end)

    y = np.array([r[f"target_{stat}"] for r in pre], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)

    params = _per_stat_xgb_params(stat)
    t0 = time.time()
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae", enable_categorical=False,
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    fit_secs = time.time() - t0

    pred_val = _inverse(stat, np.array(m.predict(X_val), dtype=float))
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val), -0.5 * (y_val - pred_val))))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    best_iter = int(getattr(m, "best_iteration", -1) or -1)
    print(f"  {stat}: val_pinball={val_pinball:.4f}  val_MAE={val_mae:.4f}  "
          f"best_iter={best_iter}  ({fit_secs:.1f}s)", flush=True)

    top10_xgb = _top10(m, fcols)
    for rank, (name, imp) in enumerate(top10_xgb, 1):
        marker = " <-- NEW" if name == opp_key else ""
        print(f"    #{rank:2d}  {name:<40}  {imp:.4f}{marker}", flush=True)

    fname = f"quantile_pergame_{stat}_q50.json"
    m.save_model(os.path.join(OOS_DIR, fname))

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre, "n_train": train_end,
        "val_pinball": val_pinball, "val_mae": val_mae,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10_xgb": [(n, float(v)) for n, v in top10_xgb],
    }


# ── meta helpers ───────────────────────────────────────────────────────────────

def _update_meta_weights(oos_dir: str, stat: str, w_xgb: float, w_lgb: float, w_mlp: float) -> None:
    weights_path = os.path.join(oos_dir, "meta_weights_pergame.json")
    all_w: dict = {}
    if os.path.exists(weights_path):
        try:
            all_w = json.load(open(weights_path, encoding="utf-8"))
        except Exception:
            all_w = {}
    all_w[stat] = {"w_xgb": round(w_xgb, 4), "w_lgb": round(w_lgb, 4), "w_mlp": round(w_mlp, 4)}
    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(all_w, fh, indent=2)


def _write_meta(results: List[dict]) -> None:
    meta_path = os.path.join(OOS_DIR, "_meta.json")
    all_meta: dict = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta["stats"] = {}

    for r in results:
        stat = r["stat"]
        base: dict = {
            "iter": "iter46",
            "cutoff_date": CUTOFF_DATE,
            "n_train": r["n_train"],
            "n_total_rows": r["n_all"],
            "n_pre_cutoff_rows": r["n_pre"],
            "n_features": len(r["fcols"]),
            "feature_columns": r["fcols"],
            "training_timestamp": datetime.now().isoformat(),
            "fit_seconds": r["fit_secs"],
            "new_feature": f"per_opp_{stat}_l3",
        }
        if stat in _LGB_Q50_STATS:
            base.update({"method": "lgb_q50", "val_pinball": r["val_pinball"],
                         "val_mae": r["val_mae"], "top10": r.get("top10", [])})
        elif stat in _XGB_Q50_STATS:
            base.update({"method": "xgb_q50", "val_pinball": r["val_pinball"],
                         "val_mae": r["val_mae"], "top10_xgb": r.get("top10_xgb", [])})
        else:
            base.update({"method": "nnls_blend", "holdout_r2": r.get("holdout_r2"),
                         "holdout_mae": r.get("holdout_mae"),
                         "w_xgb": r.get("w_xgb"), "w_lgb": r.get("w_lgb"), "w_mlp": r.get("w_mlp"),
                         "top10_xgb": r.get("top10_xgb", [])})
        all_meta["stats"][stat] = base

    all_meta["iter"] = "iter46"
    all_meta["cutoff"] = CUTOFF_DATE
    all_meta["updated_at"] = datetime.now().isoformat()

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"\n  _meta.json updated -> {meta_path}", flush=True)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", default=None,
                    choices=_ALL_ITER46_STATS + ["all"],
                    help="Train one stat only (default: all)")
    args = ap.parse_args()
    run_stats = _ALL_ITER46_STATS if (args.stat is None or args.stat == "all") else [args.stat]

    print(f"\n=== iter-46 retrain: per-opponent rolling-3 for {run_stats} "
          f"(cutoff {CUTOFF_DATE}) ===", flush=True)
    total_t0 = time.time()
    os.makedirs(OOS_DIR, exist_ok=True)

    print("  Loading gamelog rows (shared) ...", flush=True)
    rows = _load_rows()
    print(f"  Total rows: {len(rows)}", flush=True)

    results = []
    for stat in run_stats:
        if stat == "pts":
            results.append(retrain_pts(rows))
        elif stat == "ast":
            results.append(retrain_ast(rows))
        elif stat == "reb":
            results.append(retrain_reb(rows))
        else:
            results.append(retrain_q50_xgb(rows, stat))

    _write_meta(results)

    elapsed = time.time() - total_t0
    print(f"\n=== iter-46 retrain complete in {elapsed:.1f}s ===", flush=True)
    print("\n  Summary:", flush=True)
    for r in results:
        stat = r["stat"]
        if stat in _LGB_Q50_STATS | _XGB_Q50_STATS:
            print(f"  {stat:6s}: val_MAE={r['val_mae']:.4f}  pinball={r['val_pinball']:.4f}  "
                  f"({r['fit_secs']:.1f}s)", flush=True)
        else:
            print(f"  {stat:6s}: holdout_R²={r['holdout_r2']:.4f}  "
                  f"holdout_MAE={r['holdout_mae']:.4f}  ({r['fit_secs']:.1f}s)", flush=True)


if __name__ == "__main__":
    main()
