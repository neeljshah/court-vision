"""
prop_cv_split.py — Temporal CV helpers for player prop model training.

Public API
----------
    make_temporal_split(df, date_col, n_splits)         -> TimeSeriesSplit
    assert_no_future_leakage(train_idx, val_idx, dates) -> None
    filter_excluded_players(df, exclude_ids)             -> pd.DataFrame
    _objective_for_stat(stat)                            -> str
"""
from __future__ import annotations

import warnings
from typing import List

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

_COUNT_STATS = frozenset(("stl", "blk"))

_SEASON_ORDER = {
    "2020-21": 0,
    "2021-22": 1,
    "2022-23": 2,
    "2023-24": 3,
    "2024-25": 4,
    "2025-26": 5,
}


def make_temporal_split(
    df: pd.DataFrame,
    date_col: str = "game_date",
    n_splits: int = 5,
) -> TimeSeriesSplit:
    """Return a TimeSeriesSplit fitted to the chronological order of df.

    The caller is responsible for sorting df before using the returned splits.
    Use :func:`sort_chronologically` to get the sorted df.

    Ordering priority:
      1. date_col if present (game-level date)
      2. "season" column mapped to ordinal (season-level data)
      3. Row order unchanged if neither present (warns)

    Returns
    -------
    TimeSeriesSplit
        Configured with n_splits. Use tscv.split(np.arange(len(df_sorted)))
        after sorting df with sort_chronologically().
    """
    tscv = TimeSeriesSplit(n_splits=n_splits)

    if date_col not in df.columns and "season" not in df.columns:
        warnings.warn(
            "make_temporal_split: neither date_col nor 'season' found — "
            "row order preserved; splits may not be temporal",
            stacklevel=2,
        )

    return tscv


def sort_chronologically(
    df: pd.DataFrame,
    date_col: str = "game_date",
) -> pd.DataFrame:
    """Return df sorted chronologically for use with make_temporal_split splits.

    Ordering priority:
      1. date_col if present
      2. "season" column mapped to ordinal
      3. Row order unchanged (warns)
    """
    if date_col in df.columns:
        return df.sort_values(date_col).reset_index(drop=True)

    if "season" in df.columns:
        df_copy = df.copy()
        df_copy["_season_ord"] = df_copy["season"].map(_SEASON_ORDER).fillna(99)
        return (
            df_copy.sort_values("_season_ord")
            .drop(columns=["_season_ord"])
            .reset_index(drop=True)
        )

    warnings.warn(
        "sort_chronologically: neither date_col nor 'season' found — row order preserved",
        stacklevel=2,
    )
    return df.reset_index(drop=True)


def assert_no_future_leakage(
    train_idx: np.ndarray,
    val_idx: np.ndarray,
    dates: pd.Series,
) -> None:
    """Raise AssertionError if any train date is after any val date."""
    max_train = dates.iloc[train_idx].max()
    min_val = dates.iloc[val_idx].min()
    assert max_train <= min_val, (
        f"Future leakage: train contains date {max_train} "
        f"which is after val start {min_val}"
    )


def filter_excluded_players(
    df: pd.DataFrame,
    exclude_ids: List[int],
) -> pd.DataFrame:
    """Remove rows whose player_id is in exclude_ids. No-op if exclude_ids is empty."""
    if not exclude_ids:
        return df
    if "player_id" not in df.columns:
        return df
    return df[~df["player_id"].isin(exclude_ids)].reset_index(drop=True)


def _objective_for_stat(stat: str) -> str:
    """XGBoost objective for stat. Count stats use Poisson; others use squared error."""
    return "count:poisson" if stat in _COUNT_STATS else "reg:squarederror"


# Default XGBoost hyperparameters for prop regression.
_BASE_XGB_PARAMS = {
    "n_estimators":     200,
    "max_depth":        4,
    "learning_rate":    0.05,
    "subsample":        0.8,
    "colsample_bytree": 0.8,
    "random_state":     42,
}

# Stronger regularisation for low-signal count stats (stl, blk). The
# walk-forward report (PRED-02) found props_stl overfitting badly — a 0.18
# train−holdout R² gap. Shallower trees, heavier leaf weighting, and L1/L2
# penalties shrink that gap by curbing the model's capacity to memorise.
_COUNT_STAT_REGULARISATION = {
    "max_depth":        3,     # shallower trees — less capacity to memorise
    "min_child_weight": 8,     # require more samples per leaf
    "reg_lambda":       2.0,   # stronger L2 shrinkage
    "reg_alpha":        0.5,   # L1 sparsity on weak splits
    "gamma":            0.5,   # minimum loss reduction to make a split
    "subsample":        0.7,   # heavier row subsampling
    "colsample_bytree": 0.7,   # heavier column subsampling
}


def xgb_params_for_stat(stat: str) -> dict:
    """Return XGBoost hyperparameters tuned for a prop stat.

    High-signal stats (pts/reb/ast/fg3m/tov) use the base parameters. Low-signal
    count stats (stl, blk) — which the walk-forward report flagged as overfit —
    receive stronger regularisation to close the train/holdout gap.

    Args:
        stat: Prop stat name.

    Returns:
        A kwargs dict ready to splat into ``xgboost.XGBRegressor(**params)``,
        including the per-stat ``objective``.
    """
    params = dict(_BASE_XGB_PARAMS)
    params["objective"] = _objective_for_stat(stat)
    if stat in _COUNT_STATS:
        params.update(_COUNT_STAT_REGULARISATION)
    return params
