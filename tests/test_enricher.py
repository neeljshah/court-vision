"""
test_enricher.py — Unit tests for src.data.nba_enricher.

Tests:
  - _infer_clip_start_sec: returns negative offset / None for empty CSV
  - enrich(): auto-calibrates clip_start_sec when 0.0 is passed
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.nba_enricher import (
    _infer_clip_start_sec,
    _infer_period_count,
    _infer_fps,
    enrich_possessions,
)


# ── _infer_clip_start_sec ─────────────────────────────────────────────────────

class TestInferClipStartSec:

    def _write_ball_csv(self, path: Path, rows: list[dict]) -> None:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def test_returns_negative_offset_for_first_detection(self, tmp_path):
        """First detected=1 at timestamp 53.4 → returns -53.4."""
        ball_csv = tmp_path / "ball_tracking.csv"
        rows = [
            {"frame": 0,    "timestamp": 0.0,  "detected": 0},
            {"frame": 3,    "timestamp": 0.1,  "detected": 0},
            {"frame": 1602, "timestamp": 53.4, "detected": 1},
            {"frame": 1605, "timestamp": 53.5, "detected": 1},
        ]
        self._write_ball_csv(ball_csv, rows)
        result = _infer_clip_start_sec(str(tmp_path))
        assert result == -53.4

    def test_returns_earliest_timestamp_when_multiple_detections(self, tmp_path):
        """Returns -min(timestamp) when multiple detections in first 200 rows."""
        ball_csv = tmp_path / "ball_tracking.csv"
        rows = [
            {"frame": 30,  "timestamp": 1.0,  "detected": 1},
            {"frame": 60,  "timestamp": 2.0,  "detected": 1},
            {"frame": 0,   "timestamp": 0.5,  "detected": 1},  # earliest
        ]
        self._write_ball_csv(ball_csv, rows)
        result = _infer_clip_start_sec(str(tmp_path))
        assert result == -0.5

    def test_no_detection_returns_none(self, tmp_path):
        """All detected=0 → returns None (no usable offset)."""
        ball_csv = tmp_path / "ball_tracking.csv"
        rows = [
            {"frame": i * 3, "timestamp": round(i * 0.1, 3), "detected": 0}
            for i in range(50)
        ]
        self._write_ball_csv(ball_csv, rows)
        assert _infer_clip_start_sec(str(tmp_path)) is None

    def test_missing_file_returns_none(self, tmp_path):
        """No ball_tracking.csv → returns None."""
        assert _infer_clip_start_sec(str(tmp_path)) is None

    def test_only_scans_first_200_rows(self, tmp_path):
        """Detections beyond row 200 are ignored → returns None if only late detections."""
        ball_csv = tmp_path / "ball_tracking.csv"
        # 200 zero rows, then a detection at row 201
        rows = [
            {"frame": i * 3, "timestamp": round(i * 0.1, 3), "detected": 0}
            for i in range(200)
        ]
        rows.append({"frame": 603, "timestamp": 20.1, "detected": 1})
        self._write_ball_csv(ball_csv, rows)
        assert _infer_clip_start_sec(str(tmp_path)) is None


# ── enrich() auto-calibration ─────────────────────────────────────────────────

class TestEnrichAutoCalibration:

    def test_enrich_auto_calibrates_when_start_zero(self, tmp_path):
        """enrich() picks up inferred clip_start_sec when 0.0 is passed."""
        from src.data.nba_enricher import enrich

        # Write a minimal ball_tracking.csv with first detection at 10.0s
        ball_csv = tmp_path / "ball_tracking.csv"
        with open(ball_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": 300, "timestamp": 10.0, "detected": 1})

        # Write empty shot_log.csv and possessions.csv so enrich() doesn't crash
        for name in ["shot_log.csv", "possessions.csv"]:
            p = tmp_path / name
            with open(p, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=["game_id"]).writeheader()

        # Mock fetch_playbyplay to return empty events (no network needed)
        with patch("src.data.nba_enricher.fetch_playbyplay", return_value=[]) as mock_pbp:
            enrich(
                game_id        = "TEST_GAME",
                period         = 1,
                clip_start_sec = 0.0,   # triggers auto-calibration
                fps            = 30.0,
                data_dir       = str(tmp_path),
            )

        # The auto-calibration should have been triggered
        # (fetch_playbyplay was called, not short-circuited)
        mock_pbp.assert_called_once()

    def test_enrich_skips_auto_calibrate_when_start_nonzero(self, tmp_path):
        """enrich() does NOT override an explicit clip_start_sec."""
        from src.data.nba_enricher import enrich, _infer_clip_start_sec

        # Write ball_tracking.csv with first detection at 10s
        ball_csv = tmp_path / "ball_tracking.csv"
        with open(ball_csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": 300, "timestamp": 10.0, "detected": 1})

        for name in ["shot_log.csv", "possessions.csv"]:
            with open(tmp_path / name, "w", newline="") as f:
                csv.DictWriter(f, fieldnames=["game_id"]).writeheader()

        captured = []

        def _fake_pbp(game_id, period):
            captured.append((game_id, period))
            return []

        with patch("src.data.nba_enricher.fetch_playbyplay", side_effect=_fake_pbp):
            # Passing clip_start_sec=420.0 — auto-calibration must NOT override it
            enrich(
                game_id        = "TEST_GAME",
                period         = 1,
                clip_start_sec = 420.0,  # explicit value, must be respected
                fps            = 30.0,
                data_dir       = str(tmp_path),
            )

        assert captured  # enrichment ran


# ── _infer_period_count ───────────────────────────────────────────────────────

class TestInferPeriodCount:

    def _write_ball_csv(self, path: Path, max_ts: float) -> None:
        """Write a minimal ball_tracking.csv with one detected row at max_ts."""
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": int(max_ts * 60), "timestamp": max_ts, "detected": 1})

    def test_single_period_below_720(self, tmp_path):
        """max_ts = 600s → periods = [1]."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 600.0)
        periods, max_ts = _infer_period_count(str(tmp_path))
        assert periods == [1]
        assert abs(max_ts - 600.0) < 0.01

    def test_two_periods_at_935s(self, tmp_path):
        """max_ts = 935s (Q2) → periods = [1, 2]."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 935.0)
        periods, _ = _infer_period_count(str(tmp_path))
        assert periods == [1, 2]

    def test_three_periods_at_1964s(self, tmp_path):
        """max_ts = 1964s (Q3) → periods = [1, 2, 3]."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 1964.0)
        periods, _ = _infer_period_count(str(tmp_path))
        assert periods == [1, 2, 3]

    def test_four_periods_at_2200s(self, tmp_path):
        """max_ts = 2200s (Q4) → periods = [1, 2, 3, 4]."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 2200.0)
        periods, _ = _infer_period_count(str(tmp_path))
        assert periods == [1, 2, 3, 4]

    def test_capped_at_four_periods(self, tmp_path):
        """max_ts = 3600s (full OT game) → capped at [1, 2, 3, 4]."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 3600.0)
        periods, _ = _infer_period_count(str(tmp_path))
        assert periods == [1, 2, 3, 4]

    def test_missing_file_returns_single(self, tmp_path):
        """No ball_tracking.csv → default [1], max_ts=0."""
        periods, max_ts = _infer_period_count(str(tmp_path))
        assert periods == [1]
        assert max_ts == 0.0

    def test_no_detections_returns_single(self, tmp_path):
        """All detected=0 → default [1]."""
        p = tmp_path / "ball_tracking.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": 1000, "timestamp": 33.3, "detected": 0})
        periods, max_ts = _infer_period_count(str(tmp_path))
        assert periods == [1]
        assert max_ts == 0.0


