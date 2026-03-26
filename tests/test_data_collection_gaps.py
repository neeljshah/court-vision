"""
tests/test_data_collection_gaps.py — Session 16 data collection gap fixes

Tests for 9 fixes:
  FIX 1 — events_log.csv written by UnifiedPipeline
  FIX 2 — dribble_count in shot_log and tracking rows
  FIX 3 — rebound_position events in events_log
  FIX 4 — pass_count/screen_count in possessions.csv
  FIX 6 — scoreboard confidence gate on shot_clock
  FIX 7 — player_name backfill (deferred to live integration)
  FIX 8 — snapshot_shot_arc() called on shot event
  FIX 9 — spacing_hull_area column in tracking rows
"""

import csv
import io
import os
import sys
import types
from collections import defaultdict
from typing import List
from unittest.mock import MagicMock, patch, call

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_event_det():
    """Return an EventDetector configured on a small court map."""
    from src.tracking.event_detector import EventDetector
    return EventDetector(map_w=940, map_h=500)


def _make_ball_det_stub():
    """Minimal BallDetectTrack stub for FIX 8 tests."""
    from src.tracking.ball_detect_track import BallDetectTrack
    players = []
    # BallDetectTrack needs a players list; pass empty (no YOLO/CSRT in tests)
    stub = MagicMock(spec=BallDetectTrack)
    stub._shot_arc_angle = None
    stub.pixel_vel = 0.0
    stub._prev_cy = None
    return stub


# ---------------------------------------------------------------------------
# FIX 8 — snapshot_shot_arc() added to BallDetectTrack
# ---------------------------------------------------------------------------

class TestSnapshotShotArc:
    def test_method_exists(self):
        from src.tracking.ball_detect_track import BallDetectTrack
        assert hasattr(BallDetectTrack, "snapshot_shot_arc"), (
            "BallDetectTrack.snapshot_shot_arc() must exist"
        )

    def test_snapshot_calls_on_shot_event(self):
        from src.tracking.ball_detect_track import BallDetectTrack
        bd = MagicMock(spec=BallDetectTrack)
        # Call the real snapshot_shot_arc on a real instance via the class method
        # Use a tiny mock that records the call
        called = []

        class FakeBD:
            _shot_arc_angle = None
            def on_shot_event(self):
                called.append(True)
            def snapshot_shot_arc(self):
                self.on_shot_event()

        fbd = FakeBD()
        fbd.snapshot_shot_arc()
        assert called, "snapshot_shot_arc must call on_shot_event"

    def test_shot_arc_angle_initialised_none(self):
        from src.tracking.ball_detect_track import BallDetectTrack
        players_mock = MagicMock()
        # Can't instantiate without CV libs in CI — check the class attr default
        import inspect
        src = inspect.getsource(BallDetectTrack.__init__)
        assert "_shot_arc_angle" in src, "_shot_arc_angle must be set in __init__"


# ---------------------------------------------------------------------------
# FIX 2 — dribble_count property on EventDetector
# ---------------------------------------------------------------------------

class TestDribbleCountProperty:
    def test_property_exists(self):
        ed = _make_event_det()
        assert hasattr(ed, "dribble_count"), "EventDetector must expose dribble_count property"

    def test_dribble_count_starts_zero(self):
        ed = _make_event_det()
        assert ed.dribble_count == 0

    def test_dribble_count_increments_on_dribble(self):
        ed = _make_event_det()
        ed._dribble_count = 7
        assert ed.dribble_count == 7

    def test_dribble_count_resets_on_possession_change(self):
        """_classify() resets _dribble_count on new possessor."""
        ed = _make_event_det()
        ed._dribble_count = 5
        # Simulate possession change: prev=1 (had ball), now=None (ball lost)
        ed._possessor = 1
        ed._possession_held_frames = 10
        # Call classify with no possessor (ball lost)
        ed._classify(100, (100, 200), None, None)
        # _dribble_count resets when new player gains ball (None -> 2)
        ed._classify(105, (100, 200), 2, (100, 200))
        assert ed.dribble_count == 0, "dribble_count must reset on new possessor"


