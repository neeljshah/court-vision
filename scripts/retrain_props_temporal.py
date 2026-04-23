#!/usr/bin/env python3
"""
retrain_props_temporal.py — Retrain all 7 prop models with temporal CV + GridSearchCV.

Usage:
    python scripts/retrain_props_temporal.py [--stats pts reb ast] [--dry-run] [--threshold 0.08]

Args:
    --stats:     Stats to retrain (default: all 7)
    --dry-run:   Run pipeline without saving model files
    --threshold: Train-holdout R² gap threshold (default 0.08). Warns if exceeded.
    --seasons:   Seasons to use (default: 2022-23 2023-24 2024-25)
    --exclude:   player_id integers to exclude from training (space-separated)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from src.prediction.prop_cv_split import (
    make_temporal_split,
    sort_chronologically,
    filter_excluded_players,
    _objective_for_stat,
)
from src.prediction.prop_grid_search import run_grid_search

_MODEL_DIR = PROJECT_DIR / "data" / "models"
_NBA_DIR   = PROJECT_DIR / "data" / "nba"
_STATS     = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# Feature columns used in player_props._ALL_FEATS (must match training order)
from src.prediction.player_props import _ALL_FEATS as _FEAT_COLS


def _load_training_data(seasons: list[str]) -> pd.DataFrame:
    """Load cross-season player averages from NBA API cache."""
    from src.prediction.player_props import _get_all_player_avgs

    all_rows = []
    for season in seasons:
        print(f"  [data] Loading {season}...")
        rows = _get_all_player_avgs(season)
        for r in rows:
            r["season"] = season
        all_rows.extend(rows)
        time.sleep(0.2)

    df = pd.DataFrame(all_rows)
    print(f"  [data] Loaded {len(df)} player-season rows")
    return df


def retrain_props_temporal_cv(
    stats: list[str] = None,
    seasons: list[str] = None,
    dry_run: bool = False,
    threshold: float = 0.08,
    exclude_player_ids: list[int] = None,
) -> dict:
    """Run temporal CV retrain for given stats. Returns {stat: {holdout_r2, holdout_mae, ...}}."""
    stats   = list(stats or _STATS)
    seasons = seasons or ["2022-23", "2023-24", "2024-25"]
    exclude_player_ids = exclude_player_ids or []

    df = _load_training_data(seasons)

    if exclude_player_ids:
        df = filter_excluded_players(df, exclude_player_ids)
        print(f"  [train] Excluded {len(exclude_player_ids)} player IDs")

    # Sort chronologically (season-level: no game_date; uses 'season' column ordering)
    df_sorted = sort_chronologically(df, date_col="game_date")
    tscv = make_temporal_split(df_sorted, date_col="game_date", n_splits=5)

    # Add noise-injected rolling columns to simulate player_props.train_props behaviour
    rng = np.random.default_rng(0)
    for col, scale in [
        ("pts", 0.15), ("reb", 0.12), ("ast", 0.20), ("min", 0.12),
        ("fg3m", 0.25), ("stl", 0.30), ("blk", 0.30), ("tov", 0.20),
    ]:
        noise = rng.normal(0.0, scale, size=len(df_sorted))
        df_sorted[f"{col}_roll"] = (df_sorted.get(f"season_{col}", 0) * (1.0 + noise)).clip(lower=0.0)

    # Holdout = last TimeSeriesSplit fold's test indices
    all_idx = np.arange(len(df_sorted))
    splits = list(tscv.split(all_idx))
    train_idx, holdout_idx = splits[-1]

    results = {}
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    for stat in stats:
        feat_cols = [c for c in _FEAT_COLS if c != f"season_{stat}"]
        # Ensure all feature columns exist (fill missing with 0)
        for col in feat_cols:
            if col not in df_sorted.columns:
                df_sorted[col] = 0.0

        X = df_sorted[feat_cols].fillna(0.0).values
        y_col = f"season_{stat}"
        if y_col not in df_sorted.columns:
            print(f"  [skip] {stat}: label column missing")
            continue
        y = df_sorted[y_col].values

        X_train, y_train = X[train_idx], y[train_idx]
        X_hold,  y_hold  = X[holdout_idx], y[holdout_idx]

        print(f"\n  [train] {stat.upper()} — {len(y_train)} train, {len(y_hold)} holdout")
        best_model = run_grid_search(stat, X_train, y_train, tscv, n_jobs=4)

        # Holdout metrics
        y_pred_hold  = best_model.predict(X_hold)
        y_pred_train = best_model.predict(X_train)
        holdout_mae  = mean_absolute_error(y_hold, y_pred_hold)
        holdout_r2   = r2_score(y_hold, y_pred_hold)
        train_mae    = mean_absolute_error(y_train, y_pred_train)
        train_r2     = r2_score(y_train, y_pred_train)
        gap = abs(train_r2 - holdout_r2)

        status = "WARN gap>{:.2f}".format(threshold) if gap > threshold else "OK"
        print(f"  [{status}] {stat.upper()} train_r2={train_r2:.3f} holdout_r2={holdout_r2:.3f} gap={gap:.3f}")

        if not dry_run:
            model_path = _MODEL_DIR / f"props_{stat}.json"
            best_model.save_model(str(model_path))
            print(f"  [save] Model -> {model_path}")

        results[stat] = {
            "holdout_r2":    round(holdout_r2, 4),
            "holdout_mae":   round(holdout_mae, 4),
            "holdout_n":     int(len(y_hold)),
            "train_r2":      round(train_r2, 4),
            "train_mae":     round(train_mae, 4),
            "train_n":       int(len(y_train)),
            "needs_retrain": gap > threshold,
        }

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrain prop models with temporal CV + grid search")
    parser.add_argument("--stats",     nargs="+", default=list(_STATS))
    parser.add_argument("--seasons",   nargs="+", default=["2022-23", "2023-24", "2024-25"])
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--exclude",   nargs="*", type=int, default=[])
    args = parser.parse_args()

    print(f"[retrain] Stats: {args.stats}  dry_run={args.dry_run}  threshold={args.threshold}")
    results = retrain_props_temporal_cv(
        stats=args.stats,
        seasons=args.seasons,
        dry_run=args.dry_run,
        threshold=args.threshold,
        exclude_player_ids=args.exclude,
    )
    print("\n[retrain] Results:")
    for stat, m in results.items():
        gap = abs(m["train_r2"] - m["holdout_r2"])
        print(f"  {stat:5s}  holdout_r2={m['holdout_r2']:.3f}  gap={gap:.3f}  needs_retrain={m['needs_retrain']}")


if __name__ == "__main__":
    main()
