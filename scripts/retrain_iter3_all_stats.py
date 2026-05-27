"""retrain_iter3_all_stats.py — Iter-3 OOS retrain for all 7 stats with 129-col features.

Retrains:
  PTS  (sqrt+Huber blend)
  AST  (log1p multitask MLP blend)
  REB  (LGB-q50)
  FG3M / STL / BLK / TOV  (XGB-q50)

Uses the iter-3 feature set (109 baseline + 20 new = 129 cols):
  A: ref_l5_fouls, ref_l5_fta, ref_fouls_z, ref_fta_z, ref_home_advantage
  B: foul_pf36_l5, foul_pf36_l10, foul_trouble_l10, foul_last_pf, foul_min_l5
  C: dnp_in_game, dnp_l5_avg, dnp_l10_avg, dnp_prior_game
  D: adv_usage_std, adv_ts_std, adv_efg_std, adv_usage_vs_opp_l3, adv_ts_vs_opp_l3, adv_usage_z

Writes to data/models/oos_pre_playoffs/ with feature_columns in _meta.json.
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

import src.prediction.prop_pergame as pg

CUTOFF_DATE = "2024-04-21"
OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")

Q50_STATS_LGB = {"reb"}
Q50_STATS_XGB = {"blk", "fg3m", "stl", "tov"}
BLEND_STATS_PTS = {"pts"}
BLEND_STATS_AST = {"ast"}

_PRE_ROWS_CACHE = None


def _get_pre_rows():
    global _PRE_ROWS_CACHE
    if _PRE_ROWS_CACHE is not None:
        return _PRE_ROWS_CACHE
    print("  Building dataset (call 1)...")
    rows, fcols = pg.build_pergame_dataset()
    n_all = len(rows)
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    print(f"  n_all={n_all}  n_pre_cutoff={len(pre_rows)}  n_fcols={len(fcols)}")
    _PRE_ROWS_CACHE = (pre_rows, fcols, n_all)
    return _PRE_ROWS_CACHE


def _recency_weights(dates, n_train: int) -> np.ndarray:
    max_d = max(dates[:n_train])
    age = np.array([(max_d - d).days / 365.0 for d in dates[:n_train]], dtype=float)
    return np.exp(-0.5 * age)


def retrain_q50(stat: str) -> dict:
    from sklearn.metrics import mean_absolute_error
    from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params

    pre_rows, fcols, n_all = _get_pre_rows()
    method = "lgb" if stat in Q50_STATS_LGB else "xgb"
    print(f"\n  [{stat}] method={method}  n_cols={len(fcols)}")
    t0 = time.time()

    n_pre = len(pre_rows)
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[r[c] for c in fcols] for r in pre_rows], dtype=float)
    # Iter-5: NaN-fill using per-column train-split medians (XGB/LGB handle
    # NaN natively, but fill here for uniform treatment + future MLP probes).
    _nan_mask = ~np.isfinite(X_all)
    if _nan_mask.any():
        _col_med = np.nanmedian(X_all[:train_end], axis=0)
        _col_med = np.where(np.isfinite(_col_med), _col_med, 0.0)
        for _ci in range(X_all.shape[1]):
            _cm = _nan_mask[:, _ci]
            if _cm.any():
                X_all[_cm, _ci] = _col_med[_ci]
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(n_pre)]
    sw = _recency_weights(dates, train_end)
    y = np.array([r[f"target_{stat}"] for r in pre_rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)
    params = _per_stat_xgb_params(stat)

    if method == "lgb":
        import lightgbm as lgb
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
        best_iter = int(getattr(m, "best_iteration_", -1) or -1)
        import joblib
        fname = f"quantile_pergame_lgb_{stat}_q50.pkl"
        joblib.dump(m, os.path.join(OOS_MODEL_DIR, fname))
    else:
        import xgboost as xgb
        m = xgb.XGBRegressor(
            **{k: v for k, v in params.items() if k != "random_state"},
            random_state=42, objective="reg:quantileerror", quantile_alpha=0.5,
            early_stopping_rounds=40, eval_metric="mae",
        )
        m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
        best_iter = int(getattr(m, "best_iteration", -1) or -1)
        fname = f"quantile_pergame_{stat}_q50.json"
        m.save_model(os.path.join(OOS_MODEL_DIR, fname))

    pred_val_raw = _inverse(stat, m.predict(X_val))
    val_pinball = float(np.mean(np.maximum(0.5 * (y_val - pred_val_raw),
                                           -0.5 * (y_val - pred_val_raw))))
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    fit_secs = time.time() - t0
    print(f"  [{stat}] val_pinball={val_pinball:.4f}  val_mae={val_mae:.4f}  fit={fit_secs:.1f}s")
    return {
        "cutoff_date": CUTOFF_DATE, "stat": stat, "method": method,
        "n_train": train_end, "n_val": n_pre - train_end,
        "val_pinball_q50": val_pinball, "val_mae": val_mae,
        "model_filename": fname,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs, "best_iteration": best_iter,
        "n_features": len(fcols), "hps": params,
        "n_total_rows": n_all, "n_pre_cutoff_rows": n_pre,
        "feature_columns": fcols,
    }


def retrain_blend(stat: str) -> dict:
    pre_rows, fcols, n_all = _get_pre_rows()
    print(f"\n  [{stat}] blend retrain  n_cols={len(fcols)}")
    t0 = time.time()
    original_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    n_holders = {"n_all": n_all, "n_pre": len(pre_rows)}

    def _filtered_build(gamelog_dir=None, **kw):
        rows, fcols2 = original_build(gamelog_dir, **kw)
        n_holders["n_all"] = len(rows)
        filtered = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
        n_holders["n_pre"] = len(filtered)
        return filtered, fcols2

    pg.build_pergame_dataset = _filtered_build
    try:
        metrics = pg.train_pergame_models(model_dir=OOS_MODEL_DIR, stats=[stat])
    finally:
        pg.build_pergame_dataset = original_build

    sm = (metrics.get("stats") or {}).get(stat, {})
    fit_secs = time.time() - t0
    val_mae = float(sm.get("holdout_mae") or sm.get("val_mae") or 0.0)
    print(f"  [{stat}] holdout_mae={val_mae:.4f}  fit={fit_secs:.1f}s")

    method_map = {
        "pts": "sqrt_huber_blend",
        "ast": "log1p_multitask_mlp_blend",
    }
    return {
        "cutoff_date": CUTOFF_DATE, "stat": stat,
        "method": method_map.get(stat, "blend"),
        "n_train": metrics.get("n_train", 0),
        "n_val": metrics.get("n_val", 0),
        "n_holdout": metrics.get("n_holdout", 0),
        "val_mae": val_mae,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs,
        "n_features": len(fcols),
        "n_total_rows": n_holders["n_all"],
        "n_pre_cutoff_rows": n_holders["n_pre"],
        "holdout_r2": float(sm.get("holdout_r2") or 0.0),
        "holdout_mae": val_mae,
        "feature_columns": fcols,
        **({"meta_w_xgb": sm.get("meta_w_xgb"),
            "meta_w_lgb": sm.get("meta_w_lgb"),
            "meta_w_mlp": sm.get("meta_w_mlp")} if stat == "pts" else {}),
    }


def main() -> None:
    os.makedirs(OOS_MODEL_DIR, exist_ok=True)
    t_global = time.time()
    print(f"=== Iter-3 OOS retrain (cutoff < {CUTOFF_DATE}) ===")

    meta_path = os.path.join(OOS_MODEL_DIR, "_meta.json")
    all_meta: dict = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta = {"stats": {}}

    results: dict = {}

    # --- q50 stats: reb, fg3m, stl, blk, tov ---
    for stat in ["reb", "fg3m", "stl", "blk", "tov"]:
        try:
            r = retrain_q50(stat)
            all_meta["stats"][stat] = r
            results[stat] = r
        except Exception as exc:
            print(f"  [WARN] {stat} retrain failed: {exc}")

    # --- blend stats: pts ---
    for stat in ["pts"]:
        try:
            r = retrain_blend(stat)
            all_meta["stats"][stat] = r
            results[stat] = r
        except Exception as exc:
            print(f"  [WARN] {stat} retrain failed: {exc}")

    # --- blend stats: ast ---
    for stat in ["ast"]:
        try:
            r = retrain_blend(stat)
            all_meta["stats"][stat] = r
            results[stat] = r
        except Exception as exc:
            print(f"  [WARN] {stat} retrain failed: {exc}")

    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"\nMeta written -> {meta_path}")

    print("\n=== ITER-3 PRE/POST MAE SUMMARY ===")
    baseline = {
        "pts":  4.4868, "reb": 1.9023, "ast": 1.3368,
        "fg3m": 0.8943, "stl": 0.6195, "blk": 0.4540, "tov": 0.8189,
    }
    for s in ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]:
        r = results.get(s, {})
        mae_new = r.get("val_mae") or r.get("holdout_mae") or 0.0
        mae_old = baseline.get(s, 0.0)
        delta = mae_new - mae_old
        sign = "-" if delta < 0 else "+"
        print(f"  {s:4s}: baseline={mae_old:.4f}  new={mae_new:.4f}  delta={sign}{abs(delta):.4f}")

    print(f"\nTotal time: {time.time() - t_global:.1f}s")
    print("DONE.")


if __name__ == "__main__":
    main()
