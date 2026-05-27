"""retrain_pts_oos.py - iter-8 OOS retrain of PTS sqrt+Huber blend before 2024 playoffs.

Filters the prop_pergame dataset to rows with date < 2024-04-21 and retrains
the production PTS 3-way blend (XGB pseudohuber + LGB huber + MLP 5-seed +
NNLS stacking on sqrt-transformed target) with the same per-stat HPs and
recency-weighted sample weights as src.prediction.prop_pergame.train_pergame_models.

The original sqrt+Huber recipe lives in prop_pergame.py (lines 2389-2542,
the loop body for stat='pts' inside train_pergame_models). We import that
function verbatim and rely on its full machinery, but to keep this OOS
artifact isolated we monkey-patch the dataset cutoff via a local copy of the
data preparation loop (everything in train_pergame_models above the per-stat
training loop). The per-stat training block is then invoked directly.

To avoid re-implementing 300 lines we use a different path: we call
train_pergame_models(stats=['pts']) inside a temp model_dir, but FIRST
monkey-patch build_pergame_dataset to filter rows < CUTOFF_DATE. We restore
it afterward. This keeps the trained blend identical to production.

Output:
  data/models/oos_pre_playoffs/props_pg_pts.json              (XGB)
  data/models/oos_pre_playoffs/props_pg_lgb_pts.pkl           (LGB)
  data/models/oos_pre_playoffs/props_pg_mlp_pts.pkl           (MLP 5-seed)
  data/models/oos_pre_playoffs/props_pg_mlp_scaler_pts.pkl    (MLP scaler)
  data/models/oos_pre_playoffs/calibration_pergame_pts.joblib (optional)
  data/models/oos_pre_playoffs/meta_weights_pergame.json      (NNLS weights)
  data/models/oos_pre_playoffs/_meta.json                     (pts key)
"""
from __future__ import annotations

import json
import os
import sys
import time
import warnings
from datetime import datetime

warnings.filterwarnings("ignore")

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import src.prediction.prop_pergame as pg  # noqa: E402


CUTOFF_DATE = "2024-04-21"
STAT = "pts"
OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


