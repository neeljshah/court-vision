"""Tests for pick-and-roll detection (FE-04).

Tests cover: PnR setup → screen → separation sequence, deduplication, and edge cases.
Uses court-feet coordinates and ft/s speeds.
NBA reference: screener ~0-3 ft/s, ball handler ~8+ ft/s, screen contact within 6 ft.
"""

import pytest
from legacy.features.pick_and_roll import (
    detect_pick_and_roll,
    PNR_WINDOW_FRAMES,
    SCREEN_DISTANCE,
    SCREENER_MAX_SPEED,
    HANDLER_MIN_SPEED,
)
from legacy.features.types import PickAndRollEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_player(
    track_id: int,
    x: float,
    y: float,
    speed: float,
    frame_number: int = 0,
    timestamp_ms: float = 0.0,
) -> dict:
    return {
        "track_id": track_id,
        "x": x,
        "y": y,
        "speed": speed,
        "velocity_x": 0.0,
        "velocity_y": 0.0,
        "direction_degrees": 0.0,
        "frame_number": frame_number,
        "timestamp_ms": timestamp_ms,
    }


def make_pnr_sequence(
    handler_id: int = 1,
    screener_id: int = 2,
    window: int = None,
    setup_dist: float = 4.0,   # ft — close in setup frames
    screen_dist: float = 4.0,  # ft — close in middle frame (within SCREEN_DISTANCE=6)
    sep_dist: float = 8.0,     # ft — far in last frame (beyond SCREEN_DISTANCE=6)
) -> list[list[dict]]:
    """Build a canonical PnR frame sequence using court-feet coordinates.

    Args:
        handler_id: Track ID of the ball handler (fast player, 12 ft/s).
        screener_id: Track ID of the screener (slow player, 2 ft/s).
        window: Number of frames (defaults to PNR_WINDOW_FRAMES).
        setup_dist: Distance between players in setup frames (ft).
        screen_dist: Distance in the middle (screen contact) frame (ft).
        sep_dist: Distance in the final separation frame (ft).
    """
    n = window if window is not None else PNR_WINDOW_FRAMES
    frames = []
    for i in range(n):
        if i == n - 1:
            dist = sep_dist   # separation in last frame
        elif i == n // 2:
            dist = screen_dist  # screen contact in middle
        else:
            dist = setup_dist

        handler = make_player(
            track_id=handler_id,
            x=47.0,
            y=25.0,
            speed=12.0,  # ft/s — above HANDLER_MIN_SPEED=8 ft/s
            frame_number=i,
            timestamp_ms=float(i * 100),
        )
        screener = make_player(
            track_id=screener_id,
            x=47.0 + dist,
            y=25.0,
            speed=2.0,  # ft/s — below SCREENER_MAX_SPEED=3 ft/s
            frame_number=i,
            timestamp_ms=float(i * 100),
        )
        frames.append([handler, screener])
    return frames


# ---------------------------------------------------------------------------
# Degenerate / edge cases
# ---------------------------------------------------------------------------

class TestDegenerateCases:
    def test_empty_frame_sequence_returns_empty(self):
        result = detect_pick_and_roll([], game_id="g1")
        assert result == []

    def test_insufficient_frames_returns_empty(self):
        # Fewer frames than PNR_WINDOW_FRAMES
        short_seq = make_pnr_sequence(window=PNR_WINDOW_FRAMES - 1)
        result = detect_pick_and_roll(short_seq, game_id="g1")
        assert result == []

    def test_single_frame_returns_empty(self):
        frame = [make_player(1, 47.0, 25.0, 12.0), make_player(2, 50.0, 25.0, 2.0)]
        result = detect_pick_and_roll([[frame[0], frame[1]]], game_id="g1")
        assert result == []

    def test_single_player_returns_empty(self):
        frames = [[make_player(1, 47.0, 25.0, 12.0, frame_number=i)] for i in range(PNR_WINDOW_FRAMES)]
        result = detect_pick_and_roll(frames, game_id="g1")
        assert result == []


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TestReturnType:
    def test_returns_list_of_pick_and_roll_events(self):
        seq = make_pnr_sequence()
        result = detect_pick_and_roll(seq, game_id="g1")
        assert isinstance(result, list)
        for evt in result:
            assert isinstance(evt, PickAndRollEvent)

    def test_event_game_id_matches_parameter(self):
        seq = make_pnr_sequence()
        result = detect_pick_and_roll(seq, game_id="test-game-42")
        assert len(result) >= 1
        assert result[0].game_id == "test-game-42"


# ---------------------------------------------------------------------------
# PnR detection: canonical case
# ---------------------------------------------------------------------------