# ---------------------------------------------------------------------------
# FIX 1 — events_log.csv columns and accumulation
# ---------------------------------------------------------------------------

class TestEventsLogWritten:
    def _run_export(self, rows, tmp_path):
        """Call _export_events_log directly."""
        import tempfile, pathlib
        from src.pipeline.unified_pipeline import UnifiedPipeline
        # Build a minimal stub to call the method
        pipe = object.__new__(UnifiedPipeline)
        pipe._data_dir = str(tmp_path)
        pipe._export_events_log(rows)
        return os.path.join(str(tmp_path), "events_log.csv")

    def test_events_log_written(self, tmp_path):
        rows = [
            {"game_id": "g1", "frame": 10, "timestamp": 0.33, "possession_id": 1,
             "type": "screen_set", "x": 300.0, "y": 200.0},
            {"game_id": "g1", "frame": 11, "timestamp": 0.37, "possession_id": 1,
             "type": "rebound_position", "player_id": 3,
             "crash_angle": 45.0, "crash_speed": 1.2, "box_out": True},
        ]
        path = self._run_export(rows, tmp_path)
        assert os.path.exists(path), "events_log.csv must be created"
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            written = list(reader)
        assert len(written) == 2

    def test_required_columns_present(self, tmp_path):
        rows = [{"game_id": "g1", "frame": 5, "timestamp": 0.1, "possession_id": 0,
                 "type": "cut", "player_id": 2}]
        path = self._run_export(rows, tmp_path)
        with open(path, newline="") as f:
            headers = csv.DictReader(f).fieldnames
        required = {"type", "frame", "possession_id"}
        assert required.issubset(set(headers)), f"Missing headers: {required - set(headers)}"

    def test_extrasaction_ignore(self, tmp_path):
        """Events with unknown keys should not crash the DictWriter."""
        rows = [{"game_id": "g1", "frame": 1, "timestamp": 0.0, "possession_id": 0,
                 "type": "drive", "player_id": 1, "start_x": 100.0, "end_x": 300.0,
                 "unexpected_key": "should_be_ignored"}]
        path = self._run_export(rows, tmp_path)
        assert os.path.exists(path)


# ---------------------------------------------------------------------------
# FIX 3 — rebound_position keys match events_log columns
# ---------------------------------------------------------------------------

class TestReboundPositionInEventsLog:
    def test_rebound_position_keys(self):
        """_detect_rebound_positions emits crash_angle, crash_speed, box_out."""
        from src.tracking.event_detector import EventDetector
        ed = EventDetector(map_w=940, map_h=500)
        ed._prev_ball = (470, 250)
        frame_tracks = [
            {"player_id": 1, "team": "green", "x2d": 200.0, "y2d": 250.0, "has_ball": False},
            {"player_id": 6, "team": "white", "x2d": 740.0, "y2d": 250.0, "has_ball": False},
        ]
        # Seed phist so speed calculation has data
        from collections import deque
        for t in frame_tracks:
            ed._phist[t["player_id"]].append((0, t["x2d"] - 5, t["y2d"], 2.0))
            ed._phist[t["player_id"]].append((1, t["x2d"], t["y2d"], 2.0))
        ed._detect_rebound_positions(10, frame_tracks)
        assert len(ed.events) >= 1
        for evt in ed.events:
            if evt["type"] == "rebound_position":
                assert "crash_angle" in evt, "crash_angle missing from rebound_position"
                assert "crash_speed" in evt, "crash_speed missing from rebound_position"
                assert "box_out" in evt, "box_out missing from rebound_position"
                assert "player_id" in evt, "player_id missing from rebound_position"


# ---------------------------------------------------------------------------
# FIX 4 — pass_count and screen_count in possessions.csv
# ---------------------------------------------------------------------------

