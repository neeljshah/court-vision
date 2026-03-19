"""
Tests for src/analytics/shot_quality.py — Shot Quality Scoring.

Covers:
- score_shot() for all zones
- edge cases: zero spacing, empty DataFrame, referee row filtering
- all-NaN columns coerced to 0
- single shot row
- parametrized zone/isolation/spacing combinations
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analytics.shot_quality import score_shot, run, _write_heatmap


# ── score_shot() ──────────────────────────────────────────────────────────────

class TestScoreShotZones:

    def test_paint_zone_higher_than_midrange(self):
        """paint zone should score higher than mid_range (same isolation/spacing)."""
        paint = score_shot("paint", handler_isolation=100, team_spacing=40000, possession_run=50)
        mid   = score_shot("mid_range", handler_isolation=100, team_spacing=40000, possession_run=50)
        assert paint > mid

    def test_corner_3_higher_than_3pt_arc(self):
        """corner_3 should score higher than 3pt_arc."""
        c3 = score_shot("corner_3", handler_isolation=100, team_spacing=40000, possession_run=50)
        arc = score_shot("3pt_arc", handler_isolation=100, team_spacing=40000, possession_run=50)
        assert c3 > arc

    def test_backcourt_is_lowest_zone(self):
        """backcourt should score lower than all other named zones."""
        bc  = score_shot("backcourt", handler_isolation=100, team_spacing=40000, possession_run=50)
        mid = score_shot("mid_range", handler_isolation=100, team_spacing=40000, possession_run=50)
        assert bc < mid

    def test_unknown_zone_uses_fallback_prior(self):
        """Unknown zone key gets fallback prior 0.3, still returns a valid float."""
        score = score_shot("halfcourt_heave", handler_isolation=100, team_spacing=40000, possession_run=0)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("zone", ["paint", "corner_3", "3pt_arc", "mid_range", "backcourt"])
    def test_score_in_unit_interval(self, zone):
        """All zone scores are in [0, 1]."""
        score = score_shot(zone, handler_isolation=80, team_spacing=30000, possession_run=30)
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("zone", ["paint", "corner_3", "3pt_arc", "mid_range", "backcourt"])
    def test_score_is_float(self, zone):
        """score_shot always returns a float."""
        assert isinstance(score_shot(zone, 80, 30000, 30), float)


class TestScoreShotIsolation:

    def test_wide_open_higher_than_contested(self):
        """Wide open (high isolation distance) should score higher than contested."""
        open_shot = score_shot("3pt_arc", handler_isolation=160, team_spacing=40000, possession_run=50)
        contested = score_shot("3pt_arc", handler_isolation=10, team_spacing=40000, possession_run=50)
        assert open_shot > contested

    def test_zero_isolation_is_valid(self):
        """Zero isolation (fully contested) should return a valid score in [0, 1]."""
        score = score_shot("paint", handler_isolation=0, team_spacing=40000, possession_run=50)
        assert 0.0 <= score <= 1.0

    def test_none_isolation_treated_as_zero(self):
        """None handler_isolation coerced to 0 — should not raise."""
        score = score_shot("paint", handler_isolation=None, team_spacing=40000, possession_run=50)
        assert 0.0 <= score <= 1.0

    def test_very_large_isolation_capped_at_max(self):
        """Isolation >> _OPEN_DIST should still produce score <= 1.0."""
        score = score_shot("paint", handler_isolation=9999, team_spacing=40000, possession_run=50)
        assert score <= 1.0


class TestScoreShotSpacing:

    def test_zero_spacing_is_valid(self):
        """Zero team_spacing should return a valid score (not NaN or error)."""
        score = score_shot("paint", handler_isolation=100, team_spacing=0, possession_run=50)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_none_spacing_treated_as_zero(self):
        """None team_spacing coerced to 0 — should not raise."""
        score = score_shot("paint", handler_isolation=100, team_spacing=None, possession_run=50)
        assert 0.0 <= score <= 1.0

    def test_higher_spacing_scores_higher(self):
        """Better team spacing → higher shot quality."""
        good = score_shot("3pt_arc", handler_isolation=100, team_spacing=80000, possession_run=50)
        poor = score_shot("3pt_arc", handler_isolation=100, team_spacing=5000, possession_run=50)
        assert good > poor


class TestScoreShotPossessionRun:

    def test_fresh_possession_scores_higher(self):
        """Early in possession → defense less set → higher quality than deep possession."""
        fresh = score_shot("paint", handler_isolation=100, team_spacing=40000, possession_run=0)
        deep  = score_shot("paint", handler_isolation=100, team_spacing=40000, possession_run=150)
        assert fresh > deep

    def test_zero_possession_run_is_valid(self):
        """Zero possession_run should not raise."""
        score = score_shot("paint", handler_isolation=100, team_spacing=40000, possession_run=0)
        assert 0.0 <= score <= 1.0


# ── run() with DataFrame inputs ───────────────────────────────────────────────

def _make_features_csv(tmp_path, rows: list[dict]) -> str:
    """Write a minimal features.csv to tmp_path and return path."""
    df = pd.DataFrame(rows)
    path = str(tmp_path / "features.csv")
    df.to_csv(path, index=False)
    return path


class TestRunEmptyAndEdge:

    def test_empty_dataframe_returns_empty(self, tmp_path):
        """run() on a CSV with no shot events returns empty DataFrame."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 1, "team": "A", "event": "dribble",
             "handler_isolation": 100, "team_spacing": 40000, "possession_run": 10,
             "court_zone": "paint"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert result.empty

    def test_no_event_column_returns_empty(self, tmp_path):
        """run() on a CSV missing 'event' column returns empty DataFrame."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 1, "team": "A", "handler_isolation": 100,
             "team_spacing": 40000, "possession_run": 10, "court_zone": "paint"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert result.empty

    def test_referee_rows_filtered_out(self, tmp_path):
        """Shots by team='referee' are excluded from output."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 1, "team": "referee", "event": "shot",
             "handler_isolation": 100, "team_spacing": 40000, "possession_run": 10,
             "court_zone": "paint"},
            {"frame": 2, "team": "A", "event": "shot",
             "handler_isolation": 80, "team_spacing": 30000, "possession_run": 20,
             "court_zone": "3pt_arc"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert len(result) == 1
        assert "A" in result["team"].values

    def test_single_shot_row_produces_one_result(self, tmp_path):
        """Single valid shot row → one row in output."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 5, "team": "B", "event": "shot",
             "handler_isolation": 120, "team_spacing": 60000, "possession_run": 30,
             "court_zone": "corner_3"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert len(result) == 1
        assert "shot_quality" in result.columns

    def test_shot_quality_column_in_unit_interval(self, tmp_path):
        """All shot_quality values in output are in [0, 1]."""
        rows = [
            {"frame": i, "team": "A", "event": "shot",
             "handler_isolation": float(i * 10), "team_spacing": float(i * 5000),
             "possession_run": i, "court_zone": zone}
            for i, zone in enumerate(["paint", "corner_3", "3pt_arc", "mid_range", "backcourt"])
        ]
        csv = _make_features_csv(tmp_path, rows)
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert all(0.0 <= v <= 1.0 for v in result["shot_quality"])

    def test_all_nan_isolation_coerced(self, tmp_path):
        """NaN in handler_isolation coerced to 0 — run() should not raise."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 1, "team": "A", "event": "shot",
             "handler_isolation": float("nan"), "team_spacing": 40000.0,
             "possession_run": 10, "court_zone": "paint"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert len(result) == 1
        assert not result["shot_quality"].isna().any()

    def test_all_nan_spacing_coerced(self, tmp_path):
        """NaN in team_spacing coerced to 0 — run() should not raise."""
        csv = _make_features_csv(tmp_path, [
            {"frame": 1, "team": "A", "event": "shot",
             "handler_isolation": 100.0, "team_spacing": float("nan"),
             "possession_run": 10, "court_zone": "paint"},
        ])
        result = run(input_path=csv, output_dir=str(tmp_path))
        assert len(result) == 1
        assert not result["shot_quality"].isna().any()


# ── _write_heatmap() ──────────────────────────────────────────────────────────

class TestWriteHeatmap:

    def test_heatmap_json_written(self, tmp_path):
        """_write_heatmap writes shot_heatmap.json."""
        shots = pd.DataFrame([
            {"court_zone": "paint", "team": "A", "shot_quality": 0.8},
            {"court_zone": "paint", "team": "B", "shot_quality": 0.6},
            {"court_zone": "3pt_arc", "team": "A", "shot_quality": 0.5},
        ])
        _write_heatmap(shots, str(tmp_path))
        path = str(tmp_path / "shot_heatmap.json")
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "paint" in data
        assert "3pt_arc" in data

    def test_heatmap_count_and_avg_quality(self, tmp_path):
        """paint zone has count=2 and correct avg_quality."""
        shots = pd.DataFrame([
            {"court_zone": "paint", "team": "A", "shot_quality": 0.8},
            {"court_zone": "paint", "team": "A", "shot_quality": 0.6},
        ])
        _write_heatmap(shots, str(tmp_path))
        with open(str(tmp_path / "shot_heatmap.json")) as f:
            data = json.load(f)
        assert data["paint"]["count"] == 2
        assert abs(data["paint"]["avg_quality"] - 0.7) < 1e-3

    def test_heatmap_referee_team_excluded_from_per_team(self, tmp_path):
        """referee team should not appear in per_team breakdown."""
        shots = pd.DataFrame([
            {"court_zone": "paint", "team": "A", "shot_quality": 0.8},
            {"court_zone": "paint", "team": "referee", "shot_quality": 0.5},
        ])
        _write_heatmap(shots, str(tmp_path))
        with open(str(tmp_path / "shot_heatmap.json")) as f:
            data = json.load(f)
        per_team = data["paint"]["per_team"]
        assert "referee" not in per_team

    def test_heatmap_no_court_zone_column_is_noop(self, tmp_path):
        """If court_zone column missing, _write_heatmap returns without writing."""
        shots = pd.DataFrame([{"team": "A", "shot_quality": 0.8}])
        _write_heatmap(shots, str(tmp_path))
        path = str(tmp_path / "shot_heatmap.json")
        assert not os.path.exists(path)


# ── Parametrized edge cases ────────────────────────────────────────────────────

@pytest.mark.parametrize("isolation,spacing,possession", [
    (0, 0, 0),
    (0, 0, 150),
    (999, 999999, 0),
    (999, 0, 150),
    (None, None, 0),
])
def test_score_shot_parametrized_edge_cases(isolation, spacing, possession):
    """score_shot should never raise or produce out-of-range values for edge inputs."""
    score = score_shot("paint", isolation, spacing, possession)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0
