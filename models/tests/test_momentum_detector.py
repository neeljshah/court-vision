"""Tests for MomentumDetector (ML-03).

TDD RED phase — these tests define the required behavior.
Run after implementing models/momentum_detector.py to verify GREEN.
"""

import pandas as pd
import pytest

from models.momentum_detector import MomentumDetector


HIGH_MOMENTUM = {
    "scoring_run": 12,
    "possession_streak": 6,
    "scoring_run_prev": 6,
    "streak_delta": 4,
}
LOW_MOMENTUM = {
    "scoring_run": 1,
    "possession_streak": 1,
    "scoring_run_prev": 1,
    "streak_delta": 0,
}


@pytest.fixture(scope="module")
def trained_model():
    """Return a MomentumDetector trained on synthetic data (empty DataFrame)."""
    m = MomentumDetector()
    m.fit(pd.DataFrame())
    return m


class TestMomentumDetector:
    def test_predict_returns_0_or_1(self, trained_model):
        """predict() returns int 0 or 1."""
        result = trained_model.predict(HIGH_MOMENTUM)
        assert isinstance(result, int), f"Expected int, got {type(result)}"
        assert result in (0, 1), f"Expected 0 or 1, got {result}"

    def test_predict_low_momentum_returns_0_or_1(self, trained_model):
        """predict() on low-momentum features returns 0 or 1."""
        result = trained_model.predict(LOW_MOMENTUM)
        assert result in (0, 1), f"Expected 0 or 1, got {result}"

    def test_predict_high_momentum_returns_1(self, trained_model):
        """High scoring_run + high streak_delta should be classified as swing point (1)."""
        result = trained_model.predict(HIGH_MOMENTUM)
        assert result == 1, (
            f"Expected 1 (momentum shift) for scoring_run=12, streak_delta=4, got {result}"
        )

    def test_predict_proba_returns_float_in_range(self, trained_model):
        """predict_proba() returns float in [0, 1]."""
        prob = trained_model.predict_proba(HIGH_MOMENTUM)
        assert isinstance(prob, float), f"Expected float, got {type(prob)}"
        assert 0.0 <= prob <= 1.0, f"Expected [0, 1], got {prob}"

    def test_fit_empty_df_uses_synthetic(self):
        """fit() on empty DataFrame does not raise — uses synthetic seed data."""
        m = MomentumDetector()
        m.fit(pd.DataFrame())  # must not raise
        result = m.predict(HIGH_MOMENTUM)
        assert result in (0, 1)

    def test_save_creates_joblib_file(self, trained_model):
        """save() writes models/artifacts/momentum_detector.joblib."""
        path = trained_model.save()
        assert path.exists(), f"Artifact not found at {path}"
        assert path.suffix == ".joblib"
        assert path.name == "momentum_detector.joblib"

    def test_load_round_trip(self, trained_model):
        """load() deserializes and produces identical predictions."""
        trained_model.save()
        m2 = MomentumDetector.load("momentum_detector")
        assert isinstance(m2, MomentumDetector)
        r1 = trained_model.predict(HIGH_MOMENTUM)
        r2 = m2.predict(HIGH_MOMENTUM)
        assert r1 == r2, f"Round-trip mismatch: {r1} vs {r2}"
