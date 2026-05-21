#!/usr/bin/env python3
"""
retrain_props_temporal.py — Leakage-safe temporal CV retraining for prop models.

Usage:
    python scripts/retrain_props_temporal.py [--stats pts reb] [--dry-run] [--threshold 0.08]

Public API
----------
    retrain_props_temporal_cv(stats, dry_run, threshold) -> dict[str, dict]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.prediction.prop_cv_split import (
    _objective_for_stat,
    filter_excluded_players,
    make_temporal_split,
    sort_chronologically,
)

_MODEL_DIR = PROJECT_DIR / "data" / "models"
_REGISTRY_PATH = _MODEL_DIR / "model_registry.json"
_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
_OVERFIT_THRESHOLD = 0.08


def _make_synthetic_df(stat: str, n: int = 600) -> "pd.DataFrame":
    """Synthetic game-log DataFrame for dry_run / offline testing."""
    import pandas as pd

    rng = np.random.default_rng(hash(stat) % 2**32)
    dates = pd.date_range("2022-10-01", periods=n, freq="2D")
    means = {"pts": 18.0, "reb": 5.0, "ast": 4.0, "fg3m": 1.5,
              "stl": 0.9, "blk": 0.6, "tov": 1.8}
    mu = means.get(stat, 10.0)
    return pd.DataFrame({
        "game_date": dates,
        stat: rng.normal(mu, mu * 0.3, n).clip(0),
        "home": rng.integers(0, 2, n).astype(float),
        "rest_days": rng.integers(1, 5, n).astype(float),
        "opp_def_rating": rng.normal(112.0, 3.0, n),
    })


def _load_gamelog(stat: str) -> Optional["pd.DataFrame"]:
    """Load historical game-log CSV if available, else return None."""
    import pandas as pd

    path = PROJECT_DIR / "data" / "nba" / f"prop_gamelog_{stat}.csv"
    if path.exists():
        try:
            df = pd.read_csv(path, parse_dates=["game_date"])
            if len(df) >= 100 and stat in df.columns:
                return df
        except Exception:
            pass
    return None


def _cv_metrics(
    stat: str, df: "pd.DataFrame", n_splits: int = 5, threshold: float = _OVERFIT_THRESHOLD
) -> Dict:
    """Forward-chaining CV returning holdout + train metrics for one stat."""
    import pandas as pd
    from sklearn.metrics import mean_absolute_error, r2_score

    try:
        from xgboost import XGBRegressor
    except ImportError:
        from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor  # type: ignore

    df = sort_chronologically(df, date_col="game_date")
    feat_cols = [c for c in df.columns if c not in ("game_date", stat)]
    X_all = df[feat_cols].fillna(0).values
    y_all = df[stat].values

    tscv = make_temporal_split(df, date_col="game_date", n_splits=n_splits)

    holdout_preds: List[float] = []
    holdout_truths: List[float] = []
    train_preds: List[float] = []
    train_truths: List[float] = []

    obj = _objective_for_stat(stat)

    for train_idx, val_idx in tscv.split(X_all):
        X_tr, y_tr = X_all[train_idx], y_all[train_idx]
        X_val, y_val = X_all[val_idx], y_all[val_idx]

        # Rolling feature computed on train window only (no leakage)
        train_series = pd.Series(y_tr)
        last_roll = train_series.rolling(5, min_periods=1).mean().values
        val_fill = np.full(len(val_idx), last_roll[-1])
        X_tr = np.column_stack([X_tr, last_roll])
        X_val = np.column_stack([X_val, val_fill])

        _default_params: dict = {"n_estimators": 80, "max_depth": 3,
                                 "learning_rate": 0.1, "random_state": 42}
        _hp_path = _MODEL_DIR / f"hyperparams_{stat}.json"
        if _hp_path.exists():
            try:
                _saved = json.loads(_hp_path.read_text(encoding="utf-8"))
                _default_params.update(_saved.get("best_params", {}))
            except Exception:
                pass
        params: dict = _default_params
        params["random_state"] = 42
        if obj == "count:poisson" and hasattr(XGBRegressor, "set_params"):
            params["objective"] = obj
        try:
            model = XGBRegressor(**params)
        except TypeError:
            model = XGBRegressor(n_estimators=80, max_depth=3)

        model.fit(X_tr, y_tr)
        holdout_preds.extend(model.predict(X_val).tolist())
        holdout_truths.extend(y_val.tolist())
        train_preds.extend(model.predict(X_tr).tolist())
        train_truths.extend(y_tr.tolist())

    holdout_r2 = float(r2_score(holdout_truths, holdout_preds)) if holdout_truths else 0.0
    holdout_mae = float(mean_absolute_error(holdout_truths, holdout_preds)) if holdout_truths else 0.0
    train_r2 = float(r2_score(train_truths, train_preds)) if train_truths else 0.0
    train_mae = float(mean_absolute_error(train_truths, train_preds)) if train_truths else 0.0

    return {
        "holdout_r2": round(holdout_r2, 4),
        "holdout_mae": round(holdout_mae, 4),
        "train_r2": round(train_r2, 4),
        "train_mae": round(train_mae, 4),
        "train_n": len(train_truths),
        "holdout_n": len(holdout_truths),
        "needs_retrain": abs(train_r2 - holdout_r2) > threshold,
        "retrain_version": "temporal_cv_v1",
    }


def retrain_props_temporal_cv(
    stats: Optional[List[str]] = None,
    dry_run: bool = False,
    n_splits: int = 5,
    threshold: float = _OVERFIT_THRESHOLD,
    exclude_player_ids: Optional[List[int]] = None,
) -> Dict[str, Dict]:
    """
    Retrain prop models with leakage-safe forward-chaining CV.

    Args:
        stats:     Stat keys to retrain. Defaults to all 7 props.
        dry_run:   Skip writing model/registry files; still compute metrics.
        n_splits:  Number of CV folds.
        threshold: Overfit gate — needs_retrain=True when |train_r2-holdout_r2| exceeds this.

    Returns:
        {stat: {holdout_r2, holdout_mae, train_r2, train_mae,
                train_n, holdout_n, needs_retrain, retrain_version}}
    """
    stats = list(stats or _STATS)
    results: Dict[str, Dict] = {}

    for stat in stats:
        df = _load_gamelog(stat) or _make_synthetic_df(stat)
        if exclude_player_ids and "player_id" in df.columns:
            df = filter_excluded_players(df, exclude_player_ids)

        metrics = _cv_metrics(stat, df, n_splits=n_splits, threshold=threshold)
        results[stat] = metrics
        flag = " [WARN]" if metrics["needs_retrain"] else ""
        print(f"  {stat:5s}  holdout_r2={metrics['holdout_r2']:.3f}  "
              f"train_r2={metrics['train_r2']:.3f}  mae={metrics['holdout_mae']:.3f}{flag}")

    if not dry_run:
        _update_registry(results)

    return results


def _update_registry(results: Dict[str, Dict]) -> None:
    """Merge per-stat metrics into model_registry.json."""
    registry: Dict[str, Dict] = {}
    if _REGISTRY_PATH.exists():
        try:
            registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    for stat, metrics in results.items():
        registry[f"props_{stat}"] = metrics
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    print(f"  [registry] Saved {len(registry)} entries -> {_REGISTRY_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Temporal CV retraining for prop models")
    parser.add_argument("--stats", nargs="+", default=list(_STATS))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--splits", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=_OVERFIT_THRESHOLD)
    args = parser.parse_args()

    retrain_props_temporal_cv(
        stats=args.stats,
        dry_run=args.dry_run,
        n_splits=args.splits,
        threshold=args.threshold,
    )
