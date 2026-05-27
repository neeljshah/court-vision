"""retrain_ast_oos.py - iter-9 OOS retrain of AST multitask MLP blend before 2024 playoffs.

AST is the last of the 7 prop stats to OOS-validate. Per src.prediction.prop_pergame:
  - AST is in _LOG_TRANSFORM_STATS  => target = log1p(y), base learners predict log-space
  - AST is in _USE_MULTITASK_MLP_STATS = {ast, stl}  => MLP is a _MultitaskMLPProxy
    over a shared 5-seed multi-output MLP trained on ALL 7 stats' targets jointly.
  - AST is NOT in _USE_Q50_STATS    => prediction dispatches to the 3-way blend
    (XGB + LGB + multitask-MLP-proxy) via NNLS-fit weights, isotonic calibration optional.
  - AST IS in _GARBAGE_HAIRCUT_STATS => apply_garbage_time_haircut applies on inference.

We mirror scripts/retrain_pts_oos.py: monkey-patch build_pergame_dataset to filter rows
to date < 2024-04-21, then call train_pergame_models(stats=['ast']). That triggers the
multitask MLP block (line 2367) because 'ast' ∈ _USE_MULTITASK_MLP_STATS, so the MLP
gets trained ONCE on (n_train, 7) target matrix with per-stat transforms applied
column-wise — exactly the production path.

Output:
  data/models/oos_pre_playoffs/props_pg_ast.json              (XGB, squared-error on log1p)
  data/models/oos_pre_playoffs/props_pg_lgb_ast.pkl           (LGB, regression on log1p)
  data/models/oos_pre_playoffs/props_pg_mlp_ast.pkl           (_MultitaskMLPProxy)
  data/models/oos_pre_playoffs/props_pg_mlp_scaler_ast.pkl    (shared multitask scaler)
  data/models/oos_pre_playoffs/calibration_pergame_ast.joblib (optional, iff MAE lift)
  data/models/oos_pre_playoffs/meta_weights_pergame.json      (NNLS weights merged in)
  data/models/oos_pre_playoffs/_meta.json                     (ast key appended)
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
STAT = "ast"
OOS_MODEL_DIR = os.path.join(PROJECT_DIR, "data", "models", "oos_pre_playoffs")


def main() -> None:
    os.makedirs(OOS_MODEL_DIR, exist_ok=True)
    t0 = time.time()

    original_build = pg.build_pergame_dataset
    cutoff = datetime.fromisoformat(CUTOFF_DATE)

    n_total_holder = {"n_all": 0, "n_pre": 0}

    def _filtered_build(gamelog_dir=None, **kw):
        rows, fcols = original_build(gamelog_dir, **kw)
        n_total_holder["n_all"] = len(rows)
        rows = [r for r in rows if datetime.fromisoformat(r["date"]) < cutoff]
        n_total_holder["n_pre"] = len(rows)
        return rows, fcols

    print(f"  iter-9 OOS AST retrain (log1p multitask MLP blend, cutoff < {CUTOFF_DATE})")
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
    print(f"  train_pergame_models([ast]) done in {elapsed_train:.1f}s")
    print(f"  n_all={n_total_holder['n_all']}  n_pre_cutoff={n_total_holder['n_pre']}")

    if metrics.get("status") == "insufficient_data":
        raise SystemExit(f"  [abort] insufficient_data ({metrics.get('n_rows')})")

    ast_m = metrics.get("stats", {}).get(STAT, {})
    print(f"  AST holdout R²={ast_m.get('holdout_r2')}  MAE={ast_m.get('holdout_mae')}")
    print(f"  base R²: xgb={ast_m.get('xgb_holdout_r2')}  "
          f"lgb={ast_m.get('lgb_holdout_r2')}  mlp={ast_m.get('mlp_holdout_r2')}")
    print(f"  NNLS weights: xgb={ast_m.get('meta_w_xgb')}  "
          f"lgb={ast_m.get('meta_w_lgb')}  mlp={ast_m.get('meta_w_mlp')}  "
          f"src={ast_m.get('meta_fit_source')}")
    print(f"  calibration used: {ast_m.get('calibration_used')}  "
          f"lift_mae={ast_m.get('calibration_lift_mae')}")

    # Merge into the shared _meta.json so iter-7/8/9 share the same convention.
    meta_path = os.path.join(OOS_MODEL_DIR, "_meta.json")
    all_meta = {}
    if os.path.exists(meta_path):
        try:
            all_meta = json.load(open(meta_path, encoding="utf-8"))
        except Exception:
            all_meta = {}
    if "stats" not in all_meta:
        all_meta = {"stats": {}}

    n_train_val = metrics.get("n_train", 0)
    n_val_full = metrics.get("n_val", 0)
    n_holdout = metrics.get("n_holdout", 0)

    all_meta["stats"][STAT] = {
        "cutoff_date": CUTOFF_DATE,
        "stat": STAT,
        "method": "log1p_multitask_mlp_blend",
        "n_train": n_train_val,
        "n_val": n_val_full,
        "n_holdout": n_holdout,
        "val_mae": float(ast_m.get("holdout_mae") or 0.0),
        "model_filename": "props_pg_ast.json (+ lgb/mlp/scaler/cal)",
        "training_timestamp": datetime.now().isoformat(),
        "fit_seconds": float(elapsed_train),
        "n_features": len(metrics.get("feature_cols") or []),
        "n_total_rows": n_total_holder["n_all"],
        "n_pre_cutoff_rows": n_total_holder["n_pre"],
        "holdout_r2": float(ast_m.get("holdout_r2") or 0.0),
        "holdout_mae": float(ast_m.get("holdout_mae") or 0.0),
        "uncal_holdout_mae": float(ast_m.get("uncal_holdout_mae") or 0.0),
        "calibration_used": bool(ast_m.get("calibration_used") or False),
        "calibration_lift_mae": float(ast_m.get("calibration_lift_mae") or 0.0),
        "meta_w_xgb": float(ast_m.get("meta_w_xgb") or 0.0),
        "meta_w_lgb": float(ast_m.get("meta_w_lgb") or 0.0),
        "meta_w_mlp": float(ast_m.get("meta_w_mlp") or 0.0),
        "meta_fit_source": ast_m.get("meta_fit_source"),
        "xgb_holdout_r2": float(ast_m.get("xgb_holdout_r2") or 0.0),
        "lgb_holdout_r2": float(ast_m.get("lgb_holdout_r2") or 0.0),
        "mlp_holdout_r2": float(ast_m.get("mlp_holdout_r2") or 0.0),
        "hps": {
            "max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
            "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
            "subsample": 0.7,
            "target_transform": "log1p",
            "xgb_objective": "reg:squarederror",
            "lgb_objective": "regression",
            "mlp_kind": "multitask_5seed (shared across all 7 stats, proxy for ast)",
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
    print(f"    n_train/val/holdout: {n_train_val}/{n_val_full}/{n_holdout}")
    print(f"    holdout_R²:    {ast_m.get('holdout_r2')}")
    print(f"    holdout_MAE:   {ast_m.get('holdout_mae')}")
    print(f"    total time:    {total:.1f}s")


if __name__ == "__main__":
    main()
