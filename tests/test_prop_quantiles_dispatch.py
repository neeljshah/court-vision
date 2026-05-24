"""test_prop_quantiles_dispatch.py — q50 dispatch + quantile interval tests.

Cycles 26-29: predict_pergame() routes _USE_Q50_STATS through the quantile
median model; _Q50_LGB_BACKEND_STATS specifically loads the LGB variant.
predict_pergame_quantiles() produces ordered (q10, q50, q90) intervals.
"""
from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.prop_pergame import (  # noqa: E402
    _load_q50_model, feature_columns, predict_pergame, train_pergame_models,
)
from src.prediction.prop_quantiles import (  # noqa: E402
    predict_pergame_quantiles, train_quantile_models,
)
from tests.test_prop_pergame import _train_for_stack  # noqa: E402


def test_load_q50_model_xgb_backend(tmp_path):
    """_load_q50_model returns an XGBRegressor for BLK (XGB backend)."""
    import xgboost as xgb
    _train_for_stack(tmp_path)
    train_quantile_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    m = _load_q50_model("blk", str(tmp_path))
    assert m is not None, "BLK q50 model failed to load"
    assert isinstance(m, xgb.XGBRegressor), f"expected XGBRegressor, got {type(m)}"


def test_load_q50_model_lgb_backend(tmp_path):
    """_load_q50_model returns the LGB variant for REB (LGB backend in _Q50_LGB_BACKEND_STATS)."""
    import xgboost as xgb
    _train_for_stack(tmp_path)
    train_quantile_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    m = _load_q50_model("reb", str(tmp_path))
    assert m is not None, "REB q50 model failed to load"
    assert not isinstance(m, xgb.XGBRegressor), \
        f"REB should load LGB-q50 per _Q50_LGB_BACKEND_STATS, got {type(m)}"
    # LightGBM sklearn wrapper exposes the booster_ attribute.
    assert hasattr(m, "booster_") or "lightgbm" in type(m).__module__.lower(), \
        f"expected a LightGBM model, got {type(m).__module__}.{type(m).__name__}"


def test_predict_pergame_dispatches_to_q50_for_blk(tmp_path):
    """predict_pergame('blk', ...) routes through q50 and returns a sane non-negative."""
    import math
    _train_for_stack(tmp_path)
    train_pergame_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path), min_prior=6)
    train_quantile_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    feat = {c: 1.0 for c in feature_columns()}
    pred = predict_pergame("blk", feat, model_dir=str(tmp_path))
    assert pred is not None, "BLK q50 prediction returned None"
    assert isinstance(pred, float), f"expected float, got {type(pred)}"
    assert math.isfinite(pred), f"BLK prediction not finite: {pred}"
    assert pred >= 0.0, f"BLK should be non-negative, got {pred}"


def test_predict_pergame_uses_blend_for_pts(tmp_path):
    """PTS is NOT in _USE_Q50_STATS: predict_pergame must still work without a q50 file."""
    _train_for_stack(tmp_path)
    train_pergame_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path), min_prior=6)
    train_quantile_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    # Remove the PTS q50 artifact entirely — the legacy 3-way blend must still serve PTS.
    pts_q50 = tmp_path / "quantile_pergame_pts_q50.json"
    if pts_q50.exists():
        pts_q50.unlink()
    feat = {c: 1.0 for c in feature_columns()}
    pred = predict_pergame("pts", feat, model_dir=str(tmp_path))
    assert pred is not None, "PTS prediction must work without the q50 artifact"
    assert pred >= 0.0


def test_predict_pergame_quantiles_returns_intervals(tmp_path):
    """predict_pergame_quantiles yields ordered (q10, q50, q90) intervals."""
    _train_for_stack(tmp_path)
    train_quantile_models(gamelog_dir=str(tmp_path), model_dir=str(tmp_path))
    feat = {c: 1.0 for c in feature_columns()}
    out = predict_pergame_quantiles("blk", feat, model_dir=str(tmp_path))
    assert out is not None, "quantile prediction returned None"
    assert set(out.keys()) >= {"q10", "q50", "q90"}, f"missing quantile keys: {out.keys()}"
    assert out["q10"] <= out["q50"] <= out["q90"], \
        f"quantiles not ordered: q10={out['q10']} q50={out['q50']} q90={out['q90']}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