def main() -> None:
    os.makedirs(OOS_MODEL_DIR, exist_ok=True)
    t0 = time.time()

    # Wrap build_pergame_dataset so train_pergame_models gets only pre-cutoff
    # rows but the full feature_cols list and join logic stays identical to
    # production. We monkey-patch the module-level symbol that
    # train_pergame_models reads (it does `rows, feature_cols =
    # build_pergame_dataset(...)`).
    original_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(CUTOFF_DATE)

    n_total_holder = {"n_all": 0, "n_pre": 0}

    def _filtered_build(gamelog_dir=None, **kw):
        rows, fcols = original_build(gamelog_dir, **kw)
        n_total_holder["n_all"] = len(rows)
        rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
        n_total_holder["n_pre"] = len(rows)
        return rows, fcols

    print(f"  iter-8 OOS PTS retrain (sqrt+Huber blend, cutoff < {CUTOFF_DATE})")
    print(f"  Monkey-patching build_pergame_dataset for pre-cutoff filter...")
    pg.build_pergame_dataset = _filtered_build
    try:
        metrics = pg.train_pergame_models(
            model_dir=OOS_MODEL_DIR,
            stats=[STAT],
        )
    finally:
        pg.build_pergame_dataset = original_build

    elapsed_train = time.time() - t0
    print(f"  train_pergame_models([pts]) done in {elapsed_train:.1f}s")
    print(f"  n_all={n_total_holder['n_all']}  n_pre_cutoff={n_total_holder['n_pre']}")

    if metrics.get("status") == "insufficient_data":
        raise SystemExit(f"  [abort] insufficient_data ({metrics.get('n_rows')})")

    pts_m = metrics.get("stats", {}).get(STAT, {})
    print(f"  PTS holdout R²={pts_m.get('holdout_r2')}  MAE={pts_m.get('holdout_mae')}")
    print(f"  base R²: xgb={pts_m.get('xgb_holdout_r2')}  "
          f"lgb={pts_m.get('lgb_holdout_r2')}  mlp={pts_m.get('mlp_holdout_r2')}")
    print(f"  NNLS weights: xgb={pts_m.get('meta_w_xgb')}  "
          f"lgb={pts_m.get('meta_w_lgb')}  mlp={pts_m.get('meta_w_mlp')}  "
          f"src={pts_m.get('meta_fit_source')}")
    print(f"  calibration used: {pts_m.get('calibration_used')}  "
          f"lift_mae={pts_m.get('calibration_lift_mae')}")

    # Merge into the shared _meta.json so iter-7/8 share the same convention.
    meta_path = os.path.join(OOS_MODEL_DIR, "_meta.json")
    all_meta = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta = {"stats": {}}

    n_train_holdout_val = metrics.get("n_train", 0)
    n_val_full = metrics.get("n_val", 0)
    n_holdout = metrics.get("n_holdout", 0)

    all_meta["stats"][STAT] = {
        "cutoff_date": CUTOFF_DATE,
        "stat": STAT,
        "method": "sqrt_huber_blend",
        "n_train": n_train_holdout_val,
        "n_val": n_val_full,
        "n_holdout": n_holdout,
        "val_mae": float(pts_m.get("holdout_mae") or 0.0),
        "model_filename": "props_pg_pts.json (+ lgb/mlp/scaler/cal)",
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": float(elapsed_train),
        "n_features": len(metrics.get("feature_cols") or []),
        "n_total_rows": n_total_holder["n_all"],
        "n_pre_cutoff_rows": n_total_holder["n_pre"],
        "holdout_r2": float(pts_m.get("holdout_r2") or 0.0),
        "holdout_mae": float(pts_m.get("holdout_mae") or 0.0),
        "uncal_holdout_mae": float(pts_m.get("uncal_holdout_mae") or 0.0),
        "calibration_used": bool(pts_m.get("calibration_used") or False),
        "calibration_lift_mae": float(pts_m.get("calibration_lift_mae") or 0.0),
        "meta_w_xgb": float(pts_m.get("meta_w_xgb") or 0.0),
        "meta_w_lgb": float(pts_m.get("meta_w_lgb") or 0.0),
        "meta_w_mlp": float(pts_m.get("meta_w_mlp") or 0.0),
        "meta_fit_source": pts_m.get("meta_fit_source"),
        "xgb_holdout_r2": float(pts_m.get("xgb_holdout_r2") or 0.0),
        "lgb_holdout_r2": float(pts_m.get("lgb_holdout_r2") or 0.0),
        "mlp_holdout_r2": float(pts_m.get("mlp_holdout_r2") or 0.0),
        "hps": {
            "max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
            "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
            "colsample_bytree": 0.9, "reg_alpha": 2.0,
            "target_transform": "sqrt",
            "xgb_objective": "reg:pseudohubererror",
            "lgb_objective": "huber",
            "stacker": "NNLS_3way_on_raw_target",
            "recency_decay": 0.5,
            "mlp_hidden": [128, 64], "mlp_seeds": 5,
        },
    }
    with open(meta_path, "w", encoding="utf-8") as fh:
        json.dump(all_meta, fh, indent=2)
    print(f"  Meta -> {meta_path}")

    total = time.time() - t0
    print(f"\n  Summary:")
    print(f"    cutoff:        {CUTOFF_DATE}")
    print(f"    n_pre_cutoff:  {n_total_holder['n_pre']}")
    print(f"    n_train/val/holdout: {n_train_holdout_val}/{n_val_full}/{n_holdout}")
    print(f"    holdout_R²:    {pts_m.get('holdout_r2')}")
    print(f"    holdout_MAE:   {pts_m.get('holdout_mae')}")
    print(f"    total time:    {total:.1f}s")


if __name__ == "__main__":
    main()
