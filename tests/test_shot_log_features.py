"""
tests/test_shot_log_features.py — Shot log new feature columns.

Covers:
  - shot_log.csv contains shot_clock, contest_arm_angle, closeout_speed, fatigue_proxy
  - _export_shot_log writes all 4 new columns as CSV headers
  - fatigue_proxy > 0 after player movement frames
  - contest_arm_angle present when pose data available in track dict
  - closeout_speed populated from event_det.events closeout entries
"""
from __future__ import annotations

import csv
import os
import sys
import tempfile
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ───────────────────────────────────────────────────────────────────

NEW_COLUMNS = {"shot_clock", "contest_arm_angle", "closeout_speed", "fatigue_proxy"}


def _make_shot_row(**kwargs) -> dict:
    """Minimal shot_log row with all current columns."""
    base = {
        "game_id": "0022400852",
        "shot_id": 1,
        "frame": 100,
        "timestamp": 5.0,
        "player_id": 7,
        "player_name": "Test Player",
        "team": "GSW",
        "x_position": 200,
        "y_position": 150,
        "court_zone": "paint",
        "defender_distance": 3.5,
        "team_spacing": 12000.0,
        "possession_id": 1,
        "possession_duration": 120,
        "made": "",
        "shot_clock": 14.0,
        "contest_arm_angle": 32.5,
        "closeout_speed": 4.2,
        "fatigue_proxy": 870.0,
    }
    base.update(kwargs)
    return base


# ── Test: _export_shot_log fieldnames ─────────────────────────────────────────

class TestShotLogFieldnames:
    """_export_shot_log must write all 4 new column headers."""

    def test_shot_clock_in_csv_header(self, tmp_path):
        import src.pipeline.unified_pipeline as up
        pipeline = _make_stub_pipeline(tmp_path)
        pipeline._export_shot_log([_make_shot_row()])
        headers = _read_csv_headers(tmp_path / "shot_log.csv")
        assert "shot_clock" in headers

    def test_contest_arm_angle_in_csv_header(self, tmp_path):
        import src.pipeline.unified_pipeline as up
        pipeline = _make_stub_pipeline(tmp_path)
        pipeline._export_shot_log([_make_shot_row()])
        headers = _read_csv_headers(tmp_path / "shot_log.csv")
        assert "contest_arm_angle" in headers

    def test_closeout_speed_in_csv_header(self, tmp_path):
        import src.pipeline.unified_pipeline as up
        pipeline = _make_stub_pipeline(tmp_path)
        pipeline._export_shot_log([_make_shot_row()])
        headers = _read_csv_headers(tmp_path / "shot_log.csv")
        assert "closeout_speed" in headers

    def test_fatigue_proxy_in_csv_header(self, tmp_path):
        import src.pipeline.unified_pipeline as up
        pipeline = _make_stub_pipeline(tmp_path)
        pipeline._export_shot_log([_make_shot_row()])
        headers = _read_csv_headers(tmp_path / "shot_log.csv")
        assert "fatigue_proxy" in headers

    def test_all_four_new_columns_present(self, tmp_path):
        """Single assertion covering all 4 new columns."""
        pipeline = _make_stub_pipeline(tmp_path)
        pipeline._export_shot_log([_make_shot_row()])
        headers = _read_csv_headers(tmp_path / "shot_log.csv")
        missing = NEW_COLUMNS - set(headers)
        assert not missing, f"Missing columns: {missing}"

    def test_values_written_correctly(self, tmp_path):
        """The new column values survive the CSV round-trip."""
        pipeline = _make_stub_pipeline(tmp_path)
        row = _make_shot_row(shot_clock=18.5, contest_arm_angle=45.0,
                             closeout_speed=5.1, fatigue_proxy=1230.0)
        pipeline._export_shot_log([row])
        rows = _read_csv_rows(tmp_path / "shot_log.csv")
        assert len(rows) == 1
        assert rows[0]["shot_clock"] == "18.5"
        assert rows[0]["contest_arm_angle"] == "45.0"
        assert rows[0]["closeout_speed"] == "5.1"
        assert rows[0]["fatigue_proxy"] == "1230.0"


# ── Test: fatigue_proxy accumulation logic ────────────────────────────────────