class TestPickAndRollDetection:
    def test_canonical_pnr_detected(self):
        seq = make_pnr_sequence(handler_id=1, screener_id=2, screen_dist=4.0, sep_dist=8.0)
        result = detect_pick_and_roll(seq, game_id="g1")
        assert len(result) >= 1

    def test_ball_handler_is_faster_player(self):
        seq = make_pnr_sequence(handler_id=1, screener_id=2)
        result = detect_pick_and_roll(seq, game_id="g1")
        assert result[0].ball_handler_track_id == 1
        assert result[0].screener_track_id == 2

    def test_frame_number_from_middle_frame(self):
        n = PNR_WINDOW_FRAMES
        mid = n // 2
        seq = make_pnr_sequence()
        result = detect_pick_and_roll(seq, game_id="g1")
        assert result[0].frame_number == mid

    def test_timestamp_from_middle_frame(self):
        n = PNR_WINDOW_FRAMES
        mid = n // 2
        seq = make_pnr_sequence()
        result = detect_pick_and_roll(seq, game_id="g1")
        assert result[0].timestamp_ms == pytest.approx(mid * 100.0)

    def test_no_pnr_when_players_never_close_enough(self):
        # Screen distance always > SCREEN_DISTANCE (6 ft)
        seq = make_pnr_sequence(screen_dist=SCREEN_DISTANCE + 2.0, sep_dist=SCREEN_DISTANCE + 4.0)
        result = detect_pick_and_roll(seq, game_id="g1")
        assert result == []

    def test_no_pnr_when_no_separation_at_end(self):
        # Players stay close — no separation in last frame (sep_dist <= SCREEN_DISTANCE)
        seq = make_pnr_sequence(screen_dist=4.0, sep_dist=5.0)
        result = detect_pick_and_roll(seq, game_id="g1")
        assert result == []

    def test_no_pnr_when_both_players_fast(self):
        # Both players fast (12 ft/s > SCREENER_MAX_SPEED=3) — no screener candidate
        n = PNR_WINDOW_FRAMES
        frames = []
        for i in range(n):
            p1 = make_player(1, 47.0, 25.0, 12.0, frame_number=i, timestamp_ms=float(i * 100))
            p2 = make_player(2, 50.0, 25.0, 12.0, frame_number=i, timestamp_ms=float(i * 100))
            frames.append([p1, p2])
        result = detect_pick_and_roll(frames, game_id="g1")
        assert result == []

    def test_no_pnr_when_both_players_slow(self):
        # Both players slow (2 ft/s < HANDLER_MIN_SPEED=8) — no ball handler candidate
        n = PNR_WINDOW_FRAMES
        frames = []
        for i in range(n):
            p1 = make_player(1, 47.0, 25.0, 2.0, frame_number=i, timestamp_ms=float(i * 100))
            p2 = make_player(2, 50.0, 25.0, 2.0, frame_number=i, timestamp_ms=float(i * 100))
            frames.append([p1, p2])
        result = detect_pick_and_roll(frames, game_id="g1")
        assert result == []


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_same_pair_deduplicated_within_window(self):
        # Even if conditions met in multiple frames, only one event per pair per window
        seq = make_pnr_sequence(handler_id=1, screener_id=2)
        result = detect_pick_and_roll(seq, game_id="g1")
        pairs = [(e.ball_handler_track_id, e.screener_track_id) for e in result]
        assert len(pairs) == len(set(pairs))

    def test_exact_window_frames_produces_at_most_one_event_per_pair(self):
        seq = make_pnr_sequence(handler_id=3, screener_id=4)
        result = detect_pick_and_roll(seq, game_id="g1")
        pairs = [(e.ball_handler_track_id, e.screener_track_id) for e in result]
        assert pairs.count((3, 4)) <= 1


# ---------------------------------------------------------------------------
# Multiple screener candidates
# ---------------------------------------------------------------------------

class TestMultipleScreeners:
    def test_closest_screener_selected(self):
        """When two slow players are near the handler, pick the closer one."""
        n = PNR_WINDOW_FRAMES
        frames = []
        for i in range(n):
            handler = make_player(1, 47.0, 25.0, 12.0, frame_number=i, timestamp_ms=float(i * 100))
            # screener A: 3 ft away (closer, within SCREEN_DISTANCE=6)
            screener_a = make_player(2, 50.0, 25.0, 2.0, frame_number=i, timestamp_ms=float(i * 100))
            # screener B: 6 ft away (at boundary of SCREEN_DISTANCE=6)
            screener_b = make_player(3, 53.0, 25.0, 2.0, frame_number=i, timestamp_ms=float(i * 100))
            if i == n - 1:
                # Separation: move handler 15 ft away from both screeners
                handler = make_player(1, 60.0, 25.0, 12.0, frame_number=i, timestamp_ms=float(i * 100))
            frames.append([handler, screener_a, screener_b])
        result = detect_pick_and_roll(frames, game_id="g1")
        assert len(result) >= 1
        # Closest screener (id=2) should be chosen
        assert result[0].screener_track_id == 2
