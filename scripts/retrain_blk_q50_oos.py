"""retrain_blk_q50_oos.py — iter-6 OOS retrain of BLK q50 strictly before 2024 playoffs.

Filters the prop_pergame dataset to rows with date < 2024-04-21 (start of 2024
NBA playoffs), retrains ONLY the XGB-q50 BLK head with the same per-stat HPs
and recency-weighted sample weights as the production train_quantile_models,
and writes the artifact to a NEW directory data/models/oos_pre_playoffs/ so the
production artifact is never overwritten.

Why BLK only:
  - smallest MAE on disk (0.44) so changes are highly observable
  - fastest single-stat train (~30s on local)
  - iter-4 backtest showed BLK at +29.4% ROI on 59 bets, biggest in-sample edge

Output:
  data/models/oos_pre_playoffs/quantile_pergame_blk_q50.json   (XGB artifact)
  data/models/oos_pre_playoffs/_meta.json                       (training metadata)
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

from src.prediction.prop_quantiles import (  # noqa: E402
    _transform,
    _inverse,
    _per_stat_xgb_params,
)
from src.prediction.prop_pergame import build_pergame_dataset  # noqa: E402


CUTOFF_DATE = "2024-04-21"  # start of 2024 NBA playoffs (first round)
STAT = "blk"
OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


def main() -> None:
    import xgboost as xgb
    from sklearn.metrics import mean_absolute_error

    os.makedirs(OOS_MODEL_DIR, exist_ok=True)
    t0 = time.time()

    print(f"  Building per-game dataset (loading ALL gamelogs)...")
    rows, fcols = build_pergame_dataset(None)
    n_all = len(rows)
    print(f"  Total per-game rows: {n_all}")

    # Filter strictly before cutoff.
    cutoff = datetime.fromisoformat(CUTOFF_DATE)
    pre_rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
    pre_rows.sort(key=lambda r: r["date"])
    n_pre = len(pre_rows)
    print(f"  Rows strictly before {CUTOFF_DATE}: {n_pre}  ({n_pre / n_all * 100:.1f}% of full set)")
    if n_pre < 200:
        raise SystemExit(f"  [abort] only {n_pre} pre-cutoff rows — refuse to train")

    # Internal val split — no holdout (OOS evaluation happens via the separate backtest).
    val_frac = 0.15
    train_end = int(n_pre * (1.0 - val_frac))
    X_all = np.array([[r[c] for c in fcols] for r in pre_rows], dtype=float)
    X_tr = X_all[:train_end]
    X_val = X_all[train_end:]
    n_train, n_val = len(X_tr), len(X_val)
    print(f"  Train rows: {n_train}  | Val rows: {n_val}")

    # Recency sample weights (mirror prop_quantiles lines 121-124).
    train_dates = [datetime.fromisoformat(pre_rows[i]["date"]) for i in range(train_end)]
    max_d = max(train_dates)
    age = np.array([(max_d - d).days / 365.0 for d in train_dates], dtype=float)
    sw = np.exp(-0.5 * age)

    # BLK target + log1p transform.
    y = np.array([r[f"target_{STAT}"] for r in pre_rows], dtype=float)
    y_tr, y_val = y[:train_end], y[train_end:]
    yt_tr = _transform(STAT, y_tr)
    yt_val = _transform(STAT, y_val)

    # Per-stat HP block — same regularisation as production.
    params = _per_stat_xgb_params(STAT)
    print(f"  HPs (blk): {params}")

    m = xgb.XGBRegressor(
        **{k: v for k, v in params.items() if k != "random_state"},
        random_state=42,
        objective="reg:quantileerror",
        quantile_alpha=0.5,
        early_stopping_rounds=40,
        eval_metric="mae",
    )
    fit_t0 = time.time()
    m.fit(X_tr, yt_tr, eval_set=[(X_val, yt_val)], sample_weight=sw, verbose=False)
    fit_secs = time.time() - fit_t0
    print(f"  XGB-q50 fit done in {fit_secs:.1f}s  (best_iter={m.best_iteration})")

    # Val metrics: pinball@0.5 + MAE on raw-count scale.
    pred_val_raw = _inverse(STAT, m.predict(X_val))
    err = y_val - pred_val_raw
    val_pinball = float(np.mean(np.maximum(0.5 * err, -0.5 * err)))  # q=0.5 pinball == 0.5 * MAE
    val_mae = float(mean_absolute_error(y_val, pred_val_raw))
    print(f"  Val pinball@0.5 (raw-scale): {val_pinball:.4f}")
    print(f"  Val MAE (raw-scale):         {val_mae:.4f}")

    # Persist OOS artifact + metadata.
    model_filename = f"quantile_pergame_{STAT}_q50.json"
    out_path = os.path.join(OOS_MODEL_DIR, model_filename)
    m.save_model(out_path)
    print(f"  Saved -> {out_path}")

    meta = {
        "cutoff_date": CUTOFF_DATE,
        "stat": STAT,
        "n_train": n_train,
        "n_val": n_val,
        "val_pinball_q50": val_pinball,
        "val_mae": val_mae,
        "model_filename": model_filename,
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": fit_secs,
        "best_iteration": int(getattr(m, "best_iteration", -1) or -1),
        "n_features": len(fcols),
        "hps": params,
        "n_total_rows": n_all,
        "n_pre_cutoff_rows": n_pre,
    }
    meta_path = os.path.join(OOS_MODEL_DIR, "_meta.json")
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    print(f"  Meta  -> {meta_path}")

    total_secs = time.time() - t0
    print(f"\n  Summary:")
    print(f"    cutoff:      {CUTOFF_DATE}")
    print(f"    n_train:     {n_train}")
    print(f"    n_val:       {n_val}")
    print(f"    val_pinball: {val_pinball:.4f}")
    print(f"    val_MAE:     {val_mae:.4f}")
    print(f"    train_time:  {fit_secs:.1f}s  (total script {total_secs:.1f}s)")


if __name__ == "__main__":
    main()
