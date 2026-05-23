"""sweep_learning_rate.py — per-stat learning-rate sweep for prop_pergame.

Trains each stat with multiple learning rates (one stat at a time so the
shared metrics JSON doesn't get clobbered), records holdout MAE / R², and
prints the per-stat winner so it can be encoded in _STAT_PARAMS.
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

# Current per-stat params snapshot (from _STAT_PARAMS in prop_pergame.py).
# stat_params_override REPLACES — so we merge manually for each stat.
_CURRENT = {
    "pts":  {"max_depth": 6, "min_child_weight": 20, "reg_lambda": 4.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.04},
    "ast":  {"max_depth": 5, "min_child_weight": 20, "reg_lambda": 5.0,
             "gamma": 0.2, "n_estimators": 800, "learning_rate": 0.04},
    "reb":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 4.0,
             "gamma": 0.3, "n_estimators": 800, "learning_rate": 0.04},
    "fg3m": {"max_depth": 4, "min_child_weight": 15, "reg_lambda": 2.0,
             "gamma": 0.3, "n_estimators": 600, "learning_rate": 0.04},
    "tov":  {"max_depth": 3, "min_child_weight": 30, "reg_lambda": 6.0,
             "gamma": 0.4, "n_estimators": 700, "learning_rate": 0.04},
    "blk":  {"max_depth": 2, "min_child_weight": 25, "reg_lambda": 4.0,
             "gamma": 0.4, "n_estimators": 500, "learning_rate": 0.04},
    "stl":  {"max_depth": 2, "min_child_weight": 40, "reg_lambda": 6.0,
             "gamma": 0.6, "n_estimators": 400, "learning_rate": 0.04},
}

# Smaller LR with the same n_estimators should let early stopping pick a
# deeper-train fit. Larger LR is a sanity check that 0.04 isn't already big.
_LR_GRID = [0.025, 0.04, 0.06]


def _baseline(stat: str) -> tuple[float, float]:
    """Read current MAE / R² from the shared metrics JSON."""
    with open(os.path.join(_MODEL_DIR, "props_pergame_metrics.json")) as f:
        m = json.load(f)
    s = m["stats"][stat]
    return float(s["holdout_mae"]), float(s["holdout_r2"])


def _sweep_stat(stat: str) -> dict:
    """Train `stat` once per learning rate; return {lr: (mae, r2)} dict."""
    out = {}
    base = dict(_CURRENT[stat])
    for lr in _LR_GRID:
        params = dict(base, learning_rate=lr)
        metrics = train_pergame_models(
            _NBA_CACHE, _MODEL_DIR,
            stats=[stat],
            stat_params_override={stat: params},
        )
        s = metrics["stats"][stat]
        out[lr] = (float(s["holdout_mae"]), float(s["holdout_r2"]))
        print(f"  {stat:5} lr={lr:.3f} -> MAE {out[lr][0]:.4f}  R² {out[lr][1]:.4f}")
    return out


def main() -> None:
    print("Learning-rate sweep (per-stat, retrain each combo separately).\n")
    print("Baseline (current master):")
    base_mae = {s: _baseline(s) for s in STATS}
    for s, (m, r) in base_mae.items():
        print(f"  {s:5} MAE {m:.4f}  R² {r:.4f}")
    print()

    results: dict[str, dict[float, tuple[float, float]]] = {}
    for stat in STATS:
        print(f"\n[{stat}] sweeping learning_rate {_LR_GRID}")
        results[stat] = _sweep_stat(stat)

    print("\n\n=== Per-stat winners (lowest MAE) ===")
    winners: dict[str, float] = {}
    for stat in STATS:
        best_lr = min(results[stat], key=lambda lr: results[stat][lr][0])
        best_mae, best_r2 = results[stat][best_lr]
        cur_mae, cur_r2 = base_mae[stat]
        dmae = (best_mae - cur_mae) / cur_mae * 100
        winners[stat] = best_lr
        print(f"  {stat:5} winner lr={best_lr:.3f}  MAE {best_mae:.4f} ({dmae:+.3f}%)  R² {best_r2:.4f} (Δ{best_r2-cur_r2:+.4f})")

    # Net deltas if every winner shipped.
    net_mae = sum(results[s][winners[s]][0] - base_mae[s][0] for s in STATS)
    net_r2  = sum(results[s][winners[s]][1] - base_mae[s][1] for s in STATS)
    print(f"\nIf every winner ships: net MAE {net_mae:+.4f}, net R² {net_r2:+.4f}")

    out_path = os.path.join(_MODEL_DIR, "lr_sweep_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "grid": _LR_GRID,
            "results": {s: {str(lr): list(v) for lr, v in r.items()}
                        for s, r in results.items()},
            "winners": winners,
        }, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
