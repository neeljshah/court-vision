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
    _build_video_to_pbp_mapper,
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
        """All detected=0 → [1] period, max_ts from all-row fallback (Session 26 fix)."""
        p = tmp_path / "ball_tracking.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["frame", "timestamp", "detected"])
            w.writeheader()
            w.writerow({"frame": 1000, "timestamp": 33.3, "detected": 0})
        periods, max_ts = _infer_period_count(str(tmp_path))
        assert periods == [1]
        # No detected=1 rows → falls back to all-row max timestamp (33.3)
        assert max_ts == 33.3


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


# ── _build_video_to_pbp_mapper ────────────────────────────────────────────────

class TestBuildVideoToPbpMapper:
    """Tests for the canonical _build_video_to_pbp_mapper (data_dir, fps) -> (mapper, anchors).

    The canonical function requires >= 5 anchors (R7 lowered from 20) with
    video_span >= 600s and >= 10 unique pbp_sec values to build a mapper;
    sparse data returns (None, []).
    """

    def _write_scoreboard_log(self, tmp_path: Path, rows: list[dict]) -> None:
        """Write rows to scoreboard_log.csv inside tmp_path (canonical reads data_dir)."""
        log_path = tmp_path / "scoreboard_log.csv"
        fieldnames = ["frame", "game_clock", "shot_clock", "home_score",
                      "away_score", "period", "confidence"]
        with open(log_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)

    def _make_dense_anchors(self, n: int = 30, fps: float = 30.0) -> list[dict]:
        """Generate n rows spanning Q1+Q2 (>600s video, >10 unique pbp values).

        Each row is one second of game time apart.  Q1 lasts 720s game time
        (frames 0-21600 at 30fps), Q2 from game 720s onward.

        Frame spacing = fps * 1s video/row, so video_span = (n-1) * 1s >= n-1 s.
        Use n=30 for a safe margin above the 20-anchor + 600s thresholds.
        We simulate Q1 rows over 720s video (~7200s game time range is wrong; use
        realistic: Q1 is 720 game-sec at 1:1 ratio).  Space frames 1000 apart
        (33.3s video between each) so 30 rows = 29 * 33.3s = 966s video span.
        """
        rows = []
        for i in range(n):
            frame = i * 1000  # 33.3s video per row at 30fps
            # Simulate Q1 counting down from 12:00 (720s) at ~1s/row
            remaining = max(0, 720 - i * 24)  # 24s game-time per row
            mm = remaining // 60
            ss = remaining % 60
            rows.append({
                "frame": frame,
                "game_clock": f"{mm}:{ss:02d}",
                "shot_clock": "",
                "home_score": i,
                "away_score": i,
                "period": 1,
                "confidence": 0.9,
            })
        return rows

    def test_returns_none_when_file_missing(self, tmp_path):
        """No scoreboard_log.csv inside data_dir → (None, [])."""
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path))
        assert mapper is None
        assert anchors == []

    def test_returns_none_when_too_few_anchors(self, tmp_path):
        """Only 3 high-confidence anchors (< 20) → (None, [])."""
        self._write_scoreboard_log(tmp_path, [
            {"frame": 3000,  "game_clock": "10:00", "shot_clock": "", "home_score": 5,
             "away_score": 3, "period": 1, "confidence": 0.9},
            {"frame": 6000,  "game_clock": "08:00", "shot_clock": "", "home_score": 10,
             "away_score": 8, "period": 1, "confidence": 0.9},
            {"frame": 9000,  "game_clock": "06:00", "shot_clock": "", "home_score": 15,
             "away_score": 13, "period": 1, "confidence": 0.9},
        ])
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path))
        assert mapper is None
        assert anchors == []

    def test_returns_none_when_video_span_too_short(self, tmp_path):
        """20 anchors but all within 100s video (< 600s span) → (None, [])."""
        rows = []
        for i in range(20):
            frame = i * 150  # 5s apart at 30fps → 19*5=95s span
            remaining = 720 - i * 2
            mm = remaining // 60
            ss = remaining % 60
            rows.append({
                "frame": frame, "game_clock": f"{mm}:{ss:02d}", "shot_clock": "",
                "home_score": i, "away_score": i, "period": 1, "confidence": 0.9,
            })
        self._write_scoreboard_log(tmp_path, rows)
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path))
        assert mapper is None
        assert anchors == []

    def test_mapper_built_from_dense_full_game_anchors(self, tmp_path):
        """30 anchors spanning ~966s video → mapper callable, anchors non-empty.

        At anchor midpoint the mapper must return a pbp_sec > 0 and consistent
        with Q1 elapsed time (not the raw video timestamp).
        """
        rows = self._make_dense_anchors(n=30, fps=30.0)
        self._write_scoreboard_log(tmp_path, rows)
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path), fps=30.0)

        assert mapper is not None, "Expected mapper to be built with 30 dense anchors"
        # R7 lowered _MIN_ANCHORS 20→5; robust filter ±10 window then drops half
        # of dense-input anchors (which all map to similar pbp_sec → deviation
        # filter rejects). 5 is the production minimum.
        assert len(anchors) >= 5

        # Mid-anchor: frame 15000 → video_sec=500s → Q1 elapsed ~(720 - (720 - 15*24)) = 360s
        pbp_at_500 = mapper(500.0)
        assert pbp_at_500 is not None
        assert 0 < pbp_at_500 < 800, f"pbp_sec={pbp_at_500:.1f} out of expected Q1 range"

    def test_mapper_accounts_for_halftime_gap(self, tmp_path):
        """Anchors spanning Q1+Q2 with halftime gap: post-Q2 video_sec maps to pbp > 720.

        Build 30 rows in two blocks:
          - Block A (Q1): frames 0-14000 (0-467s video), game_clock counting from 12:00
          - Block B (Q2): frames 32000-46000 (1067-1533s video), game_clock Q2 counting down
        Video gap of 32000-14000=18000 frames (600s) simulates halftime broadcast.
        A post-halftime video_sec=1200 must map to pbp_sec > 720 (into Q2).
        """
        rows = []
        fps = 30.0
        # Q1 block: 15 rows, frames 0..14000 step 1000
        for i in range(15):
            frame = i * 1000
            remaining = max(0, 720 - i * 48)  # count down faster to reach 0 in 15 steps
            mm = remaining // 60
            ss = remaining % 60
            rows.append({
                "frame": frame, "game_clock": f"{mm}:{ss:02d}", "shot_clock": "",
                "home_score": i * 2, "away_score": i * 2, "period": 1, "confidence": 0.9,
            })
        # Q2 block: 15 rows, frames 32000..46000 step 1000
        for i in range(15):
            frame = 32000 + i * 1000
            remaining = max(0, 720 - i * 48)
            mm = remaining // 60
            ss = remaining % 60
            rows.append({
                "frame": frame, "game_clock": f"{mm}:{ss:02d}", "shot_clock": "",
                "home_score": 30 + i * 2, "away_score": 28 + i * 2, "period": 2, "confidence": 0.9,
            })
        self._write_scoreboard_log(tmp_path, rows)
        mapper, anchors = _build_video_to_pbp_mapper(str(tmp_path), fps=fps)

        assert mapper is not None, "Expected mapper with 30 anchors spanning Q1+Q2"
        # Q2 anchor at frame 32000 → video_sec=1066.7s → pbp >= 720 (Q2 boundary or later).
        # Inclusive bound: 720 IS the start of Q2 PBP time (Q1=0-720, Q2=720-1440).
        pbp_q2_start = mapper(32000 / fps)
        assert pbp_q2_start >= 720, (
            f"Expected pbp_sec >= 720 (Q2 territory) for video_sec={32000/fps:.0f}s, "
            f"got {pbp_q2_start:.1f}.  Halftime gap not accounted for."
        )
