"""
Tests for new analytics metric functions added in P2.

Covers:
  defense_pressure.py: help_rotation_latency, coverage_completeness
  shot_quality.py:     shot_clock_pressure_score, fatigue_penalty
  momentum.py:         scoring_run_length, momentum_shift_flag, pressure_trend
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── help_rotation_latency ─────────────────────────────────────────────────────

class TestHelpRotationLatency:

    def test_basic_latency(self):
        """Simple case: 3 drives with 5, 10, 15 frame latencies → mean 10.0."""
        from src.analytics.defense_pressure import help_rotation_latency
        drives = [0, 100, 200]
        arrivals = [5, 110, 215]
        assert help_rotation_latency(drives, arrivals) == 10.0

    def test_empty_lists_return_zero(self):
        """Empty inputs → 0.0."""
        from src.analytics.defense_pressure import help_rotation_latency
        assert help_rotation_latency([], []) == 0.0

    def test_none_arrival_excluded(self):
        """None arrival frames are skipped; average computed from valid pairs only."""
        from src.analytics.defense_pressure import help_rotation_latency
        drives = [0, 100, 200]
        arrivals = [5, None, 210]
        result = help_rotation_latency(drives, arrivals)
        # Valid pairs: (0,5)→5, (200,210)→10 → mean=7.5
        assert abs(result - 7.5) < 1e-6

    def test_negative_arrival_excluded(self):
        """Negative arrival frames (help never came) are skipped."""
        from src.analytics.defense_pressure import help_rotation_latency
        drives = [0, 100]
        arrivals = [10, -1]
        result = help_rotation_latency(drives, arrivals)
        assert result == 10.0

    def test_single_drive(self):
        """Single valid drive/arrival pair."""
        from src.analytics.defense_pressure import help_rotation_latency
        assert help_rotation_latency([50], [60]) == 10.0

    def test_all_none_arrivals_return_zero(self):
        """No valid arrivals → 0.0."""
        from src.analytics.defense_pressure import help_rotation_latency
        assert help_rotation_latency([0, 100], [None, None]) == 0.0

    def test_zero_latency_valid(self):
        """Drive and arrival on same frame → latency 0."""
        from src.analytics.defense_pressure import help_rotation_latency
        assert help_rotation_latency([10], [10]) == 0.0


# ── coverage_completeness ─────────────────────────────────────────────────────

class TestCoverageCompleteness:

    def test_all_drives_fully_covered(self):
        """All drives have >= 3 help defenders → 1.0."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"help_defenders_present": [3, 4, 3, 5]})
        assert coverage_completeness(df) == 1.0

    def test_no_drives_fully_covered(self):
        """No drives have >= 3 help defenders → 0.0."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"help_defenders_present": [0, 1, 2]})
        assert coverage_completeness(df) == 0.0

    def test_half_drives_covered(self):
        """2 of 4 drives fully covered → 0.5."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"help_defenders_present": [3, 1, 4, 2]})
        assert coverage_completeness(df) == 0.5

    def test_empty_dataframe_returns_zero(self):
        """Empty DataFrame → 0.0."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"help_defenders_present": []})
        assert coverage_completeness(df) == 0.0

    def test_missing_column_returns_zero(self):
        """Missing help_col → 0.0."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"something_else": [3, 4]})
        assert coverage_completeness(df) == 0.0

    def test_none_dataframe_returns_zero(self):
        """None input → 0.0."""
        from src.analytics.defense_pressure import coverage_completeness
        assert coverage_completeness(None) == 0.0

    def test_custom_help_spots(self):
        """Custom help_spots=2: drives with >= 2 count."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"help_defenders_present": [2, 1, 3, 0]})
        # 2 of 4 have >= 2
        assert coverage_completeness(df, help_spots=2) == 0.5

    def test_custom_help_col(self):
        """Custom help_col name."""
        from src.analytics.defense_pressure import coverage_completeness
        df = pd.DataFrame({"my_col": [3, 2, 3]})
        assert coverage_completeness(df, help_col="my_col") == pytest.approx(2 / 3)


# ── shot_clock_pressure_score ─────────────────────────────────────────────────

class TestShotClockPressureScore:

    def test_fresh_possession_is_one(self):
        """possession_run=0 → score == 1.0."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert shot_clock_pressure_score(0, 150) == 1.0

    def test_expired_possession_is_zero(self):
        """possession_run >= max → score == 0.0."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert shot_clock_pressure_score(150, 150) == 0.0

    def test_halfway_is_half(self):
        """possession_run == max/2 → score == 0.5."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert shot_clock_pressure_score(75, 150) == 0.5

    def test_exceeds_max_clamped_to_zero(self):
        """possession_run > max → clamped to 0.0."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert shot_clock_pressure_score(999, 150) == 0.0

    def test_result_in_unit_interval(self):
        """Score always in [0, 1]."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        for run in [0, 30, 75, 120, 150, 200]:
            s = shot_clock_pressure_score(run, 150)
            assert 0.0 <= s <= 1.0

    def test_negative_possession_run_clamped(self):
        """Negative possession_run treated as 0."""
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert shot_clock_pressure_score(-10, 150) == 1.0

    def test_returns_float(self):
        from src.analytics.shot_quality import shot_clock_pressure_score
        assert isinstance(shot_clock_pressure_score(50, 150), float)


