"""Synthetic coverage for combinatorial purged cross-validation."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit import cpcv


def _frame(seed: int = 7, n_dates: int = 120, per_date: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = np.repeat(pd.date_range("2024-01-01", periods=n_dates, freq="D"), per_date)
    size = len(dates)
    base = rng.normal(size=size)
    planted = rng.normal(size=size)
    frame = pd.DataFrame({"gameDate": dates, "base": base, "planted": planted,
                          "target": 1.5 * base + 3.0 * planted + rng.normal(scale=0.2, size=size)})
    for number in range(16):
        frame["noise{0}".format(number)] = rng.normal(size=size)
    return frame


def _splits(frame: pd.DataFrame) -> list[tuple[np.ndarray, np.ndarray]]:
    return list(cpcv.cpcv_splits(frame["gameDate"], n_groups=6, n_test_groups=2, embargo_blocks=1))


def test_splits_purge_shared_dates_and_embargo_the_next_block() -> None:
    frame = _frame()
    splits = _splits(frame)
    assert len(splits) == 15
    unique = np.sort(frame["gameDate"].drop_duplicates().to_numpy())
    for train_index, test_index in splits:
        assert len(train_index) and len(test_index)
        test_dates = set(frame["gameDate"].iloc[test_index])
        train_dates = set(frame["gameDate"].iloc[train_index])
        assert not test_dates & train_dates
        for stamp in test_dates:
            after = unique[unique > np.datetime64(stamp)]
            if len(after):
                assert pd.Timestamp(after[0]) not in train_dates


def test_zero_embargo_keeps_the_adjacent_block_and_rejects_bad_arguments() -> None:
    frame = _frame()
    unique = np.sort(frame["gameDate"].drop_duplicates().to_numpy())
    train_index, test_index = next(cpcv.cpcv_splits(frame["gameDate"], 6, 2, embargo_blocks=0))
    train_dates = set(frame["gameDate"].iloc[train_index])
    last = max(frame["gameDate"].iloc[test_index])
    assert pd.Timestamp(unique[unique > np.datetime64(last)][0]) in train_dates
    with pytest.raises(ValueError):
        list(cpcv.cpcv_splits(frame["gameDate"], n_groups=3, n_test_groups=3))
    with pytest.raises(ValueError):
        list(cpcv.cpcv_splits(frame["gameDate"].iloc[:4], n_groups=6, n_test_groups=2))


def test_planted_feature_set_improves_on_most_paths() -> None:
    frame = _frame()
    result = cpcv.evaluate_paths(frame, "target", ["base", "planted"], _splits(frame),
                                 baseline_cols=["base"])
    assert result["n_paths"] == 15
    assert result["share_improving"] > 0.8
    assert result["median_lift"] > 0.0
    assert result["p10_lift"] <= result["median_lift"] <= result["p90_lift"]


def test_pure_noise_feature_sets_give_pbo_near_one_half() -> None:
    # A single 15-path corpus swings 0.07-0.87, so average PBO over corpora:
    # measured mean 0.53 across these seeds, i.e. selection is a coin flip.
    sets = {"set{0}".format(number): ["noise{0}".format(2 * number), "noise{0}".format(2 * number + 1)]
            for number in range(8)}
    scores = []
    for seed in range(6):
        frame = _frame(seed=seed)
        frame["target"] = np.random.default_rng(100 + seed).normal(size=len(frame))
        result = cpcv.probability_of_backtest_overfitting(frame, "target", sets, _splits(frame))
        assert result["n_paths"] == 15 and result["n_sets"] == 8
        scores.append(result["pbo"])
    assert 0.35 <= float(np.mean(scores)) <= 0.65


def test_dominant_feature_set_has_low_pbo() -> None:
    frame = _frame()
    sets = {"real": ["base", "planted"], "noise_a": ["noise0", "noise1"], "noise_b": ["noise2", "noise3"]}
    result = cpcv.probability_of_backtest_overfitting(frame, "target", sets, _splits(frame))
    assert result["pbo"] == 0.0
    assert set(result["is_best_per_path"]) == {"real"}
