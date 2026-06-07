"""tests/test_reb_oppmodel.py — Unit tests for reb_opportunity_model.py."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.reb_opportunity_model import (
    is_enabled,
    train_reb_oppmodel,
    predict_reb_oppmodel,
    _extract_rate_features,
    _MIN_HEAD_FEATURES,
    _RATE_HEAD_FEATURES,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_row(
    *,
    target_min: float = 28.0,
    target_reb: float = 5.0,
    date: str = "2025-01-15",
    seed: int = 0,
) -> dict:
    """Construct a minimal synthetic row dict resembling build_pergame_dataset output."""
    rng = np.random.default_rng(seed)
    row: dict = {
        "date": date,
        "target_min": target_min,
        "target_reb": target_reb,
        "game_id": "fake_game",
        "player_id": 1234,
        "season": "2024-25",
        # Minutes-head features
        "l5_min": 28.0 + rng.uniform(-2, 2),
        "l10_min": 27.0 + rng.uniform(-2, 2),
        "std_min": 3.5,
        "ewma_min": 27.5,
        "prev_min": 30.0,
        "rest_days": 2.0,
        "is_b2b": 0.0,
        "is_b3b": 0.0,
        "days_since_last_game": 2.0,
        "games_since_long_absence": 0.0,
        "games_played": 55,
        "is_home": 1.0,
        # Rebound / rate features
        "l5_reb": 5.0 + rng.uniform(-1, 1),
        "l10_reb": 4.8,
        "std_reb": 1.8,
        "ewma_reb": 5.1,
        "prev_reb": 6.0,
        "bbref_orb_pct": 0.052,
        "bbref_drb_pct": 0.148,
        "bbref_trb_pct": 0.100,
        "opp_def_reb": 0.0,
        "team_oreb_pct_l5": 0.25,
        "opp_dreb_pct_l5": 0.72,
        "reb_chance_l5": 0.18,
    }
    return row


def _make_training_set(n: int = 200, seed: int = 42) -> list:
    """Generate n synthetic rows covering a range of minutes and reb values."""
    rng = np.random.default_rng(seed)
    rows = []
    base_date = "2025-01-"
    for i in range(n):
        mins = float(rng.integers(5, 42))
        reb = float(rng.poisson(max(1, mins * 0.18)))
        day = str((i % 28) + 1).zfill(2)
        row = _make_row(
            target_min=mins,
            target_reb=reb,
            date=f"2024-{str((i // 28 % 12) + 1).zfill(2)}-{day}",
            seed=i,
        )
        rows.append(row)
    return rows


# ── tests ─────────────────────────────────────────────────────────────────────

class TestIsEnabled:
    def test_default_off(self, monkeypatch):
        """Flag is OFF when the env var is absent."""
        monkeypatch.delenv("CV_PREGAME_REB_OPPMODEL", raising=False)
        assert is_enabled() is False

    def test_on_when_set(self, monkeypatch):
        monkeypatch.setenv("CV_PREGAME_REB_OPPMODEL", "1")
        assert is_enabled() is True

    def test_off_for_other_values(self, monkeypatch):
        for val in ("0", "false", "True", "yes", ""):
            monkeypatch.setenv("CV_PREGAME_REB_OPPMODEL", val)
            assert is_enabled() is False, f"Expected False for value={val!r}"


class TestExtractRateFeatures:
    def test_keys_present(self):
        row = _make_row()
        feats = _extract_rate_features(row)
        for k in _RATE_HEAD_FEATURES:
            assert k in feats, f"Missing key: {k}"

    def test_rates_are_finite(self):
        row = _make_row()
        feats = _extract_rate_features(row)
        for k, v in feats.items():
            assert np.isfinite(v), f"{k}={v} is not finite"

    def test_divide_by_zero_guarded(self):
        """When all min-form features are 0, rates should be 0 not NaN/inf."""
        row = _make_row()
        row["l5_min"] = 0.0
        row["l10_min"] = 0.0
        row["ewma_min"] = 0.0
        row["prev_min"] = 0.0
        feats = _extract_rate_features(row)
        for k, v in feats.items():
            assert np.isfinite(v), f"{k}={v} should be finite even with zero minutes"
            assert v >= 0.0, f"{k}={v} should be non-negative"


class TestTrainAndPredict:
    @pytest.fixture(scope="class")
    def artifact(self):
        rows = _make_training_set(n=300)
        return train_reb_oppmodel(rows)

    def test_predict_finite(self, artifact):
        row = _make_row()
        pred = predict_reb_oppmodel(artifact, row)
        assert np.isfinite(pred), f"Prediction should be finite, got {pred}"

    def test_predict_non_negative(self, artifact):
        row = _make_row()
        pred = predict_reb_oppmodel(artifact, row)
        assert pred >= 0.0, f"Prediction should be non-negative, got {pred}"

    def test_predict_below_ceiling(self, artifact):
        row = _make_row()
        pred = predict_reb_oppmodel(artifact, row, pred_ceiling=30.0)
        assert pred <= 30.0, f"Prediction exceeds ceiling: {pred}"

    def test_predict_plausible_range(self, artifact):
        """For a typical NBA player row, prediction should be in [0, 20]."""
        row = _make_row(target_min=30.0, target_reb=7.0)
        pred = predict_reb_oppmodel(artifact, row)
        assert 0.0 <= pred <= 20.0, f"Prediction out of plausible range: {pred}"

    def test_divide_by_zero_guarded(self, artifact):
        """Prediction should be finite even when all form min features are 0."""
        row = _make_row()
        row["l5_min"] = 0.0
        row["l10_min"] = 0.0
        row["ewma_min"] = 0.0
        row["prev_min"] = 0.0
        pred = predict_reb_oppmodel(artifact, row)
        assert np.isfinite(pred), f"Should not produce NaN/inf when mins=0: {pred}"

    def test_predict_varies_with_minutes(self, artifact):
        """Prediction should increase with expected minutes (ceteris paribus)."""
        row_low = _make_row()
        row_low["l5_min"] = 8.0
        row_low["l10_min"] = 8.0
        row_low["ewma_min"] = 8.0
        row_low["prev_min"] = 8.0

        row_high = _make_row()
        row_high["l5_min"] = 36.0
        row_high["l10_min"] = 36.0
        row_high["ewma_min"] = 36.0
        row_high["prev_min"] = 36.0

        pred_low  = predict_reb_oppmodel(artifact, row_low)
        pred_high = predict_reb_oppmodel(artifact, row_high)
        assert pred_high > pred_low, (
            f"Expected higher minutes to yield more rebounds: "
            f"low={pred_low:.3f}, high={pred_high:.3f}"
        )

    def test_multiple_rows_consistent(self, artifact):
        """Repeated predictions for the same row should be identical."""
        row = _make_row()
        p1 = predict_reb_oppmodel(artifact, row)
        p2 = predict_reb_oppmodel(artifact, row)
        assert p1 == p2, "Prediction is not deterministic"


class TestArtifactAttributes:
    def test_artifact_has_correct_fields(self):
        rows = _make_training_set(n=200)
        artifact = train_reb_oppmodel(rows)
        assert hasattr(artifact, "min_model")
        assert hasattr(artifact, "rate_model")
        assert hasattr(artifact, "rate_scaler")
        assert artifact.min_features == _MIN_HEAD_FEATURES
        assert artifact.rate_features == _RATE_HEAD_FEATURES

    def test_too_few_rows_raises(self):
        with pytest.raises((ValueError, Exception)):
            train_reb_oppmodel([])
