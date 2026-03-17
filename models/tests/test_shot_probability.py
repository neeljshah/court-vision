"""Tests for ShotProbabilityModel (ML-01).

TDD RED phase — these tests define the required behavior.
Run after implementing models/shot_probability.py to verify GREEN.
"""

import pathlib

import pandas as pd
import pytest

from models.shot_probability import ShotProbabilityModel


PAINT_FEATURES = {
    "defender_dist": 2.0,
    "shot_angle": 30.0,
    "fatigue_proxy": 0.3,
    "court_zone": "paint",
}
THREE_FEATURES = {
    "defender_dist": 2.0,
    "shot_angle": 30.0,
    "fatigue_proxy": 0.3,
    "court_zone": "three",
}


@pytest.fixture(scope="module")
def trained_model():
    """Return a ShotProbabilityModel trained on synthetic data (empty DataFrame)."""
    m = ShotProbabilityModel()
    m.fit(pd.DataFrame())
    return m


class TestShotProbabilityModel:
    def test_predict_returns_float_in_range(self, trained_model):
        """predict() returns a float between 0 and 1 inclusive."""
        p = trained_model.predict(PAINT_FEATURES)
        assert isinstance(p, float), f"Expected float, got {type(p)}"
        assert 0.0 <= p <= 1.0, f"Expected [0, 1], got {p}"

    def test_predict_paint_higher_than_three(self, trained_model):
        """Paint shot probability > three-point shot probability (all else equal)."""
        p_paint = trained_model.predict(PAINT_FEATURES)
        p_three = trained_model.predict(THREE_FEATURES)
        assert p_paint > p_three, (
            f"Paint probability {p_paint:.4f} should exceed three probability {p_three:.4f}"
        )

    def test_predict_closer_defender_higher_probability(self, trained_model):
        """Closer defender (lower dist) → higher shot probability."""
        close = trained_model.predict(
            {"defender_dist": 0.5, "shot_angle": 30.0, "fatigue_proxy": 0.3, "court_zone": "midrange"}
        )
        far = trained_model.predict(
            {"defender_dist": 10.0, "shot_angle": 30.0, "fatigue_proxy": 0.3, "court_zone": "midrange"}
        )
        assert close > far, (
            f"Close defender prob {close:.4f} should exceed far defender prob {far:.4f}"
        )

    def test_fit_empty_df_uses_synthetic(self):
        """fit() on empty DataFrame does not raise — uses synthetic seed data."""
        m = ShotProbabilityModel()
        m.fit(pd.DataFrame())  # must not raise
        p = m.predict(PAINT_FEATURES)
        assert 0.0 <= p <= 1.0

    def test_save_creates_joblib_file(self, trained_model):
        """save() writes models/artifacts/shot_probability.joblib."""
        path = trained_model.save()
        assert path.exists(), f"Artifact not found at {path}"
        assert path.suffix == ".joblib"
        assert path.name == "shot_probability.joblib"

    def test_load_round_trip(self, trained_model):
        """load() deserializes and produces identical predictions."""
        trained_model.save()
        m2 = ShotProbabilityModel.load("shot_probability")
        assert isinstance(m2, ShotProbabilityModel)
        p1 = trained_model.predict(PAINT_FEATURES)
        p2 = m2.predict(PAINT_FEATURES)
        assert abs(p1 - p2) < 1e-6, f"Round-trip mismatch: {p1} vs {p2}"