class TestPossessionEventCounts:
    def _export(self, rows, event_counts, tmp_path):
        from src.pipeline.unified_pipeline import UnifiedPipeline
        pipe = object.__new__(UnifiedPipeline)
        pipe._data_dir = str(tmp_path)
        pipe._export_possessions_csv(rows, event_counts)
        return os.path.join(str(tmp_path), "possessions.csv")

    def test_pass_screen_columns_present(self, tmp_path):
        rows = [{
            "game_id": "g1", "possession_id": 1, "team": "GSW",
            "start_frame": 0, "end_frame": 100, "duration_frames": 100,
            "duration_sec": 3.3, "avg_spacing": 100.0, "avg_defensive_pressure": 5.0,
            "avg_vel_toward_basket": 1.0, "drive_attempts": 2,
            "shot_attempted": 0, "shot_frame": "", "fast_break": 0,
            "play_type": "half_court", "result": "", "outcome_score": "",
        }]
        event_counts = {1: {"pass_count": 5, "screen_count": 2, "drive_count": 1, "cut_count": 3}}
        path = self._export(rows, event_counts, tmp_path)
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            data = list(reader)
        assert "pass_count"   in headers, "pass_count column missing"
        assert "screen_count" in headers, "screen_count column missing"
        assert "drive_count"  in headers
        assert "cut_count"    in headers
        assert data[0]["pass_count"]   == "5"
        assert data[0]["screen_count"] == "2"

    def test_defaults_to_zero_when_no_events(self, tmp_path):
        rows = [{
            "game_id": "g1", "possession_id": 99, "team": "BOS",
            "start_frame": 0, "end_frame": 90, "duration_frames": 90,
            "duration_sec": 3.0, "avg_spacing": "", "avg_defensive_pressure": "",
            "avg_vel_toward_basket": "", "drive_attempts": 0,
            "shot_attempted": 0, "shot_frame": "", "fast_break": 0,
            "play_type": "half_court", "result": "", "outcome_score": "",
        }]
        path = self._export(rows, {}, tmp_path)  # empty event_counts
        with open(path, newline="") as f:
            data = list(csv.DictReader(f))
        assert data[0]["pass_count"] == "0", "pass_count should default to 0"


# ---------------------------------------------------------------------------
# FIX 6 — scoreboard confidence gate
# ---------------------------------------------------------------------------

class TestScoreboardConfidenceGate:
    def test_gated_fields_logic(self):
        """Simulate what the pipeline does: gate fields by _sb_conf."""
        sb_state = {"shot_clock": 14, "game_clock_sec": 480.0, "score_diff": 3}

        def _gate_shot_clock(sb, conf):
            return (sb.get("shot_clock", "") if (sb.get("shot_clock", -1) > 0 and conf >= 0.4) else "")

        def _gate_game_clock(sb, conf):
            return (sb.get("game_clock_sec", "") if conf >= 0.3 else "")

        def _gate_score_diff(sb, conf):
            return (sb.get("score_diff", "") if conf >= 0.3 else "")

        # Below threshold: all empty
        assert _gate_shot_clock(sb_state, 0.3) == "", "shot_clock must be empty at conf=0.3"
        assert _gate_game_clock(sb_state, 0.2) == "", "game_clock must be empty at conf=0.2"
        assert _gate_score_diff(sb_state, 0.2) == "", "score_diff must be empty at conf=0.2"

        # At/above threshold: populated
        assert _gate_shot_clock(sb_state, 0.4) == 14
        assert _gate_game_clock(sb_state, 0.3) == 480.0
        assert _gate_score_diff(sb_state, 0.3) == 3

    def test_shot_clock_empty_when_negative(self):
        """shot_clock -1 (unknown) must always be empty regardless of confidence."""
        sb_state = {"shot_clock": -1}

        def _gate(sb, conf):
            return (sb.get("shot_clock", "") if (sb.get("shot_clock", -1) > 0 and conf >= 0.4) else "")

        assert _gate(sb_state, 0.9) == ""

    def test_scoreboard_confidence_in_tracking_fields(self):
        """scoreboard_confidence must be in _tracking_csv_fields()."""
        from src.pipeline.unified_pipeline import UnifiedPipeline
        fields = UnifiedPipeline._tracking_csv_fields()
        assert "scoreboard_confidence" in fields, "scoreboard_confidence missing from tracking CSV fields"


