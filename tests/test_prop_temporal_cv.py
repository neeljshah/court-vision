"""
test_prop_temporal_cv.py — Temporal CV split contracts.

Tests verify src/prediction/prop_cv_split.py implements leakage-safe splits.
"""
import numpy as np
import pandas as pd
import pytest


def _make_date_df(n: int = 300) -> pd.DataFrame:
    """Synthetic sorted DataFrame with game_date and pts columns."""
    dates = pd.date_range("2023-01-01", "2025-12-31", periods=n)
    rng = np.random.default_rng(42)
    return pd.DataFrame({"game_date": dates, "pts": rng.normal(20, 5, n)})


def test_temporal_split() -> None:
    """make_temporal_split returns TimeSeriesSplit with n_splits=5 and
    all fold train indices strictly before val indices in date ordering."""
    prop_cv_split = pytest.importorskip("src.prediction.prop_cv_split")
    make_temporal_split = prop_cv_split.make_temporal_split

    df = _make_date_df(300)
    tscv = make_temporal_split(df, date_col="game_date", n_splits=5)
    assert tscv.n_splits == 5

    X = np.zeros((len(df), 1))
    dates = df["game_date"].reset_index(drop=True)
    for train_idx, val_idx in tscv.split(X):
        assert len(train_idx) > 0 and len(val_idx) > 0
        assert (
            dates.iloc[train_idx].max() < dates.iloc[val_idx].min()
        ), "Train dates must be strictly before val dates"


def test_no_future_leakage() -> None:
    """For every fold produced by make_temporal_split, max(train_dates) < min(val_dates)."""
    prop_cv_split = pytest.importorskip("src.prediction.prop_cv_split")
    make_temporal_split = prop_cv_split.make_temporal_split

    df = _make_date_df(300)
    dates = df["game_date"].reset_index(drop=True)
    X = np.zeros((len(df), 1))
    tscv = make_temporal_split(df, date_col="game_date", n_splits=5)

    for fold_i, (train_idx, val_idx) in enumerate(tscv.split(X)):
        max_train = dates.iloc[train_idx].max()
        min_val = dates.iloc[val_idx].min()
        assert max_train < min_val, (
            f"Fold {fold_i}: future leakage detected — "
            f"train max {max_train} >= val min {min_val}"
        )


def test_rolling_features_per_fold() -> None:
    """Documents leakage risk: full-dataset rolling mean differs from
    train-window rolling mean for validation rows.

    The implementation must compute rolling features per-fold using only
    the train window, NOT the full dataset.
    """
    rng = np.random.default_rng(0)
    n = 200
    dates = pd.date_range("2023-01-01", periods=n, freq="3D")
    pts = rng.normal(20, 5, n)
    df = pd.DataFrame({"game_date": dates, "pts": pts})

    # Leaky: rolling computed on full dataset
    df["pts_roll_leaky"] = df["pts"].rolling(10, min_periods=1).mean()

    # Train window: first 160 rows; val: last 40 rows
    train_end = 160
    val_start = train_end
    train_pts = df["pts"].iloc[:train_end]
    roll_train = train_pts.rolling(10, min_periods=1).mean()

    # Last value of train rolling for the val window
    last_train_roll = roll_train.iloc[-1]
    val_leaky = df["pts_roll_leaky"].iloc[val_start]

    # They should differ (leaky uses future data to compute the rolling mean)
    assert val_leaky != last_train_roll, (
        "Leaky and non-leaky rolling values should differ — "
        "if equal, test setup is wrong"
    )


def test_poisson_objective_selector() -> None:
    """_objective_for_stat returns correct XGBoost objective per stat type."""
    prop_cv_split = pytest.importorskip("src.prediction.prop_cv_split")
    objective_for_stat = prop_cv_split._objective_for_stat

    poisson_stats = ("stl", "blk")
    regression_stats = ("pts", "reb", "ast", "fg3m", "tov")

    for stat in poisson_stats:
        obj = objective_for_stat(stat)
        assert obj == "count:poisson", (
            f"Expected 'count:poisson' for {stat}, got {obj!r}"
        )

    for stat in regression_stats:
        obj = objective_for_stat(stat)
        assert obj == "reg:squarederror", (
            f"Expected 'reg:squarederror' for {stat}, got {obj!r}"
        )
