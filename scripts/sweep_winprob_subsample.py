"""sweep_winprob_subsample.py — row-subsample sweep for WinProbability.

Mirrors sweep_winprob_learning_rate.py but varies the XGB `subsample` knob.
With 3.7k training rows the model can plausibly tolerate more or less bagging
than the production default of 0.8 — this sweep measures whether the gain
exceeds the ship gate.

Read-only on prod state: never overwrites win_prob_metrics.json and never
saves a model. Cache schema (v8) lacks the 4 sim_* features; sweep auto-drops
them and uses subsample=0.8 (prod default) as the in-sweep apples-to-apples
baseline.

Ship gate (workday-loop spec): pick subsample whose Brier improves by >0.001
OR whose accuracy improves by >=0.5pp vs the subsample=0.8 in-sweep baseline.

Run:
    python scripts/sweep_winprob_subsample.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import List, Tuple

import numpy as np
import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.win_probability import (  # noqa: E402
    _MODEL_DIR,
    _MODEL_FEATURE_COLS,
    _fetch_season_games,
)


# Training seasons (matches the win_probability.train() default).
SEASONS: List[str] = ["2022-23", "2023-24", "2024-25"]

# Subsample grid. 0.8 is the production default; the rest probe more (0.9/1.0)
# and less (0.6/0.7) row bagging.
_SUB_GRID: List[float] = [0.6, 0.7, 0.8, 0.9, 1.0]

# Other XGB params held constant (mirrors win_probability.train()).
_FIXED_PARAMS = dict(
    n_estimators=300,
    learning_rate=0.05,
    max_depth=4,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


def _baseline_file() -> Tuple[float, float]:
    """Read accuracy/brier from the last-saved metrics JSON. Informational only."""
    path = os.path.join(_MODEL_DIR, "win_prob_metrics.json")
    if os.path.exists(path):
        with open(path) as f:
            m = json.load(f)
        return float(m.get("accuracy", 0.685)), float(m.get("brier", 0.209))
    return 0.685, 0.209


def _build_dataset(
    seasons: List[str],
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Materialize the chronologically-ordered X/y for the win-prob model.

    Drops any `_MODEL_FEATURE_COLS` entry not present in every cached row so
    that schema drift (e.g. sim_* features missing from v8 cache) doesn't
    crash the sweep. The same column set is used across every subsample.
    """
    rows: list = []
    for s in seasons:
        s_rows = _fetch_season_games(s)
        if not s_rows:
            raise RuntimeError(f"empty cache for {s} — run train() first to warm")
        rows.extend(s_rows)
        print(f"  {s}: {len(s_rows)} games")

    df = pd.DataFrame(rows).dropna(subset=["home_win"])
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)

    available = [c for c in _MODEL_FEATURE_COLS if c in df.columns]
    missing   = [c for c in _MODEL_FEATURE_COLS if c not in df.columns]
    if missing:
        print(f"  [warn] {len(missing)} feature(s) absent from cache "
              f"(schema drift); sweep will use {len(available)} of "
              f"{len(_MODEL_FEATURE_COLS)}: missing={missing}")

    X = df[available].values.astype(np.float32)
    y = df["home_win"].values.astype(int)
    return X, y, available


def _fit_eval(X: np.ndarray, y: np.ndarray, sub: float) -> Tuple[float, float]:
    """Train XGB with the given subsample; return (val_accuracy, val_brier)."""
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss

    split = int(len(X) * 0.8)
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    clf = XGBClassifier(subsample=sub, **_FIXED_PARAMS)
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    probs = clf.predict_proba(X_val)[:, 1]
    acc   = float(accuracy_score(y_val, (probs >= 0.5).astype(int)))
    brier = float(brier_score_loss(y_val, probs))
    return acc, brier


def main() -> None:
    print(f"Win-Probability subsample sweep (grid={_SUB_GRID})\n")
    file_acc, file_brier = _baseline_file()
    print(f"Prod metrics file: accuracy={file_acc:.4f}  Brier={file_brier:.4f} "
          f"(informational only)")

    print("\nBuilding dataset from cached season games...")
    X, y, features_used = _build_dataset(SEASONS)
    print(f"  Dataset: n={len(X)} games | home win rate {y.mean():.1%} "
          f"| features={X.shape[1]}\n")

    if 0.8 not in _SUB_GRID:
        raise RuntimeError("subsample grid must include 0.8 (prod default) "
                           "as the in-sweep baseline.")

    results: dict[float, Tuple[float, float]] = {}
    for sub in _SUB_GRID:
        acc, brier = _fit_eval(X, y, sub)
        results[sub] = (acc, brier)
        print(f"  subsample={sub:.2f}  acc {acc:.4f}  brier {brier:.4f}")

    sweep_base_acc, sweep_base_brier = results[0.8]
    print(f"\nIn-sweep baseline (subsample=0.80): "
          f"acc {sweep_base_acc:.4f}  brier {sweep_base_brier:.4f}")
    print("Deltas vs in-sweep baseline:")
    for sub in _SUB_GRID:
        a, b = results[sub]
        d_acc_pp = (a - sweep_base_acc) * 100
        d_brier  = b - sweep_base_brier
        print(f"  subsample={sub:.2f}  d_acc {d_acc_pp:+.2f}pp  "
              f"d_brier {d_brier:+.4f}")

    best_sub = min(results, key=lambda s: results[s][1])
    best_acc, best_brier = results[best_sub]
    d_acc_pp = (best_acc - sweep_base_acc) * 100
    d_brier  = best_brier - sweep_base_brier
    print("\n=== Winner (by Brier) ===")
    print(f"  subsample={best_sub:.2f}  acc {best_acc:.4f}  brier {best_brier:.4f}")
    print(f"  vs subsample=0.80: d_acc {d_acc_pp:+.2f}pp  d_brier {d_brier:+.4f}")

    ships = (d_brier < -0.001) or (d_acc_pp >= 0.5)
    print(f"  Ship gate: {'PASS' if ships else 'FAIL'}  "
          f"(needs d_brier < -0.001 OR d_acc >= +0.5pp)")

    out_path = os.path.join(_MODEL_DIR, "winprob_subsample_sweep_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "grid": _SUB_GRID,
            "seasons": SEASONS,
            "fixed_params": _FIXED_PARAMS,
            "features_used": features_used,
            "n_features_used": len(features_used),
            "prod_metrics_file": {"accuracy": file_acc, "brier": file_brier},
            "in_sweep_baseline_subsample": 0.8,
            "in_sweep_baseline": {"accuracy": sweep_base_acc,
                                  "brier": sweep_base_brier},
            "results": {str(sub): {"accuracy": a, "brier": b}
                        for sub, (a, b) in results.items()},
            "winner": {"subsample": best_sub,
                       "accuracy": best_acc, "brier": best_brier,
                       "delta_acc_pp": d_acc_pp,
                       "delta_brier": d_brier,
                       "ships": bool(ships)},
        }, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