# ── fatigue_penalty ───────────────────────────────────────────────────────────

class TestFatiguePenalty:

    def test_no_fatigue_score_unchanged(self):
        """velocity_mean_90 >= 0.8 * velocity_mean_150 → no penalty."""
        from src.analytics.shot_quality import fatigue_penalty
        score = fatigue_penalty(velocity_mean_90=8.0, velocity_mean_150=9.0, base_score=0.7)
        assert score == pytest.approx(0.7, abs=1e-4)

    def test_full_fatigue_applies_penalty(self):
        """velocity_mean_90 << velocity_mean_150 → score reduced."""
        from src.analytics.shot_quality import fatigue_penalty
        score = fatigue_penalty(velocity_mean_90=0.0, velocity_mean_150=10.0, base_score=0.8)
        # ratio=0 → penalty_fraction=1.0 → adjusted = 0.8 * (1 - 0.20) = 0.64
        assert score == pytest.approx(0.64, abs=1e-3)

    def test_result_in_unit_interval(self):
        """Adjusted score is in [0, 1]."""
        from src.analytics.shot_quality import fatigue_penalty
        for v90, v150, base in [(0, 10, 0.9), (5, 10, 0.5), (10, 10, 0.8)]:
            s = fatigue_penalty(v90, v150, base)
            assert 0.0 <= s <= 1.0

    def test_zero_velocity_150_no_penalty(self):
        """velocity_mean_150 == 0 → no division error, returns base_score."""
        from src.analytics.shot_quality import fatigue_penalty
        score = fatigue_penalty(velocity_mean_90=0.0, velocity_mean_150=0.0, base_score=0.6)
        assert score == pytest.approx(0.6, abs=1e-4)

    def test_returns_float(self):
        from src.analytics.shot_quality import fatigue_penalty
        assert isinstance(fatigue_penalty(8.0, 10.0, 0.7), float)

    def test_boundary_exactly_at_threshold_no_penalty(self):
        """velocity_mean_90 == 0.8 * velocity_mean_150 → no penalty (boundary)."""
        from src.analytics.shot_quality import fatigue_penalty
        score = fatigue_penalty(velocity_mean_90=8.0, velocity_mean_150=10.0, base_score=0.7)
        assert score == pytest.approx(0.7, abs=1e-4)


# ── scoring_run_length ────────────────────────────────────────────────────────

class TestScoringRunLength:

    def test_three_same_team_at_end(self):
        """A,A,B,A,A,A → trailing run of 3 (A)."""
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length(["A", "A", "B", "A", "A", "A"]) == 3

    def test_empty_list_returns_zero(self):
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length([]) == 0

    def test_alternating_teams(self):
        """Alternating → run length 1."""
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length(["A", "B", "A", "B", "A"]) == 1

    def test_all_same_team(self):
        """All A → run length == len."""
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length(["A"] * 5) == 5

    def test_single_element(self):
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length(["B"]) == 1

    def test_run_breaks_at_different_team(self):
        """B,B,A → run is 1 (A)."""
        from src.analytics.momentum import scoring_run_length
        assert scoring_run_length(["B", "B", "A"]) == 1


