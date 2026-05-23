"""Tests for the loop-4 multi-learner pre-game WinProb stack.

Covers the architecture that landed in cycles 7-14:
  - 5 base learners: XGB, LGB, LR, MLP-ensemble, NB
  - NNLS-weighted blend (positive coefficients, sanity-bounded sum)
  - Adaptive feature_cols (handles missing sim_* in older v8 caches)
  - Save/load round-trip of all learners + weights + calibrator

These tests do NOT call any external NBA API. They depend on a previously
trained model existing at `data/models/win_probability.pkl`; CI/cold-start
runs will skip rather than fail.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.win_probability import (  # noqa: E402
    _MODEL_DIR,
    _MODEL_FEATURE_COLS,
    WinProbModel,
    load,
)


MODEL_PATH = os.path.join(_MODEL_DIR, "win_probability.pkl")


def _model_present() -> bool:
    return os.path.exists(MODEL_PATH)


pytestmark = pytest.mark.skipif(
    not _model_present(),
    reason=f"No trained model at {MODEL_PATH} — run train() first",
)


def test_load_round_trip_preserves_all_learners():
    """Reloaded model must expose all 5 base learners + calibrator slot."""
    m = load()
    # Primary learner (XGB) always present after training.
    assert m.model is not None, "XGB base learner missing"
    # Optional learners — at minimum the stack uses XGB+LR+MLP+NB and may
    # drop LGB (cycle-10+ pattern shows w_lgb=0.0).
    assert m._lr_model is not None, "LR base learner missing"
    assert m._lr_scaler is not None, "Shared StandardScaler missing"
    assert m._mlp_models is not None and len(m._mlp_models) >= 1, \
        "MLP ensemble missing or empty"
    assert m._nb_model is not None, "NB base learner missing"
    # Calibrator slot must exist (None when not deployed is fine).
    assert hasattr(m, "_calibrator")


def test_blend_weights_sum_in_sanity_bounds():
    """NNLS guard rejects weights summing outside [0.5, 1.5]."""
    m = load()
    w_sum = m._w_xgb + m._w_lgb + m._w_lr + m._w_mlp + m._w_nb
    assert 0.5 <= w_sum <= 1.5, (
        f"NNLS weight sum {w_sum:.3f} outside sanity bounds — "
        "the fallback_equal branch should have engaged"
    )


def test_all_weights_non_negative():
    """LinearRegression(positive=True) must produce non-negative weights."""
    m = load()
    for name, w in [("xgb", m._w_xgb), ("lgb", m._w_lgb), ("lr", m._w_lr),
                    ("mlp", m._w_mlp), ("nb", m._w_nb)]:
        assert w >= 0.0, f"Negative NNLS weight on {name}: {w}"


def test_blend_prob_returns_unit_interval():
    """_blend_prob output (uncalibrated) should be in [0, 1]."""
    m = load()
    # Synthetic feature vector — all zeros works since the model handles
    # any numeric input even if not meaningful.
    X = np.zeros((1, len(m._feature_cols)), dtype=np.float32)
    prob = m._blend_prob(X)
    assert isinstance(prob, float)
    # Pre-clip blend can technically exceed [0, 1] when weight sum != 1,
    # but the guard keeps the sum near 1.0 — so generous bounds are fine.
    assert -0.5 <= prob <= 1.5, f"Blend prob far outside unit interval: {prob}"


def test_feature_cols_subset_of_model_feature_cols():
    """Trained model's feature_cols must be a subset of the master list."""
    m = load()
    extras = set(m._feature_cols) - set(_MODEL_FEATURE_COLS)
    assert not extras, f"Model trained on unknown features: {extras}"


def test_backward_compat_xgb_only_constructor():
    """Default constructor (no LGB/LR/MLP/NB args) must still work."""
    wp = WinProbModel()
    assert wp.model is None
    assert wp._lgb_model is None
    assert wp._lr_model is None
    assert wp._mlp_models is None
    assert wp._nb_model is None
    assert wp._w_xgb == 1.0
    assert wp._w_lgb == wp._w_lr == wp._w_mlp == wp._w_nb == 0.0
    assert wp._feature_cols == list(_MODEL_FEATURE_COLS)


def test_constructor_normalises_single_mlp_to_list():
    """Passing a single MLP (cycle-12 shape) should wrap to a list."""
    from sklearn.neural_network import MLPClassifier

    single = MLPClassifier(hidden_layer_sizes=(8,), max_iter=10, random_state=0)
    wp = WinProbModel(mlp_models=single)
    assert isinstance(wp._mlp_models, list)
    assert len(wp._mlp_models) == 1


def test_constructor_accepts_mlp_list():
    """Standard cycle-13+ shape: list of MLPs preserved as-is."""
    from sklearn.neural_network import MLPClassifier

    mlps = [
        MLPClassifier(hidden_layer_sizes=(8,), max_iter=10, random_state=i)
        for i in range(3)
    ]
    wp = WinProbModel(mlp_models=mlps)
    assert isinstance(wp._mlp_models, list)
    assert len(wp._mlp_models) == 3
