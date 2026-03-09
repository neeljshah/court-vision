"""Tests for off-ball movement event detection (FE-03).

Tests cover: cut, screen, drift classification plus degenerate cases.
Uses synthetic frame sequences — no database or numpy required.
"""

import pytest
from features.off_ball_events import (
    detect_off_ball_events,
    CUT_SPEED_THRESHOLD,
    SCREEN_SPEED_THRESHOLD,
    SCREEN_PROXIMITY,
    DRIFT_SPEED_MIN,
    DRIFT_SPEED_MAX,
)
from features.types import OffBallEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_player(
    track_id: int,
    x: float,
    y: float,
    speed: float,
    velocity_x: float = 0.0,
    velocity_y: float = 0.0,
    direction_degrees: float = 0.0,
    frame_number: int = 1,
    timestamp_ms: float = 1000.0,
) -> dict:
    return {
        "track_id": track_id,
        "x": x,
        "y": y,
        "speed": speed,
        "velocity_x": velocity_x,
        "velocity_y": velocity_y,
        "direction_degrees": direction_degrees,
        "frame_number": frame_number,
        "timestamp_ms": timestamp_ms,
    }


# ---------------------------------------------------------------------------
# Degenerate / empty cases
# ---------------------------------------------------------------------------

class TestDegenerateCases:
    def test_empty_frame_sequence_returns_empty_list(self):
        result = detect_off_ball_events([], game_id="g1", ball_pos=None)
        assert result == []

    def test_empty_frame_sequence_with_ball_pos_returns_empty_list(self):
        result = detect_off_ball_events([], game_id="g1", ball_pos={"x": 250.0, "y": 150.0})
        assert result == []

    def test_frame_with_no_players_returns_empty_list(self):
        frame_sequence = [[]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result == []

    def test_player_with_no_detectable_pattern_emits_no_event(self):
        # Speed exactly at boundary (not exceeding any threshold) with no screen partner
        player = make_player(track_id=1, x=200.0, y=150.0, speed=15.0)
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos={"x": 200.0, "y": 150.0})
        assert result == []


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_list_of_off_ball_events(self):
        # Fast player moving toward basket — cut
        player = make_player(
            track_id=1, x=200.0, y=150.0, speed=250.0,
            velocity_x=250.0, velocity_y=0.0
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert isinstance(result, list)
        for evt in result:
            assert isinstance(evt, OffBallEvent)

    def test_event_game_id_matches_parameter(self):
        player = make_player(
            track_id=1, x=200.0, y=150.0, speed=250.0,
            velocity_x=250.0, velocity_y=0.0
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="test-game-99", ball_pos=None)
        assert len(result) >= 1
        assert result[0].game_id == "test-game-99"


# ---------------------------------------------------------------------------
# Cut detection
# ---------------------------------------------------------------------------

class TestCutDetection:
    def _make_cut_frame_sequence(self, speed=250.0, track_id=1):
        # Player moving fast to the right (toward basket at x=470)
        player = make_player(
            track_id=track_id, x=200.0, y=150.0, speed=speed,
            velocity_x=speed, velocity_y=0.0,
            frame_number=5, timestamp_ms=5000.0,
        )
        return [[player]]

    def test_fast_player_toward_basket_is_tagged_cut(self):
        frame_sequence = self._make_cut_frame_sequence(speed=250.0)
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert len(result) == 1
        assert result[0].event_type == "cut"

    def test_cut_event_has_correct_track_id(self):
        frame_sequence = self._make_cut_frame_sequence(speed=300.0, track_id=7)
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result[0].track_id == 7

    def test_cut_confidence_is_positive(self):
        frame_sequence = self._make_cut_frame_sequence(speed=250.0)
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result[0].confidence > 0.0

    def test_cut_confidence_capped_at_1(self):
        # Very high speed should still cap at 1.0
        frame_sequence = self._make_cut_frame_sequence(speed=10000.0)
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result[0].confidence <= 1.0

    def test_higher_speed_proportionally_higher_confidence(self):
        fast = self._make_cut_frame_sequence(speed=400.0)
        slow = self._make_cut_frame_sequence(speed=210.0)
        r_fast = detect_off_ball_events(fast, game_id="g1", ball_pos=None)
        r_slow = detect_off_ball_events(slow, game_id="g1", ball_pos=None)
        assert r_fast[0].confidence >= r_slow[0].confidence

    def test_speed_below_threshold_not_a_cut(self):
        # Speed just below threshold
        frame_sequence = self._make_cut_frame_sequence(speed=CUT_SPEED_THRESHOLD - 1)
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        cut_events = [e for e in result if e.event_type == "cut"]
        assert cut_events == []

    def test_cut_frame_number_from_most_recent_frame(self):
        player = make_player(
            track_id=1, x=200.0, y=150.0, speed=250.0,
            velocity_x=250.0, velocity_y=0.0,
            frame_number=42, timestamp_ms=42000.0
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result[0].frame_number == 42
        assert result[0].timestamp_ms == 42000.0

    def test_player_moving_away_from_basket_is_not_a_cut(self):
        # Moving left (negative x velocity) — away from basket at x=470
        player = make_player(
            track_id=1, x=400.0, y=150.0, speed=250.0,
            velocity_x=-250.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        cut_events = [e for e in result if e.event_type == "cut"]
        assert cut_events == []


# ---------------------------------------------------------------------------
# Screen detection
# ---------------------------------------------------------------------------

class TestScreenDetection:
    def test_slow_player_near_faster_player_is_tagged_screen(self):
        # Screener: slow, stationary
        screener = make_player(
            track_id=10, x=300.0, y=150.0, speed=10.0,
            velocity_x=0.0, velocity_y=0.0,
        )
        # Mover: fast, close by
        mover = make_player(
            track_id=11, x=330.0, y=150.0, speed=150.0,
            velocity_x=150.0, velocity_y=0.0,
        )
        frame_sequence = [[screener, mover]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        screen_events = [e for e in result if e.event_type == "screen"]
        assert len(screen_events) >= 1
        screen_track_ids = [e.track_id for e in screen_events]
        assert 10 in screen_track_ids

    def test_screen_confidence_is_0_8(self):
        screener = make_player(
            track_id=10, x=300.0, y=150.0, speed=10.0,
        )
        mover = make_player(
            track_id=11, x=330.0, y=150.0, speed=150.0,
            velocity_x=150.0, velocity_y=0.0,
        )
        frame_sequence = [[screener, mover]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        screen_events = [e for e in result if e.event_type == "screen"]
        for e in screen_events:
            if e.track_id == 10:
                assert e.confidence == 0.8

    def test_slow_player_far_from_others_is_not_a_screen(self):
        # Slow player but no one nearby
        slow_player = make_player(
            track_id=10, x=300.0, y=150.0, speed=10.0,
        )
        far_player = make_player(
            track_id=11, x=500.0, y=300.0, speed=200.0,
            velocity_x=200.0, velocity_y=0.0,
        )
        frame_sequence = [[slow_player, far_player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        screen_events = [e for e in result if e.event_type == "screen" and e.track_id == 10]
        assert screen_events == []

    def test_slow_player_near_equally_slow_player_is_not_a_screen(self):
        # Both slow — no "faster" player nearby
        slow1 = make_player(track_id=10, x=300.0, y=150.0, speed=10.0)
        slow2 = make_player(track_id=11, x=320.0, y=150.0, speed=15.0)
        frame_sequence = [[slow1, slow2]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        screen_events = [e for e in result if e.event_type == "screen"]
        assert screen_events == []

    def test_single_player_cannot_be_screener(self):
        slow_player = make_player(track_id=10, x=300.0, y=150.0, speed=10.0)
        frame_sequence = [[slow_player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert result == []


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

class TestDriftDetection:
    def test_medium_speed_player_moving_laterally_away_from_ball_is_tagged_drift(self):
        # Ball at x=300, y=150. Player at x=300, y=50. Moving in -y direction (away laterally).
        # Ball-to-player vector: (0, -100). Velocity: (0, -60).
        # Lateral: velocity perpendicular to ball-player vector = cross product.
        # To get drift: player moving laterally away. We'll use purely lateral motion.
        ball_pos = {"x": 300.0, "y": 150.0}
        # Player below ball, moving further down (away in y axis)
        player = make_player(
            track_id=5, x=300.0, y=50.0, speed=60.0,
            velocity_x=60.0, velocity_y=0.0,  # Moving laterally (perpendicular to ball vector)
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=ball_pos)
        drift_events = [e for e in result if e.event_type == "drift"]
        assert len(drift_events) >= 1
        assert drift_events[0].track_id == 5

    def test_drift_confidence_is_0_6(self):
        ball_pos = {"x": 300.0, "y": 150.0}
        player = make_player(
            track_id=5, x=300.0, y=50.0, speed=60.0,
            velocity_x=60.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=ball_pos)
        drift_events = [e for e in result if e.event_type == "drift" and e.track_id == 5]
        if drift_events:
            assert drift_events[0].confidence == pytest.approx(0.6)

    def test_player_below_min_drift_speed_not_tagged_drift(self):
        ball_pos = {"x": 300.0, "y": 150.0}
        # Speed 20 < DRIFT_SPEED_MIN (30)
        player = make_player(
            track_id=5, x=300.0, y=50.0, speed=20.0,
            velocity_x=20.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=ball_pos)
        drift_events = [e for e in result if e.event_type == "drift" and e.track_id == 5]
        assert drift_events == []

    def test_player_above_max_drift_speed_not_tagged_drift(self):
        ball_pos = {"x": 300.0, "y": 150.0}
        # Speed 110 > DRIFT_SPEED_MAX (100)
        player = make_player(
            track_id=5, x=300.0, y=50.0, speed=110.0,
            velocity_x=110.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=ball_pos)
        drift_events = [e for e in result if e.event_type == "drift" and e.track_id == 5]
        assert drift_events == []

    def test_drift_requires_ball_pos(self):
        # Without ball_pos drift cannot be computed — no drift event
        player = make_player(
            track_id=5, x=300.0, y=50.0, speed=60.0,
            velocity_x=60.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        drift_events = [e for e in result if e.event_type == "drift"]
        assert drift_events == []


# ---------------------------------------------------------------------------
# Priority: cut > screen > drift
# ---------------------------------------------------------------------------

class TestEventPriority:
    def test_cut_takes_priority_over_screen(self):
        # Fast player (cut-eligible) that is also slow enough to be screener?
        # Actually: can't be both cut and screen at same speed. Test: multiple players,
        # one player could match both — ensure only cut emitted.
        # Player 1: very fast (cut), also near player 2
        cutter = make_player(
            track_id=1, x=300.0, y=150.0, speed=260.0,
            velocity_x=260.0, velocity_y=0.0,
        )
        # Player 2: nearby, slower (screen candidate for player 1?)
        # Player 1 is the cutter and also near player 2 who is slow.
        # Player 2 is slow -> screen candidate
        slow_nearby = make_player(
            track_id=2, x=330.0, y=150.0, speed=15.0,
        )
        frame_sequence = [[cutter, slow_nearby]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        # Cutter should emit only one event (cut), not also screen
        cutter_events = [e for e in result if e.track_id == 1]
        assert len(cutter_events) == 1
        assert cutter_events[0].event_type == "cut"

    def test_at_most_one_event_per_player_per_frame(self):
        player = make_player(
            track_id=1, x=200.0, y=150.0, speed=250.0,
            velocity_x=250.0, velocity_y=0.0,
        )
        frame_sequence = [[player]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos={"x": 300.0, "y": 150.0})
        player1_events = [e for e in result if e.track_id == 1]
        assert len(player1_events) <= 1

    def test_multiple_players_can_each_emit_event(self):
        cutter1 = make_player(
            track_id=1, x=200.0, y=150.0, speed=250.0,
            velocity_x=250.0, velocity_y=0.0, frame_number=1, timestamp_ms=1000.0
        )
        cutter2 = make_player(
            track_id=2, x=100.0, y=200.0, speed=300.0,
            velocity_x=300.0, velocity_y=0.0, frame_number=1, timestamp_ms=1000.0
        )
        frame_sequence = [[cutter1, cutter2]]
        result = detect_off_ball_events(frame_sequence, game_id="g1", ball_pos=None)
        assert len(result) == 2