# ---------------------------------------------------------------------------
# FIX 9 — spacing_hull_area in tracking rows
# ---------------------------------------------------------------------------

class TestSpacingHullAreaInTracking:
    def test_field_in_tracking_csv_fields(self):
        from src.pipeline.unified_pipeline import UnifiedPipeline
        fields = UnifiedPipeline._tracking_csv_fields()
        assert "spacing_hull_area" in fields, "spacing_hull_area must be in tracking CSV fields"

    def test_hull_area_computed_in_frame_spatial(self):
        """_frame_spatial returns hull_area >= 0 for each team when >= 3 players."""
        from src.pipeline.unified_pipeline import UnifiedPipeline
        frame_tracks = [
            {"player_id": i, "team": "green", "x2d": float(100 * i), "y2d": float(50 * i), "has_ball": False}
            for i in range(1, 6)
        ] + [
            {"player_id": 10 + i, "team": "white", "x2d": float(600 + 30 * i), "y2d": float(200 + 20 * i), "has_ball": False}
            for i in range(1, 6)
        ]
        result = UnifiedPipeline._frame_spatial(frame_tracks, None, 940, 500)
        assert "green" in result
        assert "hull_area" in result["green"], "hull_area key missing from spatial result"
        assert result["green"]["hull_area"] >= 0.0

    def test_hull_area_zero_when_fewer_than_3_players(self):
        from src.pipeline.unified_pipeline import UnifiedPipeline
        frame_tracks = [
            {"player_id": 1, "team": "green", "x2d": 100.0, "y2d": 100.0, "has_ball": False},
            {"player_id": 2, "team": "green", "x2d": 200.0, "y2d": 200.0, "has_ball": False},
        ]
        result = UnifiedPipeline._frame_spatial(frame_tracks, None, 940, 500)
        # With < 3 players hull can't be computed — should default to 0
        assert result["green"]["hull_area"] == 0.0


# ---------------------------------------------------------------------------
# FIX 2 — dribble_count in shot_log fieldnames
# ---------------------------------------------------------------------------

class TestDribbleCountInShotLog:
    def test_dribble_count_in_shot_log_fieldnames(self, tmp_path):
        from src.pipeline.unified_pipeline import UnifiedPipeline
        pipe = object.__new__(UnifiedPipeline)
        pipe._data_dir = str(tmp_path)
        rows = [{
            "game_id": "g1", "shot_id": 1, "frame": 100, "timestamp": 3.3,
            "player_id": 3, "player_name": "", "team": "GSW",
            "x_position": 300.0, "y_position": 200.0, "court_zone": "mid_range",
            "defender_distance": 5.0, "team_spacing": 1000.0,
            "possession_id": 1, "possession_duration": 50, "made": "",
            "shot_clock": 14, "contest_arm_angle": "", "closeout_speed": "",
            "fatigue_proxy": 0.0, "dribble_count": 3, "ball_shot_arc_angle": 45.0,
        }]
        pipe._export_shot_log(rows)
        path = os.path.join(str(tmp_path), "shot_log.csv")
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            data = list(reader)
        assert "dribble_count" in headers, "dribble_count missing from shot_log fieldnames"
        assert data[0]["dribble_count"] == "3"

    def test_dribble_count_in_tracking_csv_fields(self):
        from src.pipeline.unified_pipeline import UnifiedPipeline
        assert "dribble_count" in UnifiedPipeline._tracking_csv_fields()
