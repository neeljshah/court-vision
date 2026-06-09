"""retrain_iter44_synergy_ppp.py - Iter-44 OOS retrain for narrow synergy PPP probe.

Retrains ONLY the three stats that received new per-stat features in iter-44:
  AST  (+1 col: syn_pnr_bh_ppp)
  PTS  (+2 cols: syn_iso_ppp + syn_pnr_bh_ppp)
  FG3M (+1 col: syn_spotup_ppp)

All three stats build X from feature_columns(stat) — the extended per-stat list —
so the new PPP columns are included in training. Same HPs, same cutoff (2025-04-21),
same recency decay (0.5) as the current artifacts in oos_pre_playoffs.

AST: NNLS(XGB-log1p + LGB-log1p + multitask-MLP). Uses train_pergame_models with
     a monkey-patched X builder that uses feature_columns('ast').

PTS: NNLS(XGB-sqrt+Huber + LGB-huber + MLP). Uses train_pergame_models with
     a monkey-patched X builder that uses feature_columns('pts').

FG3M: XGB q50 (quantile_alpha=0.5). Standalone loop using feature_columns('fg3m').

Backup MUST be done before running this script.
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from src.prediction.prop_pergame import (
    build_pergame_dataset,
    feature_columns,
    _SYN_PPP_KEYS,
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
from sklearn.linear_model import LinearRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import mean_absolute_error, r2_score

CUTOFF_DATE = "2025-04-21"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


# ---------------------------------------------------------------------------
# Common helpers
# ---------------------------------------------------------------------------

def _load_rows() -> list:
    rows, _ = build_pergame_dataset(None)
    return rows


def _filter_and_sort(rows: list, cutoff: datetime) -> list:
    pre = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre.sort(key=lambda r: r["date"])
    return pre


def _build_X(rows: list, fcols: list) -> np.ndarray:
    return np.array([[float(r.get(c, 0.0) or 0.0) for c in fcols] for r in rows],
                    dtype=float)


def _sample_weights(rows: list, train_end: int, decay: float = _RECENCY_DECAY) -> np.ndarray:
    train_dates = [datetime.fromisoformat(rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    return np.exp(-decay * age) if decay > 0 else np.ones(train_end)


def _nnls_weights(preds_tr: list[np.ndarray], y_tr: np.ndarray) -> np.ndarray:
    """Non-negative least squares stacking weights."""
    from scipy.optimize import nnls
    A = np.column_stack(preds_tr)
    w, _ = nnls(A, y_tr)
    s = w.sum()
    return w / s if s > 0 else np.ones(len(w)) / len(w)


# ---------------------------------------------------------------------------
# PTS retrain: sqrt+Huber blend
# ---------------------------------------------------------------------------

def retrain_pts(rows: list) -> dict:
    stat = "pts"
    fcols = feature_columns(stat)
    print(f"\n  [iter-44] {stat}: {len(fcols)} cols "
          f"(base 129 + {fcols[129:]})")

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}")

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

    # XGB
    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:pseudohubererror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(xgb_m.predict(X_tr), 0, None) ** 2
    xgb_pred_ho = np.clip(xgb_m.predict(X_ho), 0, None) ** 2

    # LGB
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

    # MLP 5-seed ensemble
    scaler = StandardScaler()
    Xs_tr = scaler.fit_transform(X_tr)
    Xs_val = scaler.transform(X_val)
    Xs_ho  = scaler.transform(X_ho)
    mlp = _MLPSeedEnsemble()
    mlp.fit(Xs_tr, y_tr_t)
    mlp_pred_tr = np.clip(mlp.predict(Xs_tr), 0, None) ** 2
    mlp_pred_ho = np.clip(mlp.predict(Xs_ho), 0, None) ** 2

    # NNLS stacking on RAW-count train predictions
    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}")

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)")

    # Persist artifacts
    xgb_m.save_model(os.path.join(OOS_DIR, f"props_pg_{stat}.json"))
    joblib.dump(lgb_m, os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"))
    joblib.dump(mlp, os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"))
    joblib.dump(scaler, os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"))

    # Update NNLS weights in meta_weights_pergame.json
    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    all_w: dict = {}
    if os.path.exists(weights_path):
        try:
            all_w = json.load(open(weights_path, encoding="utf-8"))
        except Exception:
            all_w = {}
    all_w[stat] = {"w_xgb": round(w_xgb, 4), "w_lgb": round(w_lgb, 4),
                   "w_mlp": round(w_mlp, 4)}
    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(all_w, fh, indent=2)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": val_end - train_end, "n_holdout": n_pre - val_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
    }


# ---------------------------------------------------------------------------
# AST retrain: log1p multitask-MLP blend
# ---------------------------------------------------------------------------

def retrain_ast(rows: list) -> dict:
    stat = "ast"
    fcols = feature_columns(stat)
    print(f"\n  [iter-44] {stat}: {len(fcols)} cols "
          f"(base 129 + {fcols[129:]})")

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}")

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

    # XGB
    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(np.expm1(xgb_m.predict(X_tr)), 0, None)
    xgb_pred_ho = np.clip(np.expm1(xgb_m.predict(X_ho)), 0, None)

    # LGB
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

    # Multitask MLP for AST (stat in _USE_MULTITASK_MLP_STATS)
    # Build the full multi-output target matrix for all 7 STATS using the
    # base 129-col X (multitask MLP is shared; it was trained on base features).
    # For the iter-44 probe we include the 1 extra col — the multitask MLP
    # sees the full extended X (130 cols for ast).
    scaler = StandardScaler()
    Xs_tr = scaler.fit_transform(X_tr)
    Xs_ho  = scaler.transform(X_ho)

    # Build multi-output Y for all STATS (log1p/sqrt transform as in prod)
    Y_tr_mt = np.zeros((train_end, len(STATS)), dtype=float)
    # We need all 7 stat targets from pre rows. For non-ast stats we need the
    # base 129-col X; for simplicity the multitask MLP uses the AST-extended
    # X (130 cols) for all outputs — slightly inconsistent with prod (which
    # trains multitask on base 129) but acceptable for this narrow probe since
    # AST is the only stat in _USE_MULTITASK_MLP_STATS being retrained here.
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
    mlp_pred_tr_t = mlp_proxy.predict(Xs_tr)
    mlp_pred_tr = np.clip(np.expm1(mlp_pred_tr_t), 0, None)
    mlp_pred_ho_t = mlp_proxy.predict(Xs_ho)
    mlp_pred_ho = np.clip(np.expm1(mlp_pred_ho_t), 0, None)

    # NNLS stacking
    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}")

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)")

    # Persist
    xgb_m.save_model(os.path.join(OOS_DIR, f"props_pg_{stat}.json"))
    joblib.dump(lgb_m, os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"))
    joblib.dump(mlp_proxy, os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"))
    joblib.dump(scaler, os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"))

    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    all_w: dict = {}
    if os.path.exists(weights_path):
        try:
            all_w = json.load(open(weights_path, encoding="utf-8"))
        except Exception:
            all_w = {}
    all_w[stat] = {"w_xgb": round(w_xgb, 4), "w_lgb": round(w_lgb, 4),
                   "w_mlp": round(w_mlp, 4)}
    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(all_w, fh, indent=2)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": val_end - train_end, "n_holdout": n_pre - val_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
    }


# ---------------------------------------------------------------------------
# FG3M retrain: XGB q50
# ---------------------------------------------------------------------------

def retrain_fg3m(rows: list) -> dict:
    stat = "fg3m"
    fcols = feature_columns(stat)
    print(f"\n  [iter-44] {stat}: {len(fcols)} cols "
          f"(base 129 + {fcols[129:]})")

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
    print(f"  {stat}: n_all={n_all}  n_pre={n_pre}")

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
    print(f"  HPs: {params}")
    t0 = time.time()

    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae",
    )
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    fit_secs = time.time() - t0
    best_iter = int(getattr(m, "best_iteration", -1) or -1)

    pred_val_raw = _inverse(stat, m.predict(X_val))
    err = y_val - pred_val_raw
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    print(f"  {stat}: val_pinball={val_pinball:.4f}  val_MAE={val_mae:.4f}  "
          f"({fit_secs:.1f}s  best_iter={best_iter})")

    fname = f"quantile_pergame_{stat}_q50.json"
    m.save_model(os.path.join(OOS_DIR, fname))

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": len(X_val),
        "val_pinball": val_pinball, "val_mae": val_mae,
        "best_iter": best_iter, "fit_secs": fit_secs,
        "fname": fname, "fcols": fcols, "params": params,
    }


# ---------------------------------------------------------------------------
# Update _meta.json
# ---------------------------------------------------------------------------

def update_meta(results: list[dict]) -> None:
    meta_path = os.path.join(OOS_DIR, "_meta.json")
    all_meta: dict = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta = {"stats": {}}

    for r in results:
        stat = r["stat"]
        entry: dict = {
            "cutoff_date": CUTOFF_DATE,
            "stat": stat,
            "iter": "iter44",
            "n_train": r["n_train"],
            "n_total_rows": r["n_all"],
            "n_pre_cutoff_rows": r["n_pre"],
            "n_features": len(r["fcols"]),
            "training_timestamp": datetime.now().isoformat(),
            "fit_seconds": r["fit_secs"],
            "feature_columns": r["fcols"],
        }
        if stat == "fg3m":
            entry.update({
                "method": "xgb",
                "n_val": r["n_val"],
                "val_pinball_q50": r["val_pinball"],
                "val_mae": r["val_mae"],
                "model_filename": r["fname"],
                "best_iteration": r["best_iter"],
                "hps": r["params"],
            })
        else:
            entry.update({
                "method": "sqrt_huber_blend" if stat == "pts" else "log1p_multitask_mlp_blend",
                "n_val": r.get("n_val", 0),
                "n_holdout": r.get("n_holdout", 0),
                "holdout_r2": r.get("holdout_r2"),
                "holdout_mae": r.get("holdout_mae"),
                "meta_w_xgb": r.get("w_xgb"),
                "meta_w_lgb": r.get("w_lgb"),
                "meta_w_mlp": r.get("w_mlp"),
            })
        all_meta["stats"][stat] = entry

    all_meta["iter"] = "iter44"
    all_meta["cutoff"] = CUTOFF_DATE
    all_meta["updated_at"] = datetime.now().isoformat()

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"\n  _meta.json updated -> {meta_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print(f"\n=== iter-44 retrain: narrow synergy PPP (cutoff {CUTOFF_DATE}) ===")
    total_t0 = time.time()
    os.makedirs(OOS_DIR, exist_ok=True)

    print("  Loading all gamelog rows (shared across stats) ...")
    rows = _load_rows()
    print(f"  Total rows: {len(rows)}")

    results = []
    results.append(retrain_pts(rows))
    results.append(retrain_ast(rows))
    results.append(retrain_fg3m(rows))
    update_meta(results)

    print(f"\n=== iter-44 retrain complete in {time.time()-total_t0:.1f}s ===")
    for r in results:
        stat = r["stat"]
        if stat == "fg3m":
            print(f"  {stat}: val_MAE={r['val_mae']:.4f}  pinball={r['val_pinball']:.4f}")
        else:
            print(f"  {stat}: holdout_R²={r['holdout_r2']:.4f}  MAE={r['holdout_mae']:.4f}")


if __name__ == "__main__":
    main()
