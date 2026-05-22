"""
test_prop_regularisation.py -- Tests for per-stat prop regularisation (PRED-08).

The walk-forward report (PRED-02) flagged props_stl as overfit (train 0.24,
holdout 0.06 — a 0.18 gap). xgb_params_for_stat() gives the low-signal count
stats stronger regularisation to close that gap.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

import pytest  # noqa: E402

from src.prediction.prop_cv_split import xgb_params_for_stat  # noqa: E402

_HIGH_SIGNAL = ["pts", "reb", "ast", "fg3m", "tov"]
_COUNT_STATS = ["stl", "blk"]


@pytest.fixture
def empty_models(tmp_path):
    """An empty model dir so tests see the static layering, not tuned files."""
    return str(tmp_path)


def test_high_signal_stats_use_base_params(empty_models):
    """pts/reb/ast use the base depth-4 config with no extra regularisation."""
    for stat in _HIGH_SIGNAL:
        p = xgb_params_for_stat(stat, model_dir=empty_models)
        assert p["max_depth"] == 4
        assert "min_child_weight" not in p
        assert "gamma" not in p


def test_count_stats_get_shallower_trees(empty_models):
    """stl/blk train shallower trees than the high-signal stats."""
    for stat in _COUNT_STATS:
        assert (xgb_params_for_stat(stat, model_dir=empty_models)["max_depth"]
                < xgb_params_for_stat("pts", model_dir=empty_models)["max_depth"])


def test_count_stats_get_l1_l2_and_leaf_penalties(empty_models):
    """stl/blk carry the regularisation knobs the base config lacks."""
    for stat in _COUNT_STATS:
        p = xgb_params_for_stat(stat, model_dir=empty_models)
        assert p["min_child_weight"] >= 8
        assert p["reg_lambda"] > 0
        assert p["reg_alpha"] > 0
        assert p["gamma"] > 0


def test_count_stats_subsample_more_aggressively(empty_models):
    """stl/blk use heavier row/column subsampling than the base config."""
    for stat in _COUNT_STATS:
        p = xgb_params_for_stat(stat, model_dir=empty_models)
        assert p["subsample"] < 0.8
        assert p["colsample_bytree"] < 0.8


def test_count_stats_keep_poisson_objective(empty_models):
    """Regularisation does not disturb the Poisson objective for count stats."""
    assert xgb_params_for_stat("stl", model_dir=empty_models)["objective"] == "count:poisson"
    assert xgb_params_for_stat("blk", model_dir=empty_models)["objective"] == "count:poisson"
    assert xgb_params_for_stat("pts", model_dir=empty_models)["objective"] == "reg:squarederror"


def test_params_are_splattable_into_xgbregressor(empty_models):
    """The returned dict is valid XGBRegressor kwargs."""
    from xgboost import XGBRegressor
    for stat in _HIGH_SIGNAL + _COUNT_STATS:
        model = XGBRegressor(**xgb_params_for_stat(stat, model_dir=empty_models))
        assert model.get_params()["random_state"] == 42


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
