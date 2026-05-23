"""sweep_subsample.py — per-stat row-subsample sweep for prop_pergame.

With 99k+ rows the model can tolerate less bagging than the 0.8 default.
Sweep {0.7, 0.8, 0.9, 1.0} per stat, ship per-stat winners.
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

# Current per-stat params snapshot (post cycle 25 — learning_rate encoded).
_CURRENT = {
    "pts":  {"max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025},
    "ast":  {"max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.025},
    "reb":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 4.0,
             "gamma": 0.3, "n_estimators": 800, "learning_rate": 0.025},
    "fg3m": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 2.0,
             "gamma": 0.3, "n_estimators": 600, "learning_rate": 0.025},
    "tov":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
             "gamma": 0.4, "n_estimators": 700, "learning_rate": 0.025},
    "blk":  {"max_depth": 2, "min_child_weight": 25, "reg_lambda": 4.0,
             "gamma": 0.4, "n_estimators": 500, "learning_rate": 0.06},
    "stl":  {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
             "gamma": 0.6, "n_estimators": 400, "learning_rate": 0.06},
}

_SUBSAMPLE_GRID = [0.7, 0.8, 0.9, 1.0]


def _baseline() -> dict:
    with open(os.path.join(_MODEL_DIR, "props_pergame_metrics.json")) as f:
        m = json.load(f)
    return {s: (float(m["stats"][s]["holdout_mae"]),
                float(m["stats"][s]["holdout_r2"])) for s in STATS}


def main() -> None:
    base = _baseline()
    print("Baseline (master):")
    for s, (mae, r2) in base.items():
        print(f"  {s:5} MAE {mae:.4f}  R² {r2:.4f}")

    results = {}
    for stat in STATS:
        print(f"\n[{stat}] sweeping subsample {_SUBSAMPLE_GRID}")
        results[stat] = {}
        for sub in _SUBSAMPLE_GRID:
            params = dict(_CURRENT[stat], subsample=sub)
            metrics = train_pergame_models(
                _NBA_CACHE, _MODEL_DIR,
                stats=[stat], stat_params_override={stat: params})
            s = metrics["stats"][stat]
            mae, r2 = float(s["holdout_mae"]), float(s["holdout_r2"])
            results[stat][sub] = (mae, r2)
            print(f"  {stat:5} subsample={sub:.2f} -> MAE {mae:.4f}  R² {r2:.4f}")

    print("\n=== Per-stat winners (lowest MAE) ===")
    winners = {}
    net_mae = net_r2 = 0.0
    for stat in STATS:
        best_sub = min(results[stat], key=lambda x: results[stat][x][0])
        mae, r2 = results[stat][best_sub]
        cm, cr = base[stat]
        winners[stat] = best_sub
        net_mae += mae - cm
        net_r2 += r2 - cr
        print(f"  {stat:5} winner subsample={best_sub:.2f}  MAE {mae:.4f} ({(mae-cm)/cm*100:+.3f}%)  R² Δ{r2-cr:+.4f}")

    print(f"\nIf every winner ships: net MAE {net_mae:+.4f}, net R² {net_r2:+.4f}")

    out_path = os.path.join(_MODEL_DIR, "subsample_sweep_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "grid": _SUBSAMPLE_GRID,
            "results": {s: {str(k): list(v) for k, v in r.items()} for s, r in results.items()},
            "winners": winners,
        }, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
