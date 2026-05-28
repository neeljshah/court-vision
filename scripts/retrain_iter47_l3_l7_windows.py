"""retrain_iter47_l3_l7_windows.py — Iter-47 OOS retrain: l3 + l7 rolling windows.

Probe: add l3_{stat} (3-game hot-streak) and l7_{stat} (mid-range trend) alongside
existing l5/l10/ewma for PTS, AST, and REB — the 3 stats with the most consistent
OOS edge per CLV analysis.

New feature counts:
  PTS : 129 → 131  (+l3_pts, +l7_pts)
  AST : 129 → 131  (+l3_ast, +l7_ast)
  REB : 132 → 134  (+l3_reb, +l7_reb)   [REB was 132 with oreb-context keys]

Methods (unchanged from production):
  PTS  — NNLS(XGB-sqrt+Huber, LGB-huber, MLP-5seed)
  AST  — NNLS(XGB-log1p, LGB-log1p, MultitaskMLP)
  REB  — LGB q50

Usage:
    python scripts/retrain_iter47_l3_l7_windows.py

Backup must be done BEFORE running. Script is idempotent (re-running overwrites
the same artifact paths).
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

# ── constants ──────────────────────────────────────────────────────────────────

CUTOFF_DATE = "2025-04-21"
OOS_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


# ── helpers ────────────────────────────────────────────────────────────────────

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


def _nnls_weights(preds_tr: list, y_tr: np.ndarray) -> np.ndarray:
    from scipy.optimize import nnls
    A = np.column_stack(preds_tr)
    w, _ = nnls(A, y_tr)
    s = w.sum()
    return w / s if s > 0 else np.ones(len(w)) / len(w)


def _top10_importances(model, fcols: list) -> list:
    """Return top-10 (feature_name, importance) pairs."""
    try:
        imps = model.feature_importances_
    except AttributeError:
        return []
    ranked = sorted(zip(fcols, imps), key=lambda x: x[1], reverse=True)
    return ranked[:10]


# ── PTS retrain ────────────────────────────────────────────────────────────────

def retrain_pts(rows: list) -> dict:
    stat = "pts"
    fcols = feature_columns(stat)
    print(f"\n  [iter-47] {stat}: {len(fcols)} cols  new={fcols[129:]}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
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

    # XGB sqrt+Huber
    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:pseudohubererror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(xgb_m.predict(X_tr), 0, None) ** 2
    xgb_pred_ho = np.clip(xgb_m.predict(X_ho), 0, None) ** 2

    # LGB huber
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

    # NNLS stacking
    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}", flush=True)

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)", flush=True)

    # Feature importance — top 10 from XGB (primary learner)
    top10_xgb = _top10_importances(xgb_m, fcols)
    print(f"  {stat} top-10 XGB importance:")
    for rank, (name, imp) in enumerate(top10_xgb, 1):
        marker = " <-- NEW" if name in (f"l3_{stat}", f"l7_{stat}") else ""
        print(f"    #{rank:2d}  {name:40s}  {imp:.4f}{marker}", flush=True)

    # Persist
    xgb_m.save_model(os.path.join(OOS_DIR, f"props_pg_{stat}.json"))
    joblib.dump(lgb_m, os.path.join(OOS_DIR, f"props_pg_lgb_{stat}.pkl"))
    joblib.dump(mlp, os.path.join(OOS_DIR, f"props_pg_mlp_{stat}.pkl"))
    joblib.dump(scaler, os.path.join(OOS_DIR, f"props_pg_mlp_scaler_{stat}.pkl"))

    weights_path = os.path.join(OOS_DIR, "meta_weights_pergame.json")
    all_w: dict = {}
    if os.path.exists(weights_path):
        try:
            all_w = json.load(open(weights_path, encoding="utf-8"))
        except Exception:
            all_w = {}
    all_w[stat] = {"w_xgb": round(w_xgb, 4), "w_lgb": round(w_lgb, 4), "w_mlp": round(w_mlp, 4)}
    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(all_w, fh, indent=2)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": val_end - train_end, "n_holdout": n_pre - val_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10_xgb": [(n, float(i)) for n, i in top10_xgb],
    }


# ── AST retrain ────────────────────────────────────────────────────────────────

def retrain_ast(rows: list) -> dict:
    stat = "ast"
    fcols = feature_columns(stat)
    print(f"\n  [iter-47] {stat}: {len(fcols)} cols  new={fcols[129:]}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
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

    # XGB log1p
    xgb_m = xgb.XGBRegressor(
        **params, random_state=42, objective="reg:squarederror",
        early_stopping_rounds=40, eval_metric="mae",
    )
    xgb_m.fit(X_tr, y_tr_t, eval_set=[(X_val, y_val_t)], sample_weight=sw, verbose=False)
    xgb_pred_tr = np.clip(np.expm1(xgb_m.predict(X_tr)), 0, None)
    xgb_pred_ho = np.clip(np.expm1(xgb_m.predict(X_ho)), 0, None)

    # LGB log1p
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

    # Multitask MLP
    scaler = StandardScaler()
    Xs_tr = scaler.fit_transform(X_tr)
    Xs_ho  = scaler.transform(X_ho)

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

    # NNLS
    w = _nnls_weights([xgb_pred_tr, lgb_pred_tr, mlp_pred_tr], y_tr)
    w_xgb, w_lgb, w_mlp = float(w[0]), float(w[1]), float(w[2])
    print(f"  {stat} NNLS: xgb={w_xgb:.3f}  lgb={w_lgb:.3f}  mlp={w_mlp:.3f}", flush=True)

    pred_ho = w_xgb * xgb_pred_ho + w_lgb * lgb_pred_ho + w_mlp * mlp_pred_ho
    ho_r2  = float(r2_score(y_ho, pred_ho))
    ho_mae = float(mean_absolute_error(y_ho, pred_ho))
    fit_secs = time.time() - t0
    print(f"  {stat}: holdout R²={ho_r2:.4f}  MAE={ho_mae:.4f}  ({fit_secs:.1f}s)", flush=True)

    # Feature importance — top 10 from XGB
    top10_xgb = _top10_importances(xgb_m, fcols)
    print(f"  {stat} top-10 XGB importance:")
    for rank, (name, imp) in enumerate(top10_xgb, 1):
        marker = " <-- NEW" if name in (f"l3_{stat}", f"l7_{stat}") else ""
        print(f"    #{rank:2d}  {name:40s}  {imp:.4f}{marker}", flush=True)

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
    all_w[stat] = {"w_xgb": round(w_xgb, 4), "w_lgb": round(w_lgb, 4), "w_mlp": round(w_mlp, 4)}
    with open(weights_path, "w", encoding="utf-8") as fh:
        json.dump(all_w, fh, indent=2)

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": val_end - train_end, "n_holdout": n_pre - val_end,
        "holdout_r2": ho_r2, "holdout_mae": ho_mae,
        "w_xgb": w_xgb, "w_lgb": w_lgb, "w_mlp": w_mlp,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10_xgb": [(n, float(i)) for n, i in top10_xgb],
    }


# ── REB retrain ─────────────────────────────────────────────────────────────────

def retrain_reb(rows: list) -> dict:
    stat = "reb"
    fcols = feature_columns(stat)
    print(f"\n  [iter-47] {stat}: {len(fcols)} cols  new_extras={fcols[129:]}", flush=True)

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre = _filter_and_sort(rows, cutoff)
    n_all = len(rows)
    n_pre = len(pre)
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

    pred_val_t = np.array(m.predict(X_val), dtype=float)
    pred_val = _inverse(stat, pred_val_t)
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val), -0.5 * (y_val - pred_val))))
    val_mae = float(mean_absolute_error(y_val, pred_val))
    print(f"  {stat}: val_pinball={val_pinball:.4f}  val_MAE={val_mae:.4f}  "
          f"({fit_secs:.1f}s  best_iter={getattr(m, 'best_iteration_', -1)})", flush=True)

    # Feature importance — top 10
    top10 = _top10_importances(m, fcols)
    print(f"  {stat} top-10 LGB importance:")
    for rank, (name, imp) in enumerate(top10, 1):
        marker = " <-- NEW" if name in (f"l3_{stat}", f"l7_{stat}") else ""
        print(f"    #{rank:2d}  {name:40s}  {imp:.1f}{marker}", flush=True)

    # Persist
    joblib.dump(m, os.path.join(OOS_DIR, "quantile_pergame_lgb_reb_q50.pkl"))

    return {
        "stat": stat, "n_all": n_all, "n_pre": n_pre,
        "n_train": train_end, "n_val": n_pre - train_end,
        "val_pinball": val_pinball, "val_mae": val_mae,
        "fit_secs": fit_secs, "fcols": fcols,
        "top10": [(n, float(i)) for n, i in top10],
    }


# ── _meta.json update ──────────────────────────────────────────────────────────

def update_meta(results: list) -> None:
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
        base: dict = {
            "cutoff_date": CUTOFF_DATE,
            "stat": stat,
            "iter": "iter47",
            "n_train": r["n_train"],
            "n_total_rows": r["n_all"],
            "n_pre_cutoff_rows": r["n_pre"],
            "n_features": len(r["fcols"]),
            "training_timestamp": datetime.now().isoformat(),
            "fit_seconds": r["fit_secs"],
            "feature_columns": r["fcols"],
        }
        if stat == "reb":
            base.update({
                "method": "lgb_q50",
                "n_val": r["n_val"],
                "val_pinball_q50": r["val_pinball"],
                "val_mae": r["val_mae"],
                "model_filename": "quantile_pergame_lgb_reb_q50.pkl",
                "top10_importance": r["top10"],
            })
        else:
            base.update({
                "method": "sqrt_huber_blend" if stat == "pts" else "log1p_multitask_mlp_blend",
                "n_val": r.get("n_val", 0),
                "n_holdout": r.get("n_holdout", 0),
                "holdout_r2": r.get("holdout_r2"),
                "holdout_mae": r.get("holdout_mae"),
                "meta_w_xgb": r.get("w_xgb"),
                "meta_w_lgb": r.get("w_lgb"),
                "meta_w_mlp": r.get("w_mlp"),
                "top10_xgb_importance": r.get("top10_xgb"),
            })
        all_meta["stats"][stat] = base

    all_meta["iter"] = "iter47"
    all_meta["cutoff"] = CUTOFF_DATE
    all_meta["updated_at"] = datetime.now().isoformat()

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"\n  _meta.json updated -> {meta_path}", flush=True)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n=== iter-47 retrain: l3 + l7 windows for PTS/AST/REB (cutoff {CUTOFF_DATE}) ===",
          flush=True)
    total_t0 = time.time()
    os.makedirs(OOS_DIR, exist_ok=True)

    print("  Loading gamelog rows (shared) ...", flush=True)
    rows = _load_rows()
    print(f"  Total rows: {len(rows)}", flush=True)

    results = []
    results.append(retrain_pts(rows))
    results.append(retrain_ast(rows))
    results.append(retrain_reb(rows))
    update_meta(results)

    elapsed = time.time() - total_t0
    print(f"\n=== iter-47 retrain complete in {elapsed:.1f}s ===", flush=True)
    for r in results:
        stat = r["stat"]
        if stat == "reb":
            print(f"  {stat}: val_MAE={r['val_mae']:.4f}  pinball={r['val_pinball']:.4f}",
                  flush=True)
        else:
            print(f"  {stat}: holdout_R²={r['holdout_r2']:.4f}  MAE={r['holdout_mae']:.4f}",
                  flush=True)


if __name__ == "__main__":
    main()