# ── _infer_fps ────────────────────────────────────────────────────────────────

class TestInferFps:

    def _write_ball_csv(self, path: Path, frame: int, ts: float) -> None:
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": frame, "timestamp": ts, "detected": 1})

    def test_detects_60fps(self, tmp_path):
        """64035 frames at 1068s → snaps to 59.94 fps."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 64035, 1068.317)
        fps = _infer_fps(str(tmp_path))
        assert fps == 59.94

    def test_detects_30fps(self, tmp_path):
        """18000 frames at 600s → snaps to 30 fps."""
        self._write_ball_csv(tmp_path / "ball_tracking.csv", 18000, 600.0)
        fps = _infer_fps(str(tmp_path))
        assert fps == 30.0

    def test_missing_file_returns_default(self, tmp_path):
        fps = _infer_fps(str(tmp_path), default=30.0)
        assert fps == 30.0


# ── enrich_possessions writes back in-place ───────────────────────────────────

class TestEnrichPossessionsInPlace:

    def test_possessions_written_back_to_original_path(self, tmp_path):
        """enrich_possessions() must update possessions.csv in-place."""
        poss_path = tmp_path / "possessions.csv"
        with open(poss_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["possession_id", "end_frame", "result", "outcome_score"])
            w.writeheader()
            w.writerow({"possession_id": 1, "end_frame": 600, "result": "", "outcome_score": ""})

        # PBP event: made shot at 20s elapsed period 1
        pbp = [{"period": 1, "game_clock_sec": 20, "event_type": 1,
                "event_desc": "2pt shot made", "score_margin": "2"}]

        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        # possessions.csv (in-place) must now have a non-empty result
        rows = list(csv.DictReader(open(poss_path)))
        assert len(rows) == 1
        assert rows[0]["result"] != ""

    def test_enriched_csv_also_written(self, tmp_path):
        """enrich_possessions() must also write possessions_enriched.csv."""
        poss_path = tmp_path / "possessions.csv"
        with open(poss_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["possession_id", "end_frame", "result", "outcome_score"])
            w.writeheader()
            w.writerow({"possession_id": 1, "end_frame": 600, "result": "", "outcome_score": ""})

        pbp = [{"period": 1, "game_clock_sec": 20, "event_type": 5,
                "event_desc": "turnover", "score_margin": ""}]

        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        enriched_path = tmp_path / "possessions_enriched.csv"
        assert enriched_path.exists()
        rows = list(csv.DictReader(open(enriched_path)))
        assert len(rows) == 1

    def test_score_diff_added_to_fieldnames(self, tmp_path):
        """score_diff must appear in possessions.csv after enrichment."""
        poss_path = tmp_path / "possessions.csv"
        with open(poss_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["possession_id", "end_frame", "result", "outcome_score"])
            w.writeheader()
            w.writerow({"possession_id": 1, "end_frame": 600, "result": "", "outcome_score": ""})

        pbp = [{"period": 1, "game_clock_sec": 20, "event_type": 1,
                "event_desc": "shot made", "score_margin": "4"}]

        enrich_possessions(pbp, str(poss_path), clip_start_sec=0.0, fps=30.0)

        rows = list(csv.DictReader(open(poss_path)))
        assert "score_diff" in rows[0]
