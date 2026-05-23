"""sweep_winprob_learning_rate.py — learning-rate sweep for WinProbability.

Mirrors the per-stat sweep methodology used for prop_pergame, applied to the
binary win-probability classifier. Trains XGBoost across a small learning-rate
grid using the same chronological 80/20 split and the cached season-game rows
(no NBA API calls — relies on data/nba/season_games_*.json v8 cache).

Sweep is read-only on production state: it does NOT save a model or overwrite
`data/models/win_prob_metrics.json`. Results go to a dedicated sweep JSON so
the prod model is untouched until a winner is encoded into win_probability.py.

Ship gate (workday-loop spec): pick lr whose Brier improves by >0.001 OR
whose accuracy improves by >=0.5pp vs the current baseline. If no candidate
clears the gate the script still writes the result file for diagnostics.

Run:
    python scripts/sweep_winprob_learning_rate.py
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

# Learning rates to scan. 0.05 is the current default in train();
# 0.025/0.035 probe slower fits where early-stopping may exploit more trees,
# 0.07/0.10 probe a faster fit.
_LR_GRID: List[float] = [0.025, 0.035, 0.05, 0.07, 0.10]

# Other XGB params held constant (mirrors win_probability.train()).
_FIXED_PARAMS = dict(
    n_estimators=300,
    max_depth=4,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric="logloss",
    random_state=42,
    n_jobs=-1,
    early_stopping_rounds=20,
)


def _baseline() -> Tuple[float, float]:
    """Read accuracy/brier from the last-saved metrics JSON.

    Falls back to vault-recorded values (0.685 / 0.209) if the file is absent.
    """
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

    Relies on `_fetch_season_games` returning cached rows for the listed
    completed seasons. Raises if any cache is empty.

    The cache schema may lag `_MODEL_FEATURE_COLS` (sim_* features are
    appended at fetch time, so older v8 caches lack them). Any column not
    present in every row is dropped from the sweep — same column set is then
    used across all LR variants, so within-sweep comparisons are sound. The
    in-sweep `lr=0.05` baseline (rather than the prod metrics file) is what
    the ship gate uses, so a reduced feature set does not invalidate it.
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


def _fit_eval(X: np.ndarray, y: np.ndarray, lr: float) -> Tuple[float, float]:
    """Train XGB with the given LR; return (val_accuracy, val_brier).

    Uses the same chronological 80/20 split as production training and does
    not persist the model.
    """
    from xgboost import XGBClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss

    split = int(len(X) * 0.8)
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    clf = XGBClassifier(learning_rate=lr, **_FIXED_PARAMS)
    clf.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
    probs = clf.predict_proba(X_val)[:, 1]
    acc   = float(accuracy_score(y_val, (probs >= 0.5).astype(int)))
    brier = float(brier_score_loss(y_val, probs))
    return acc, brier


def main() -> None:
    print(f"Win-Probability learning-rate sweep (grid={_LR_GRID})\n")
    file_acc, file_brier = _baseline()
    print(f"Prod metrics file: accuracy={file_acc:.4f}  Brier={file_brier:.4f} "
          f"(informational only)")

    print("\nBuilding dataset from cached season games...")
    X, y, features_used = _build_dataset(SEASONS)
    print(f"  Dataset: n={len(X)} games | home win rate {y.mean():.1%} "
          f"| features={X.shape[1]}\n")

    # The default LR (0.05) must be present in the grid so the ship gate
    # compares apples-to-apples on the exact feature set used in this sweep.
    if 0.05 not in _LR_GRID:
        raise RuntimeError("LR grid must include 0.05 (the production default) "
                           "as the in-sweep baseline.")

    results: dict[float, Tuple[float, float]] = {}
    for lr in _LR_GRID:
        acc, brier = _fit_eval(X, y, lr)
        results[lr] = (acc, brier)
        print(f"  lr={lr:.3f}  acc {acc:.4f}  brier {brier:.4f}")

    # In-sweep baseline = current default LR on the same feature set.
    sweep_base_acc, sweep_base_brier = results[0.05]
    print(f"\nIn-sweep baseline (lr=0.050): "
          f"acc {sweep_base_acc:.4f}  brier {sweep_base_brier:.4f}")
    print("Deltas vs in-sweep baseline:")
    for lr in _LR_GRID:
        a, b = results[lr]
        d_acc_pp = (a - sweep_base_acc) * 100
        d_brier  = b - sweep_base_brier
        print(f"  lr={lr:.3f}  d_acc {d_acc_pp:+.2f}pp  d_brier {d_brier:+.4f}")

    # Winner: lowest Brier (calibration is the primary metric).
    best_lr = min(results, key=lambda lr: results[lr][1])
    best_acc, best_brier = results[best_lr]
    d_acc_pp = (best_acc - sweep_base_acc) * 100
    d_brier  = best_brier - sweep_base_brier
    print("\n=== Winner (by Brier) ===")
    print(f"  lr={best_lr:.3f}  acc {best_acc:.4f}  brier {best_brier:.4f}")
    print(f"  vs lr=0.050: d_acc {d_acc_pp:+.2f}pp  d_brier {d_brier:+.4f}")

    # Ship gate from workday-loop spec, computed vs in-sweep baseline.
    ships = (d_brier < -0.001) or (d_acc_pp >= 0.5)
    print(f"  Ship gate: {'PASS' if ships else 'FAIL'}  "
          f"(needs d_brier < -0.001 OR d_acc >= +0.5pp)")

    out_path = os.path.join(_MODEL_DIR, "winprob_lr_sweep_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "grid": _LR_GRID,
            "seasons": SEASONS,
            "fixed_params": _FIXED_PARAMS,
            "features_used": features_used,
            "n_features_used": len(features_used),
            "prod_metrics_file": {"accuracy": file_acc, "brier": file_brier},
            "in_sweep_baseline_lr": 0.05,
            "in_sweep_baseline": {"accuracy": sweep_base_acc,
                                  "brier": sweep_base_brier},
            "results": {str(lr): {"accuracy": a, "brier": b}
                        for lr, (a, b) in results.items()},
            "winner": {"learning_rate": best_lr,
                       "accuracy": best_acc, "brier": best_brier,
                       "delta_acc_pp": d_acc_pp,
                       "delta_brier": d_brier,
                       "ships": bool(ships)},
        }, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
