"""retrain_qstat_q50_oos.py - iter-7 generalized OOS retrain for q50 stats.

Filters prop_pergame to rows with date < 2024-04-21, retrains the q50 head
for one stat with same HPs+sample weights as production train_quantile_models.
Writes to data/models/oos_pre_playoffs/ (production untouched).

REB -> LGB-q50 (cycle 29). FG3M/STL/BLK/TOV -> XGB-q50.
Usage: python scripts/retrain_qstat_q50_oos.py --stat reb
"""
from __future__ import annotations

import argparse, json, os, sys, time, warnings
from datetime import datetime
import numpy as np

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_quantiles import _transform, _inverse, _per_stat_xgb_params
from src.prediction.prop_pergame import build_pergame_dataset


CUTOFF_DATE = "2024-04-21"
DEFAULT_OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")
LGB_STATS = {"reb"}
XGB_STATS = {"blk", "fg3m", "stl", "tov"}


def _train_xgb(X_tr, X_val, yt_tr, yt_val, sw, params, seed=42):
    import xgboost as xgb
    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=seed, objective="reg:quantileerror", quantile_alpha=0.5,
        early_stopping_rounds=40, eval_metric="mae",
    )
    t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    return m, time.time() - t0, int(getattr(m, "best_iteration", -1) or -1)


def _train_lgb(X_tr, X_val, yt_tr, yt_val, sw, params, seed=42):
    import lightgbm as lgb
    m = lgb.LGBMRegressor(
        n_estimators=params["n_estimators"], max_depth=params["max_depth"],
        learning_rate=params["learning_rate"],
        subsample=params["subsample"], subsample_freq=1,
        colsample_bytree=params["colsample_bytree"],
        min_child_samples=max(20, params["min_child_weight"] * 2),
        reg_lambda=params["reg_lambda"], reg_alpha=params["reg_alpha"],
        random_state=seed, objective="quantile", alpha=0.5,
        n_jobs=-1, verbosity=-1,
    )
    t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw,
          callbacks=[lgb.early_stopping(40, verbose=False)])
    return m, time.time() - t0, int(getattr(m, "best_iteration_", -1) or -1)


def _save_model(stat, model, out_dir):
    if stat in LGB_STATS:
        import joblib
        fname = f"quantile_pergame_lgb_{stat}_q50.pkl"
        path = os.path.join(out_dir, fname)
        joblib.dump(model, path)
    else:
        fname = f"quantile_pergame_{stat}_q50.json"
        path = os.path.join(out_dir, fname)
        model.save_model(path)
    return fname, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stat", required=True, choices=sorted(LGB_STATS | XGB_STATS))
    ap.add_argument("--seed", type=int, default=42,
                    help="Random seed for model training (default: 42)")
    ap.add_argument("--out-dir", default=None,
                    help="Override output directory. Default uses seed in name "
                         "for non-42 seeds.")
    args = ap.parse_args()
    stat = args.stat
    seed = args.seed
    method = "lgb" if stat in LGB_STATS else "xgb"

    if args.out_dir:
        out_dir = args.out_dir
    elif seed == 42:
        out_dir = DEFAULT_OOS_MODEL_DIR
    else:
        out_dir = os.path.join(PROJECT_DIR, "data", "models",
                               f"oos_pre_playoffs_seed{seed}")

    from sklearn.metrics import mean_absolute_error
    os.makedirs(out_dir, exist_ok=True)
    print(f"  [seed={seed}] [out_dir={out_dir}]")
    t0 = time.time()

    print(f"  [stat={stat}] method={method}")
    rows, fcols = build_pergame_dataset(None)
    n_all = len(rows)
    print(f"  Total rows: {n_all}")

    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    n_pre = len(pre_rows)
    print(f"  Pre-cutoff: {n_pre}  ({n_pre/n_all*100:.1f}%)")
    if n_pre < 200:
        raise SystemExit(f"  [abort] only {n_pre} pre-cutoff rows")

    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[r[c] for c in fcols] for r in pre_rows], dtype=float)
    X_tr, X_val = X_all[:train_end], X_all[train_end:]
    n_train, n_val = len(X_tr), len(X_val)
    print(f"  Train: {n_train} | Val: {n_val}")

    train_dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    y = np.array([r[f"target_{stat}"] for r in pre_rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(stat, y_tr)
    yt_val = _transform(stat, y_val)

    params = _per_stat_xgb_params(stat)
    print(f"  HPs: {params}")

    if method == "lgb":
        m, fit_secs, best_iter = _train_lgb(X_tr, X_val, yt_tr, yt_val, sw, params, seed=seed)
    else:
        m, fit_secs, best_iter = _train_xgb(X_tr, X_val, yt_tr, yt_val, sw, params, seed=seed)
    print(f"  Fit: {fit_secs:.1f}s (best_iter={best_iter})")

    pred_val_t = m.predict(X_val)
    pred_val_raw = _inverse(stat, pred_val_t)
    err = y_val - pred_val_raw
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    print(f"  val_pinball@0.5: {val_pinball:.4f}")
    print(f"  val_MAE (raw):   {val_mae:.4f}")

    fname, path = _save_model(stat, m, out_dir)
    print(f"  Saved -> {path}")

    meta_path = os.path.join(out_dir, "_meta.json")
    all_meta = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}

    if "cutoff_date" in all_meta and "stat" in all_meta and "stats" not in all_meta:
        existing_stat = all_meta.get("stat", "blk")
        legacy = {k: v for k, v in all_meta.items() if k != "stats"}
        all_meta = {"stats": {existing_stat: legacy}}
    elif "stats" not in all_meta:
        all_meta = {"stats": {}}

    all_meta["stats"][stat] = {
        "cutoff_date": CUTOFF_DATE, "stat": stat, "method": method,
        "seed": seed,
        "n_train": n_train, "n_val": n_val,
        "val_pinball_q50": val_pinball, "val_mae": val_mae,
        "model_filename": fname,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs, "best_iteration": best_iter,
        "n_features": len(fcols), "hps": params,
        "n_total_rows": n_all, "n_pre_cutoff_rows": n_pre,
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"  Meta -> {meta_path}")
    print(f"  Done in {time.time() - t0:.1f}s.")


if __name__ == "__main__":
    main()
