"""
tune_prop_hyperparams.py — Grid-search prop hyperparameters (PRED-12).

The prop_grid_search infrastructure (96–192 param combinations per stat,
scored on temporal CV) existed but was never invoked — training always used
the static defaults. This script runs the grid search for every prop stat
and writes hyperparams_{stat}.json; prop_cv_split.xgb_params_for_stat() then
picks those tuned params up automatically on the next training run.

Usage:
    python scripts/tune_prop_hyperparams.py [--stat pts] [--n-jobs 4]

Needs the NBA player-stats caches — run on a data-available host.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)


def tune_all(stats: Optional[List[str]] = None, n_jobs: int = 4) -> dict:
    """Run grid search for the given prop stats and persist tuned params.

    Returns ``{stat: status}`` — "tuned", "no_label", or an error string.
    Returns ``{"status": "no_data"}`` when the prop training frame is empty.
    """
    from src.prediction.player_props import _build_prop_training_frame, _PROP_STATS
    from src.prediction.prop_cv_split import make_temporal_split, sort_chronologically
    from src.prediction.prop_grid_search import run_grid_search

    train_df, _test_df, feat_cols = _build_prop_training_frame(None, None)
    if train_df is None:
        return {"status": "no_data"}

    train_df = sort_chronologically(train_df)
    results: dict = {}
    for stat in (stats or list(_PROP_STATS)):
        label = f"season_{stat}"
        if label not in train_df.columns:
            results[stat] = "no_label"
            continue
        stat_cols = [c for c in feat_cols if c != label and c in train_df.columns]
        X = train_df[stat_cols].fillna(0.0).values
        y = train_df[label].values
        tscv = make_temporal_split(train_df)
        try:
            run_grid_search(stat, X, y, tscv, n_jobs=n_jobs)
            results[stat] = "tuned"
        except Exception as exc:  # noqa: BLE001
            results[stat] = f"error: {exc}"
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="Grid-search prop hyperparameters")
    ap.add_argument("--stat", default=None, help="Tune just one stat")
    ap.add_argument("--n-jobs", type=int, default=4, help="GridSearchCV workers")
    args = ap.parse_args()

    stats = [args.stat] if args.stat else None
    results = tune_all(stats, n_jobs=args.n_jobs)
    print("\n[tune_prop_hyperparams] results:")
    for k, v in results.items():
        print(f"  {k}: {v}")
    if results.get("status") == "no_data":
        print("  No training data — run on a host with the NBA stats caches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
