"""
tests/test_drift_detector.py — Unit tests for the feature drift detector.

Tests:
1. Drift detected (3σ shift on one feature) → feature flagged + alert fired.
2. No drift (batch matches baseline) → no flags, no alert.
3. Missing baseline file → returns empty list gracefully (no exception).
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pandas as pd
import pytest

from src.prediction.drift_detector import DriftDetector, DRIFT_SIGMA_THRESHOLD


# ── helpers ───────────────────────────────────────────────────────────────────

def _write_baseline(path: str, baseline: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(baseline, f)


# ── tests ─────────────────────────────────────────────────────────────────────

class TestDriftDetected:
    """3σ shift on feature_a → flagged + alert fired."""

    def test_flagged_feature_returned(self, tmp_path):
        """The drifted feature name is in the returned list."""
        baseline_path = str(tmp_path / "output" / "feature_baseline.json")
        baseline = {
            "feature_a": {"mean": 10.0, "std": 1.0},
            "feature_b": {"mean": 5.0,  "std": 0.5},
        }
        _write_baseline(baseline_path, baseline)

        detector = DriftDetector(baseline_path=baseline_path)

        # feature_a shifted +3σ (mean = 10 + 3*1 = 13), feature_b unchanged
        batch = pd.DataFrame({
            "feature_a": [13.0] * 20,
            "feature_b": [5.0]  * 20,
        })

        flagged = detector.check(batch, send_telegram=False)

        assert "feature_a" in flagged, f"Expected 'feature_a' flagged, got {flagged}"
        assert "feature_b" not in flagged

    def test_alert_fires_on_drift(self, tmp_path):
        """fire_alert is called exactly once for a single drifted feature."""
        baseline_path = str(tmp_path / "output" / "feature_baseline.json")
        baseline = {
            "pts": {"mean": 20.0, "std": 2.0},
        }
        _write_baseline(baseline_path, baseline)

        detector = DriftDetector(baseline_path=baseline_path)

        # 4σ shift
        batch = pd.DataFrame({"pts": [28.0] * 30})

        with patch("src.prediction.drift_detector.fire_alert") as mock_fire:
            flagged = detector.check(batch, send_telegram=False)

        assert "pts" in flagged
        assert mock_fire.call_count == 1
        breach_arg = mock_fire.call_args[0][0]
        assert breach_arg.slo_name == "feature_drift"
        assert breach_arg.measured > DRIFT_SIGMA_THRESHOLD

    def test_multiple_drifted_features_all_flagged(self, tmp_path):
        """All features exceeding 2σ are returned and an alert fires for each."""
        baseline_path = str(tmp_path / "output" / "feature_baseline.json")
        baseline = {
            "a": {"mean": 0.0, "std": 1.0},
            "b": {"mean": 0.0, "std": 1.0},
            "c": {"mean": 0.0, "std": 1.0},
        }
        _write_baseline(baseline_path, baseline)

        detector = DriftDetector(baseline_path=baseline_path)
        # a and b drift by 3σ, c stays near baseline
        batch = pd.DataFrame({
            "a": [3.0]  * 10,
            "b": [-3.0] * 10,
            "c": [0.1]  * 10,
        })

        with patch("src.prediction.drift_detector.fire_alert") as mock_fire:
            flagged = detector.check(batch, send_telegram=False)

        assert set(flagged) == {"a", "b"}
        assert mock_fire.call_count == 2


class TestNoDrift:
    """Batch that matches baseline → nothing flagged, no alert."""

    def test_no_flags_when_within_threshold(self, tmp_path):
        """Batch mean within 2σ → empty flagged list."""
        baseline_path = str(tmp_path / "output" / "feature_baseline.json")
        baseline = {
            "feature_x": {"mean": 50.0, "std": 5.0},
            "feature_y": {"mean": 10.0, "std": 1.0},
        }
        _write_baseline(baseline_path, baseline)

        detector = DriftDetector(baseline_path=baseline_path)

        # Both features within ±1σ
        batch = pd.DataFrame({
            "feature_x": [51.0] * 50,
            "feature_y": [10.3] * 50,
        })

        with patch("src.prediction.drift_detector.fire_alert") as mock_fire:
            flagged = detector.check(batch, send_telegram=False)

        assert flagged == []
        mock_fire.assert_not_called()

    def test_exactly_at_threshold_not_flagged(self, tmp_path):
        """Mean exactly at 2σ boundary is NOT flagged (strict > comparison)."""
        baseline_path = str(tmp_path / "output" / "feature_baseline.json")
        baseline = {"feat": {"mean": 0.0, "std": 1.0}}
        _write_baseline(baseline_path, baseline)

        detector = DriftDetector(baseline_path=baseline_path)
        # z-score == exactly 2.0 → should NOT be flagged
        batch = pd.DataFrame({"feat": [2.0] * 100})

        with patch("src.prediction.drift_detector.fire_alert") as mock_fire:
            flagged = detector.check(batch, send_telegram=False)

        assert flagged == []
        mock_fire.assert_not_called()


class TestMissingBaseline:
    """Absent baseline file → graceful no-op."""

    def test_absent_file_returns_empty_list(self, tmp_path):
        """Non-existent baseline → check() returns [] without raising."""
        missing_path = str(tmp_path / "does_not_exist.json")
        detector = DriftDetector(baseline_path=missing_path)

        batch = pd.DataFrame({"feature_a": [1.0, 2.0, 3.0]})

        with patch("src.prediction.drift_detector.fire_alert") as mock_fire:
            flagged = detector.check(batch, send_telegram=False)

        assert flagged == []
        mock_fire.assert_not_called()

    def test_malformed_baseline_returns_empty_list(self, tmp_path):
        """Malformed JSON baseline → check() returns [] without raising."""
        bad_path = str(tmp_path / "bad_baseline.json")
        with open(bad_path, "w") as f:
            f.write("NOT_VALID_JSON{{{{")

        detector = DriftDetector(baseline_path=bad_path)
        batch = pd.DataFrame({"feature_a": [999.0] * 10})

        flagged = detector.check(batch, send_telegram=False)
        assert flagged == []
