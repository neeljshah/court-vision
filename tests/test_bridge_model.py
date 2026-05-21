"""Tests for BridgeModel — CV-to-public-stat bridge."""

from __future__ import annotations

import sys
import os

import numpy as np
import pandas as pd
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.models.bridge_model import BridgeModel, _make_synthetic


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def synth_data():
    return _make_synthetic(n=400, seed=42)


@pytest.fixture(scope="module")
def fitted_model(synth_data):
    X_cv, X_pub, y = synth_data
    model = BridgeModel(n_estimators=80)
    model.fit(X_cv.iloc[:300], X_pub.iloc[:300], y.iloc[:300])
    return model


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

def test_fit_succeeds(synth_data):
    """fit() completes without error and sets is_fitted=True."""
    X_cv, X_pub, y = synth_data
    model = BridgeModel(n_estimators=50)
    model.fit(X_cv.iloc[:200], X_pub.iloc[:200], y.iloc[:200])
    assert model.is_fitted


def test_predict_shape(fitted_model, synth_data):
    """predict() returns array of shape (n_samples, n_targets)."""
    X_cv, X_pub, y = synth_data
    X_cv_ts = X_cv.iloc[300:]
    X_pub_ts = X_pub.iloc[300:]
    preds = fitted_model.predict(X_cv_ts, X_pub_ts)
    assert preds.shape == (100, len(y.columns)), (
        f"Expected (100, {len(y.columns)}), got {preds.shape}"
    )


def test_predict_shape_pub_only_fallback(fitted_model, synth_data):
    """predict() with X_cv=None returns correct shape (public-only fallback)."""
    _, X_pub, y = synth_data
    X_pub_ts = X_pub.iloc[300:]
    preds = fitted_model.predict(None, X_pub_ts)
    assert preds.shape == (100, len(y.columns))


def test_r2_on_synthetic_holdout(fitted_model, synth_data):
    """Mean R² on holdout ≥ 0.3 with CV features available."""
    X_cv, X_pub, y = synth_data
    r2 = fitted_model.score(X_cv.iloc[300:], X_pub.iloc[300:], y.iloc[300:])
    assert r2 >= 0.3, f"R² {r2:.4f} < 0.3"


def test_pub_only_fallback_no_crash(fitted_model, synth_data):
    """Public-only fallback completes without crash and returns finite values."""
    _, X_pub, y = synth_data
    preds = fitted_model.predict(None, X_pub.iloc[300:])
    assert np.isfinite(preds).all()


def test_partial_cv_nan_imputed(fitted_model, synth_data):
    """Partial NaN in CV input is imputed, predict() still runs."""
    X_cv, X_pub, y = synth_data
    X_cv_nan = X_cv.iloc[300:].copy()
    X_cv_nan.iloc[:, :3] = np.nan  # zero out first 3 CV columns
    preds = fitted_model.predict(X_cv_nan, X_pub.iloc[300:])
    assert preds.shape[0] == 100
    assert np.isfinite(preds).all()


def test_save_load_roundtrip(tmp_path, fitted_model, synth_data):
    """save/load roundtrip preserves predictions."""
    X_cv, X_pub, y = synth_data
    path = str(tmp_path / "bridge.pkl")
    fitted_model.save(path)
    loaded = BridgeModel.load(path)
    preds_orig = fitted_model.predict(X_cv.iloc[300:], X_pub.iloc[300:])
    preds_load = loaded.predict(X_cv.iloc[300:], X_pub.iloc[300:])
    np.testing.assert_allclose(preds_orig, preds_load, rtol=1e-5)


def test_predict_before_fit_raises():
    """predict() raises RuntimeError when called before fit()."""
    model = BridgeModel()
    _, X_pub, _ = _make_synthetic(n=10)
    with pytest.raises(RuntimeError, match="fit"):
        model.predict(None, X_pub)