# ── momentum_shift_flag ───────────────────────────────────────────────────────

class TestMomentumShiftFlag:

    def test_large_swing_returns_one(self):
        """A scores 10 pts, B scores 0 → swing >= 5 → flag 1."""
        from src.analytics.momentum import momentum_shift_flag
        scores_a = [2, 3, 2, 3, 0, 0, 0, 0, 0, 0]
        scores_b = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        assert momentum_shift_flag(scores_a, scores_b) == 1

    def test_small_swing_returns_zero(self):
        """Equal scoring → no swing → flag 0."""
        from src.analytics.momentum import momentum_shift_flag
        scores_a = [2, 0, 2, 0, 2]
        scores_b = [2, 0, 2, 0, 2]
        assert momentum_shift_flag(scores_a, scores_b) == 0

    def test_empty_lists_return_zero(self):
        from src.analytics.momentum import momentum_shift_flag
        assert momentum_shift_flag([], []) == 0

    def test_exact_threshold_is_flagged(self):
        """Swing exactly at threshold triggers flag."""
        from src.analytics.momentum import momentum_shift_flag
        # A scores 5, B scores 0 → swing = 5 → flag 1
        scores_a = [5] + [0] * 9
        scores_b = [0] * 10
        assert momentum_shift_flag(scores_a, scores_b, swing_threshold=5) == 1

    def test_below_threshold_not_flagged(self):
        """Swing of 4 with threshold 5 → no flag."""
        from src.analytics.momentum import momentum_shift_flag
        scores_a = [4] + [0] * 9
        scores_b = [0] * 10
        assert momentum_shift_flag(scores_a, scores_b, swing_threshold=5) == 0

    def test_window_respected(self):
        """Only last `window` possessions examined."""
        from src.analytics.momentum import momentum_shift_flag
        # Long history of A dominance, but last 5 possessions are equal
        old_a = [10, 10, 10]
        old_b = [0, 0, 0]
        recent_a = [2, 0, 2, 0, 2]
        recent_b = [2, 0, 2, 0, 2]
        result = momentum_shift_flag(old_a + recent_a, old_b + recent_b, window=5)
        assert result == 0


# ── pressure_trend ────────────────────────────────────────────────────────────

class TestPressureTrend:

    def test_rising_trend_positive_slope(self):
        """Steadily increasing pressure → positive slope."""
        from src.analytics.momentum import pressure_trend
        values = [0.1 * i for i in range(10)]
        slope = pressure_trend(values, window=10)
        assert slope > 0

    def test_falling_trend_negative_slope(self):
        """Steadily decreasing pressure → negative slope."""
        from src.analytics.momentum import pressure_trend
        values = [1.0 - 0.1 * i for i in range(10)]
        slope = pressure_trend(values, window=10)
        assert slope < 0

    def test_flat_trend_near_zero(self):
        """Constant pressure → slope near 0."""
        from src.analytics.momentum import pressure_trend
        values = [0.5] * 20
        slope = pressure_trend(values, window=20)
        assert abs(slope) < 1e-6

    def test_empty_list_returns_zero(self):
        from src.analytics.momentum import pressure_trend
        assert pressure_trend([]) == 0.0

    def test_single_value_returns_zero(self):
        from src.analytics.momentum import pressure_trend
        assert pressure_trend([0.5]) == 0.0

    def test_window_limits_lookback(self):
        """Only last `window` frames used — different windows give different slopes."""
        from src.analytics.momentum import pressure_trend
        values = [0.1] * 20 + [0.9 - 0.05 * i for i in range(10)]
        slope_long = pressure_trend(values, window=30)
        slope_short = pressure_trend(values, window=10)
        # Short window should see falling trend; long window sees mixed signal
        assert slope_short < 0

    def test_returns_float(self):
        from src.analytics.momentum import pressure_trend
        assert isinstance(pressure_trend([0.1, 0.5, 0.9]), float)
