"""
test_run_phase_g.py — Unit tests for run_phase_g.py helpers.

Tests:
  - _is_complete (True / False: missing file / empty file)
  - _recompute_ball_valid (with and without live column)
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.run_phase_g import _is_complete, _recompute_ball_valid, _quality_label


# ── _is_complete ──────────────────────────────────────────────────────────────

class TestIsComplete:

    def _write_csv(self, path: Path, header: list[str], rows: list[list]) -> None:
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    def test_is_complete_true(self, tmp_path):
        """All three required CSVs with at least one data row → True."""
        self._write_csv(tmp_path / "ball_tracking.csv",
                        ["frame", "detected"], [[1, 1]])
        self._write_csv(tmp_path / "tracking_data.csv",
                        ["frame", "player_id"], [[1, 99]])
        self._write_csv(tmp_path / "possessions.csv",
                        ["possession_id", "team"], [[1, "green"]])
        assert _is_complete(tmp_path) is True

    def test_is_complete_false_missing_file(self, tmp_path):
        """Missing possessions.csv → False."""
        self._write_csv(tmp_path / "ball_tracking.csv",
                        ["frame", "detected"], [[1, 1]])
        self._write_csv(tmp_path / "tracking_data.csv",
                        ["frame", "player_id"], [[1, 99]])
        # possessions.csv intentionally absent
        assert _is_complete(tmp_path) is False

    def test_is_complete_false_empty_file(self, tmp_path):
        """possessions.csv with only a header row (0 data rows) → False."""
        self._write_csv(tmp_path / "ball_tracking.csv",
                        ["frame", "detected"], [[1, 1]])
        self._write_csv(tmp_path / "tracking_data.csv",
                        ["frame", "player_id"], [[1, 99]])
        self._write_csv(tmp_path / "possessions.csv",
                        ["possession_id", "team"], [])  # header only
        assert _is_complete(tmp_path) is False

    def test_is_complete_false_all_missing(self, tmp_path):
        """Empty directory → False."""
        assert _is_complete(tmp_path) is False


# ── _recompute_ball_valid ─────────────────────────────────────────────────────

class TestRecomputeBallValid:

    def _write_ball_csv(self, path: Path, rows: list[dict]) -> None:
        if not rows:
            return
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def test_with_live_column_uses_live_denominator(self, tmp_path):
        """CSV with live column: detected.sum() / live.sum()."""
        ball_csv = tmp_path / "ball_tracking.csv"
        # 4 live frames (live=1): 3 detected; 2 non-live (live=0)
        rows = [
            {"frame": i, "timestamp": i * 0.1, "detected": d, "live": lv}
            for i, (d, lv) in enumerate([
                (1, 1), (1, 1), (1, 1), (0, 1),  # 3/4 live detected
                (0, 0), (0, 0),                   # non-live, excluded
            ])
        ]
        self._write_ball_csv(ball_csv, rows)
        result = _recompute_ball_valid(ball_csv)
        assert result == 75.0  # 3 / 4 * 100

    def test_with_live_column_all_live(self, tmp_path):
        """All rows live, all detected → 100%."""
        ball_csv = tmp_path / "ball_tracking.csv"
        rows = [{"frame": i, "detected": 1, "live": 1} for i in range(10)]
        self._write_ball_csv(ball_csv, rows)
        assert _recompute_ball_valid(ball_csv) == 100.0

    def test_streak_heuristic_excludes_long_zero_stretches(self, tmp_path):
        """Without live column: 100-frame zero-detection stretch excluded from denominator."""
        ball_csv = tmp_path / "ball_tracking.csv"
        # 10 detected frames, then 100 consecutive zeros (non-live by heuristic),
        # then 10 more detected frames.
        rows = []
        for i in range(10):
            rows.append({"frame": i, "detected": 1})
        for i in range(100):
            rows.append({"frame": 10 + i, "detected": 0})
        for i in range(10):
            rows.append({"frame": 110 + i, "detected": 1})
        self._write_ball_csv(ball_csv, rows)

        result = _recompute_ball_valid(ball_csv)
        # Heuristic should mark the 100-frame zero-stretch as non-live.
        # Live frames = 10 + 10 = 20; detected = 20 → 100%
        assert result == 100.0

    def test_streak_heuristic_short_gap_included(self, tmp_path):
        """Without live column: a gap shorter than 90 frames stays in denominator."""
        ball_csv = tmp_path / "ball_tracking.csv"
        # 10 detected, 50 zero (< 90 threshold, stays live), 10 detected
        rows = []
        for i in range(10):
            rows.append({"frame": i, "detected": 1})
        for i in range(50):
            rows.append({"frame": 10 + i, "detected": 0})
        for i in range(10):
            rows.append({"frame": 60 + i, "detected": 1})
        self._write_ball_csv(ball_csv, rows)

        result = _recompute_ball_valid(ball_csv)
        # All 70 frames count as live; 20 detected → ~28.6%
        assert abs(result - round(20 / 70 * 100, 1)) < 0.1

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Missing ball_tracking.csv → None."""
        assert _recompute_ball_valid(tmp_path / "ball_tracking.csv") is None


