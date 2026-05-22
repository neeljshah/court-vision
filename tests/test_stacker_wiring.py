"""
test_stacker_wiring.py -- Tests for stacker integration into predict_props (PRED-10).

The multi-model stacker (XGBoost + LightGBM + CatBoost) was trained-capable but
predict_props only ever used a single XGBoost model. _predict_with_models now
prefers the stacker ensemble, falling back cleanly to XGBoost when no stacker
has been trained — a zero-regression wiring.
"""

from __future__ import annotations

import os
import sys

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.player_props import (  # noqa: E402
    _PROP_STATS,
    _predict_with_models,
    _try_stacker_prediction,
)


def test_try_stacker_returns_none_when_no_stacker():
    """With no trained stacker, _try_stacker_prediction returns None so the
    caller falls back to the existing XGBoost path (zero regression)."""
    import src.prediction.prop_stacker as ps
    # Force the "no stacker" branch regardless of what is on disk.
    _orig = ps.load_stacker
    ps.load_stacker = lambda stat, models_dir=None: None
    try:
        assert _try_stacker_prediction([[0.0, 1.0]], "pts") is None
    finally:
        ps.load_stacker = _orig


def test_try_stacker_uses_ensemble_when_present(monkeypatch):
    """When a stacker bundle exists, its ensemble prediction is returned."""
    import src.prediction.prop_stacker as ps

    monkeypatch.setattr(ps, "load_stacker",
                        lambda stat, models_dir=None: {"meta": object(), "learners": ["xgb"]})
    monkeypatch.setattr(ps, "predict_ensemble",
                        lambda X, stat, models_dir=None: np.array([24.5]))

    val = _try_stacker_prediction([[0.0, 1.0]], "pts")
    assert val == 24.5


def test_try_stacker_rejects_non_finite(monkeypatch):
    """A NaN ensemble prediction is treated as unavailable -> None."""
    import src.prediction.prop_stacker as ps
    monkeypatch.setattr(ps, "load_stacker",
                        lambda stat, models_dir=None: {"meta": object(), "learners": ["xgb"]})
    monkeypatch.setattr(ps, "predict_ensemble",
                        lambda X, stat, models_dir=None: np.array([float("nan")]))
    assert _try_stacker_prediction([[0.0]], "pts") is None


def test_try_stacker_swallows_errors(monkeypatch):
    """A failing stacker never propagates — it returns None."""
    import src.prediction.prop_stacker as ps

    def boom(stat, models_dir=None):
        raise RuntimeError("stacker exploded")

    monkeypatch.setattr(ps, "load_stacker", boom)
    assert _try_stacker_prediction([[0.0]], "pts") is None


def test_predict_with_models_returns_all_seven_stats():
    """_predict_with_models still produces a prediction for every prop stat."""
    feats = {f"season_{s}": 10.0 for s in _PROP_STATS}
    feats.update({f"{s}_roll": 11.0 for s in _PROP_STATS})
    predictions, confidence = _predict_with_models(feats)
    assert set(predictions.keys()) == set(_PROP_STATS)
    assert all(v >= 0.0 for v in predictions.values())
    assert confidence in ("ensemble", "model", "rolling")


def test_confidence_is_ensemble_when_stacker_used(monkeypatch):
    """When the stacker supplies predictions, confidence is reported 'ensemble'."""
    import src.prediction.prop_stacker as ps
    monkeypatch.setattr(ps, "load_stacker",
                        lambda stat, models_dir=None: {"meta": object(), "learners": ["xgb"]})
    monkeypatch.setattr(ps, "predict_ensemble",
                        lambda X, stat, models_dir=None: np.array([15.0]))

    feats = {f"season_{s}": 10.0 for s in _PROP_STATS}
    _predictions, confidence = _predict_with_models(feats)
    assert confidence == "ensemble"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
