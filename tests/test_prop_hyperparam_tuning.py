"""
test_prop_hyperparam_tuning.py -- Tests for grid-search param wiring (PRED-12).

prop_grid_search writes hyperparams_{stat}.json; xgb_params_for_stat() now
picks those tuned params up automatically, overriding the static defaults.
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_cv_split import xgb_params_for_stat  # noqa: E402


def test_defaults_used_when_no_tuned_file(tmp_path):
    """With no hyperparams file, the static base defaults are returned."""
    params = xgb_params_for_stat("pts", model_dir=str(tmp_path))
    assert params["max_depth"] == 4
    assert params["n_estimators"] == 200
    assert params["objective"] == "reg:squarederror"


def test_tuned_params_override_defaults(tmp_path):
    """A hyperparams_{stat}.json file overrides the static defaults."""
    (tmp_path / "hyperparams_pts.json").write_text(json.dumps({
        "stat": "pts",
        "best_params": {"max_depth": 6, "learning_rate": 0.03, "n_estimators": 350},
        "best_cv_r2": 0.52,
    }), encoding="utf-8")

    params = xgb_params_for_stat("pts", model_dir=str(tmp_path))
    assert params["max_depth"] == 6           # tuned value won
    assert params["learning_rate"] == 0.03
    assert params["n_estimators"] == 350
    assert params["objective"] == "reg:squarederror"   # objective preserved


def test_count_stat_regularisation_outranks_stale_tuning(tmp_path):
    """For stl/blk the overfit-fix regularisation is authoritative.

    The pre-existing grid search for the count stats was run on a leaky CV
    split (best_cv_r2 ≈ 0.79 vs a 0.06 realised holdout). Its params must NOT
    silently undo the PRED-08 regularisation that closes the overfit gap.
    """
    (tmp_path / "hyperparams_stl.json").write_text(json.dumps({
        "stat": "stl",
        "best_params": {"max_depth": 9, "subsample": 1.0},  # an overfit-y tuning
    }), encoding="utf-8")

    params = xgb_params_for_stat("stl", model_dir=str(tmp_path))
    assert params["max_depth"] == 3           # regularisation wins, not the tuned 9
    assert params["subsample"] == 0.7         # regularisation wins, not the tuned 1.0
    assert params["min_child_weight"] == 8
    assert params["objective"] == "count:poisson"


def test_corrupt_hyperparams_file_falls_back_to_defaults(tmp_path):
    """A malformed hyperparams file is ignored — defaults are used."""
    (tmp_path / "hyperparams_reb.json").write_text("{not valid json", encoding="utf-8")
    params = xgb_params_for_stat("reb", model_dir=str(tmp_path))
    assert params["max_depth"] == 4


def test_params_remain_valid_xgb_kwargs(tmp_path):
    """The merged params still construct a valid XGBRegressor."""
    from xgboost import XGBRegressor
    (tmp_path / "hyperparams_ast.json").write_text(json.dumps({
        "best_params": {"max_depth": 5, "subsample": 0.9},
    }), encoding="utf-8")
    model = XGBRegressor(**xgb_params_for_stat("ast", model_dir=str(tmp_path)))
    assert model.get_params()["max_depth"] == 5


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
