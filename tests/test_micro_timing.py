"""Tests for src/analytics/micro_timing.py

Covers:
  - _build_event: constructs MicroTimingEvent with correct decision probs
  - compute_micro_timing: detects catch-and-shoot, catch-and-drive, catch-and-pass events
  - decision probabilities sum to 1; event fields are valid
"""
from __future__ import annotations

import math
import pytest

from src.analytics.micro_timing import (
    MicroTimingEvent,
    _build_event,
    compute_micro_timing,
)

# ---------------------------------------------------------------------------
# Helpers to build minimal frame dicts
# ---------------------------------------------------------------------------

def _ball(fn: int, x: float = 0.0, y: float = 0.0, speed: float = 0.0) -> dict:
    return {"object_type": "ball", "track_id": -1, "x": x, "y": y,
            "x_ft": x, "y_ft": y, "speed": speed}


def _player(track_id: int, x: float, y: float, speed: float = 0.0) -> dict:
    return {"object_type": "player", "track_id": track_id,
            "x": x, "y": y, "x_ft": x, "y_ft": y, "speed": speed}


def _frames(*rows) -> dict:
    """Build frames_by_number from (frame_number, *objects) tuples."""
    result = {}
    for item in rows:
        fn, objs = item[0], list(item[1:])
        result[fn] = objs
    return result


# ---------------------------------------------------------------------------
# _build_event
# ---------------------------------------------------------------------------

class TestBuildEvent:
    def test_decision_probs_sum_to_one(self) -> None:
        ev = _build_event(1, 10, "catch_and_shoot", catch_to_shot=0.4)
        total = ev.shot_decision_prob + ev.drive_decision_prob + ev.pass_decision_prob
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_catch_and_shoot_has_highest_shot_prob(self) -> None:
        ev = _build_event(1, 10, "catch_and_shoot", catch_to_shot=0.3)
        assert ev.shot_decision_prob > ev.drive_decision_prob
        assert ev.shot_decision_prob > ev.pass_decision_prob

    def test_catch_and_drive_has_high_drive_prob(self) -> None:
        ev = _build_event(1, 10, "catch_and_drive", catch_to_drive=0.5)
        assert ev.drive_decision_prob > ev.shot_decision_prob

    def test_catch_and_pass_has_high_pass_prob(self) -> None:
        ev = _build_event(1, 10, "catch_and_pass", catch_to_pass=1.0)
        assert ev.pass_decision_prob > ev.shot_decision_prob

    def test_fields_populated(self) -> None:
        ev = _build_event(5, 99, "catch_and_shoot", catch_to_shot=0.2,
                          decision_latency=0.2)
        assert ev.track_id == 5
        assert ev.frame_number == 99
        assert ev.event_type == "catch_and_shoot"
        assert ev.catch_to_shot_time == pytest.approx(0.2)
        assert ev.decision_latency == pytest.approx(0.2)

    def test_probs_are_in_range(self) -> None:
        for event_type, kwargs in [
            ("catch_and_shoot", {"catch_to_shot": 0.3}),
            ("catch_and_drive", {"catch_to_drive": 0.4}),
            ("catch_and_pass",  {"catch_to_pass": 1.2}),
        ]:
            ev = _build_event(1, 1, event_type, **kwargs)
            for p in (ev.shot_decision_prob, ev.drive_decision_prob, ev.pass_decision_prob):
                assert 0.0 <= p <= 1.0


# ---------------------------------------------------------------------------
# compute_micro_timing
# ---------------------------------------------------------------------------

class TestComputeMicroTiming:
    def test_empty_frames_returns_empty(self) -> None:
        result = compute_micro_timing({}, [], fps=30.0)
        assert result == []

    def test_no_ball_returns_empty(self) -> None:
        frames = {0: [_player(1, 5, 5)], 1: [_player(1, 5, 5)]}
        result = compute_micro_timing(frames, [0, 1])
        assert result == []

    def test_catch_and_shoot_detected(self) -> None:
        # Frame 0: player 1 holds ball (close), frame 5: ball flying fast (shot)
        frames = {
            0: [_ball(0, x=5, y=5, speed=0), _player(1, 5, 5, speed=0)],
            5: [_ball(5, x=6, y=6, speed=60), _player(1, 5, 5, speed=1)],
        }
        result = compute_micro_timing(frames, [0, 5], fps=30.0)
        shot_events = [e for e in result if e.event_type == "catch_and_shoot"]
        assert len(shot_events) >= 1
        ev = shot_events[0]
        assert ev.catch_to_shot_time is not None
        assert ev.catch_to_shot_time >= 0.0

    def test_catch_and_drive_detected(self) -> None:
        # Player 2 catches at frame 0, then moves fast at frame 3 (<2s at 30fps)
        frames = {
            0: [_ball(0, x=0, y=0, speed=0), _player(2, 0, 0, speed=0)],
            3: [_ball(3, x=1, y=1, speed=5), _player(2, 1, 1, speed=12)],
        }
        result = compute_micro_timing(frames, [0, 3], fps=30.0)
        drive_events = [e for e in result if e.event_type == "catch_and_drive"]
        assert len(drive_events) >= 1

    def test_catch_and_pass_detected(self) -> None:
        # Ball stays near player (within CATCH_PROXIMITY_FT=4ft) but moves at pass speed.
        # This keeps player as current_holder so the pass branch fires.
        frames = {
            0:  [_ball(0, x=0, y=0, speed=0), _player(3, 0, 0, speed=0)],
            15: [_ball(15, x=1, y=1, speed=30), _player(3, 0, 0, speed=2)],
        }
        result = compute_micro_timing(frames, [0, 15], fps=30.0)
        pass_events = [e for e in result if e.event_type == "catch_and_pass"]
        assert len(pass_events) >= 1

    def test_all_events_have_valid_probs(self) -> None:
        frames = {
            0: [_ball(0, x=0, y=0, speed=0), _player(1, 0, 0, speed=0)],
            5: [_ball(5, x=1, y=1, speed=60), _player(1, 0.5, 0.5, speed=1)],
        }
        result = compute_micro_timing(frames, [0, 5], fps=30.0)
        for ev in result:
            total = ev.shot_decision_prob + ev.drive_decision_prob + ev.pass_decision_prob
            assert total == pytest.approx(1.0, abs=1e-9)

    def test_result_types(self) -> None:
        frames = {
            0: [_ball(0, x=0, y=0, speed=0), _player(1, 0, 0, speed=0)],
            4: [_ball(4, x=1, y=1, speed=55), _player(1, 1, 1, speed=0)],
        }
        result = compute_micro_timing(frames, [0, 4], fps=30.0)
        for ev in result:
            assert isinstance(ev, MicroTimingEvent)