# ── _quality_label (Fix 5) ────────────────────────────────────────────────────

class TestQualityLabel:

    def test_high_at_80_pct(self):
        """80% or above → high."""
        assert _quality_label(80.0) == "high"
        assert _quality_label(97.3) == "high"

    def test_medium_at_65_to_79(self):
        """65–79.9% → medium."""
        assert _quality_label(65.0) == "medium"
        assert _quality_label(79.9) == "medium"

    def test_low_below_65(self):
        """Below 65% → low, warns about exclusion from training."""
        assert _quality_label(57.7) == "low"
        assert _quality_label(0.0)  == "low"


# ── possession min-duration filter (Fix 3 Part B) ─────────────────────────────

class TestPossessionMinDurationFilter:
    """backfill_possession_filter._keep() must drop rows with duration_sec < 2.0."""

    def test_keep_above_threshold(self):
        from scripts.backfill_possession_filter import _keep
        assert _keep({"duration_sec": "2.0"})  is True
        assert _keep({"duration_sec": "5.5"})  is True
        assert _keep({"duration_sec": "30.0"}) is True

    def test_drop_below_threshold(self):
        from scripts.backfill_possession_filter import _keep
        assert _keep({"duration_sec": "0.1"}) is False
        assert _keep({"duration_sec": "1.9"}) is False
        assert _keep({"duration_sec": "0.0"}) is False

    def test_keep_unparseable_duration(self):
        """Rows with missing/unparseable duration_sec must be kept (safe default)."""
        from scripts.backfill_possession_filter import _keep
        assert _keep({"duration_sec": ""})      is True
        assert _keep({})                         is True


# ── game_id in _summarize_possession output (Fix 1) ───────────────────────────

class TestGameIdInPossessionRow:
    """game_id must flow from UnifiedPipeline._summarize_possession to the CSV row."""

    def test_game_id_present_in_row(self):
        """_summarize_possession includes game_id in the returned dict."""
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.pipeline.unified_pipeline import UnifiedPipeline
        buf = [
            {"frame": 10, "spacing": 5.0, "isolation": 0.2, "vtb": 0.5,
             "drive": 0, "shot_event": False, "fast_break": 0,
             "poss_type": "half_court", "play_type": "isolation"},
        ] * 100  # 100 frames at 30fps = 3.3s → passes 2s filter
        row = UnifiedPipeline._summarize_possession(
            pid=42, team="white", start_f=0, end_f=99,
            buf=buf, fps=30.0, game_id="0022400430",
        )
        assert row.get("game_id") == "0022400430"

    def test_game_id_none_when_not_passed(self):
        """Without game_id, the field is None (not empty string)."""
        from src.pipeline.unified_pipeline import UnifiedPipeline
        buf = [
            {"frame": i, "spacing": 5.0, "isolation": 0.2, "vtb": 0.5,
             "drive": 0, "shot_event": False, "fast_break": 0,
             "poss_type": "half_court", "play_type": "isolation"}
            for i in range(100)
        ]
        row = UnifiedPipeline._summarize_possession(
            pid=1, team="green", start_f=0, end_f=99, buf=buf, fps=30.0,
        )
        assert row.get("game_id") is None
