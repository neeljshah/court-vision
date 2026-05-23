"""sweep_n_estimators.py — per-stat n_estimators ceiling sweep.

With small lr (0.025) + early_stopping_rounds=40, the n_estimators
parameter is an upper bound. If models hit the cap, they may benefit
from more headroom. Try {current, current*1.5, current*2}.
"""
from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    STATS,
    train_pergame_models,
    _NBA_CACHE,
    _MODEL_DIR,
)

_CURRENT = {
    "pts":  {"max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
             "subsample": 0.8, "colsample_bytree": 0.9, "reg_alpha": 2.0},
    "ast":  {"max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025,
             "subsample": 0.7, "colsample_bytree": 0.8, "reg_alpha": 0.5},
    "reb":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 4.0,
             "gamma": 0.3, "n_estimators": 800, "learning_rate": 0.025,
             "subsample": 0.7, "colsample_bytree": 0.9, "reg_alpha": 0.5},
    "fg3m": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 8.0,
             "gamma": 0.0, "n_estimators": 600, "learning_rate": 0.025,
             "subsample": 0.7, "colsample_bytree": 0.8, "reg_alpha": 0.5},
    "tov":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
             "gamma": 0.4, "n_estimators": 700, "learning_rate": 0.025,
             "subsample": 0.8, "colsample_bytree": 0.8, "reg_alpha": 0.5},
    "blk":  {"max_depth": 3, "min_child_weight": 25, "reg_lambda": 4.0,
             "gamma": 0.4, "n_estimators": 500, "learning_rate": 0.06,
             "subsample": 0.8, "colsample_bytree": 1.0, "reg_alpha": 0.5},
    "stl":  {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
             "gamma": 0.6, "n_estimators": 400, "learning_rate": 0.06,
             "subsample": 0.9, "colsample_bytree": 0.8, "reg_alpha": 0.25},
}

_GRIDS = {
    "pts":  [800, 1200, 1500, 2000],
    "ast":  [800, 1200, 1500, 2000],
    "reb":  [800, 1200, 1500, 2000],
    "fg3m": [600, 1000, 1500],
    "tov":  [700, 1000, 1500],
    "blk":  [500, 800, 1200],
    "stl":  [400, 600, 1000],
}


def _baseline():
    with open(os.path.join(_MODEL_DIR, "props_pergame_metrics.json")) as f:
        m = json.load(f)
    return {s: (float(m["stats"][s]["holdout_mae"]),
                float(m["stats"][s]["holdout_r2"])) for s in STATS}


def main():
    base = _baseline()
    print("Baseline:")
    for s, (mae, r2) in base.items():
        print(f"  {s:5} MAE {mae:.4f}  R² {r2:.4f}")

    results = {}
    for stat in STATS:
        grid = _GRIDS[stat]
        print(f"\n[{stat}] sweeping n_estimators {grid}")
        results[stat] = {}
        for ne in grid:
            params = dict(_CURRENT[stat], n_estimators=ne)
            metrics = train_pergame_models(
                _NBA_CACHE, _MODEL_DIR,
                stats=[stat], stat_params_override={stat: params})
            s = metrics["stats"][stat]
            mae, r2 = float(s["holdout_mae"]), float(s["holdout_r2"])
            results[stat][ne] = (mae, r2)
            print(f"  {stat:5} n_est={ne} -> MAE {mae:.4f}  R² {r2:.4f}")

    print("\n=== Per-stat winners (lowest MAE) ===")
    winners = {}; net_mae = net_r2 = 0.0
    for stat in STATS:
        best = min(results[stat], key=lambda x: results[stat][x][0])
        mae, r2 = results[stat][best]
        cm, cr = base[stat]
        winners[stat] = best
        net_mae += mae - cm; net_r2 += r2 - cr
        print(f"  {stat:5} winner n_est={best}  MAE {mae:.4f} ({(mae-cm)/cm*100:+.3f}%)  R²Δ{r2-cr:+.4f}")

    print(f"\nIf every winner ships: net MAE {net_mae:+.4f}, net R² {net_r2:+.4f}")

    out = os.path.join(_MODEL_DIR, "n_estimators_sweep_results.json")
    with open(out, "w") as f:
        json.dump({"grids": _GRIDS,
                   "results": {s: {str(k): list(v) for k, v in r.items()} for s, r in results.items()},
                   "winners": winners}, f, indent=2)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
