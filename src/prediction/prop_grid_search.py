"""
prop_grid_search.py — GridSearchCV orchestrator for temporal prop model tuning.

Public API
----------
    run_grid_search(stat, X, y, tscv, n_jobs)   -> xgb.XGBRegressor (best estimator)

Param grids
-----------
    REGRESSION_PARAM_GRID  — pts, reb, ast, fg3m, tov
    POISSON_PARAM_GRID     — stl, blk (count stats, tighter LR)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import numpy as np
import xgboost as xgb
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

from src.prediction.prop_cv_split import _objective_for_stat

_MODEL_DIR = Path(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))) / "data" / "models"

# Regression stats (continuous): pts, reb, ast, fg3m, tov
# 2×2×2×1×1×3×2×2 = 96 combos
REGRESSION_PARAM_GRID: dict = {
    "n_estimators":     [100, 200],
    "max_depth":        [3, 5],
    "learning_rate":    [0.05, 0.10],
    "subsample":        [0.8],
    "colsample_bytree": [0.8],
    "min_child_weight": [1, 3, 5],
    "reg_alpha":        [0.0, 0.5],
    "reg_lambda":       [1.0, 3.0],
}

# Count stats (Poisson): stl, blk — tighter learning_rate per research
# 2×2×2×2×1×3×2×2 = 192 combos
POISSON_PARAM_GRID: dict = {
    "n_estimators":     [150, 200],
    "max_depth":        [3, 4],
    "learning_rate":    [0.02, 0.05],
    "subsample":        [0.8, 0.9],
    "colsample_bytree": [0.8],
    "min_child_weight": [1, 3, 5],
    "reg_alpha":        [0.0, 0.5],
    "reg_lambda":       [1.0, 3.0],
}

_COUNT_STATS = frozenset(("stl", "blk"))


def run_grid_search(
    stat: str,
    X: np.ndarray,
    y: np.ndarray,
    tscv: TimeSeriesSplit,
    n_jobs: int = 4,
    verbose: int = 0,
) -> xgb.XGBRegressor:
    """Run GridSearchCV for one stat using temporal CV folds.

    Args:
        stat:   Stat name ("pts", "reb", ...). Controls objective and param grid.
        X:      Feature matrix (n_samples, n_features).
        y:      Target vector (n_samples,).
        tscv:   Pre-built TimeSeriesSplit from make_temporal_split().
        n_jobs: Parallel workers for GridSearchCV (default 4).
        verbose: GridSearchCV verbosity level.

    Returns:
        Fitted XGBRegressor (best estimator). Best params written to
        data/models/hyperparams_{stat}.json.
    """
    objective  = _objective_for_stat(stat)
    param_grid = POISSON_PARAM_GRID if stat in _COUNT_STATS else REGRESSION_PARAM_GRID

    estimator = xgb.XGBRegressor(
        objective=objective,
        random_state=42,
        n_jobs=1,   # GridSearchCV owns parallelism; XGB threads to 1 avoids oversubscription
    )

    grid = GridSearchCV(
        estimator,
        param_grid,
        cv=tscv,
        scoring="r2",
        n_jobs=n_jobs,
        verbose=verbose,
        refit=True,   # Refit best estimator on full X, y
    )

    grid_size = 1
    for v in param_grid.values():
        grid_size *= len(v)
    print(f"  [grid] {stat.upper()} — objective={objective}, grid={grid_size} combos × {tscv.n_splits} folds")

    grid.fit(X, y)

    best_params = grid.best_params_
    best_score  = grid.best_score_
    print(f"  [grid] {stat.upper()} — best CV R²={best_score:.4f}  params={best_params}")

    # Persist best params
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    params_path = _MODEL_DIR / f"hyperparams_{stat}.json"
    with open(params_path, "w") as f:
        json.dump({"stat": stat, "best_params": best_params, "best_cv_r2": round(best_score, 4)}, f, indent=2)
    print(f"  [grid] Saved best params -> {params_path}")

    return grid.best_estimator_