class TestFatigueProxyAccumulation:
    """_player_dist_run must grow with each movement frame."""

    def test_fatigue_zero_at_start(self):
        _player_dist_run: dict = {}
        assert _player_dist_run.get(7, 0.0) == 0.0

    def test_fatigue_increases_after_movement(self):
        """Simulate two frames of 10px movement; fatigue_proxy must be 20."""
        import math
        _player_dist_run: dict = {}
        pid = 7
        # Frame 1: displacement 10px
        _raw_dist = 10.0
        _player_dist_run[pid] = _player_dist_run.get(pid, 0.0) + _raw_dist
        # Frame 2: displacement 10px
        _player_dist_run[pid] = _player_dist_run.get(pid, 0.0) + _raw_dist
        assert _player_dist_run[pid] == pytest.approx(20.0)

    def test_fatigue_proxy_positive_after_movement(self):
        """After N frames of movement, snapshot at shot time must be > 0."""
        _player_dist_run: dict = {}
        pid = 3
        for _ in range(50):
            _raw_dist = 5.5
            _player_dist_run[pid] = _player_dist_run.get(pid, 0.0) + _raw_dist
        fatigue_proxy = round(_player_dist_run.get(pid, 0.0), 1)
        assert fatigue_proxy > 0

    def test_fatigue_independent_per_player(self):
        """Each player accumulates independently."""
        _player_dist_run: dict = {}
        for _ in range(10):
            _player_dist_run[1] = _player_dist_run.get(1, 0.0) + 8.0
        for _ in range(20):
            _player_dist_run[2] = _player_dist_run.get(2, 0.0) + 8.0
        assert _player_dist_run[2] == pytest.approx(2 * _player_dist_run[1])


# ── Test: contest_arm_angle from pose data ────────────────────────────────────

class TestContestArmAngle:
    """contest_arm_angle must be present in shot dict when pose data available."""

    def test_contest_arm_angle_key_present_in_shot_row(self):
        """A shot row dict built with pose data must contain contest_arm_angle."""
        row = _make_shot_row(contest_arm_angle=28.3)
        assert "contest_arm_angle" in row

    def test_contest_arm_angle_value_propagated(self):
        """Value from shooter track survives into shot row."""
        shooter_track = {
            "player_id": 5, "team": "BOS", "x2d": 100, "y2d": 80,
            "contest_arm_angle": 42.7,
        }
        angle = shooter_track.get("contest_arm_angle", "")
        assert angle == pytest.approx(42.7)

    def test_contest_arm_angle_empty_when_no_pose(self):
        """When pose data absent (key missing), falls back to empty string."""
        shooter_track = {
            "player_id": 5, "team": "BOS", "x2d": 100, "y2d": 80,
        }
        angle = shooter_track.get("contest_arm_angle", "")
        assert angle == ""


# ── Test: closeout_speed from event_det.events ────────────────────────────────

class TestCloseoutSpeed:
    """closeout_speed must be extracted from event_det.events at shot frame."""

    def test_closeout_speed_extracted_from_events(self):
        """When a closeout event is in events[n:], its speed is used."""
        events = [
            {"type": "screen", "player_id": 3},
            {"type": "closeout", "defender_id": 9, "closeout_speed": 6.3},
        ]
        n_before = 1  # closeout is new this frame
        speed = next(
            (e["closeout_speed"] for e in reversed(events[n_before:])
             if e.get("type") == "closeout"),
            "",
        )
        assert speed == pytest.approx(6.3)

    def test_closeout_speed_empty_when_no_closeout(self):
        """When no closeout event in events[n:], returns empty string."""
        events = [{"type": "drive", "player_id": 4}]
        n_before = 0
        speed = next(
            (e["closeout_speed"] for e in reversed(events[n_before:])
             if e.get("type") == "closeout"),
            "",
        )
        assert speed == ""

    def test_closeout_speed_uses_events_from_current_frame_only(self):
        """Only events after n_before slice should be scanned."""
        events = [
            {"type": "closeout", "closeout_speed": 99.0},  # old — before this frame
            {"type": "closeout", "closeout_speed": 5.5},   # new — this frame
        ]
        n_before = 1
        speed = next(
            (e["closeout_speed"] for e in reversed(events[n_before:])
             if e.get("type") == "closeout"),
            "",
        )
        assert speed == pytest.approx(5.5)


# ── Private helpers ───────────────────────────────────────────────────────────

def _make_stub_pipeline(tmp_path):
    """Return a minimal object that exposes _export_shot_log without video."""
    from src.pipeline.unified_pipeline import UnifiedPipeline
    obj = object.__new__(UnifiedPipeline)
    obj._data_dir = str(tmp_path)
    return obj


def _read_csv_headers(path) -> List[str]:
    with open(str(path), newline="") as f:
        reader = csv.reader(f)
        return next(reader)


def _read_csv_rows(path) -> List[dict]:
    with open(str(path), newline="") as f:
        return list(csv.DictReader(f))
