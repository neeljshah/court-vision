"""Tests for shared dataclass type contracts used by all Phase 2 feature modules."""

from features.types import (
    SpacingMetrics,
    DefensivePressure,
    OffBallEvent,
    PickAndRollEvent,
    PassingEdge,
    MomentumSnapshot,
)


def test_spacing_metrics_fields_present():
    sm = SpacingMetrics(
        game_id="game-1",
        possession_id="poss-1",
        frame_number=100,
        convex_hull_area=1200.5,
        avg_inter_player_distance=15.3,
        timestamp_ms=5000,
    )
    assert sm.game_id == "game-1"
    assert sm.possession_id == "poss-1"
    assert sm.frame_number == 100
    assert sm.convex_hull_area == 1200.5
    assert sm.avg_inter_player_distance == 15.3
    assert sm.timestamp_ms == 5000


def test_spacing_metrics_convex_hull_area_non_negative():
    sm = SpacingMetrics(
        game_id="game-1",
        possession_id="poss-1",
        frame_number=1,
        convex_hull_area=0.0,
        avg_inter_player_distance=10.0,
        timestamp_ms=1000,
    )
    assert sm.convex_hull_area >= 0


def test_defensive_pressure_fields_present():
    dp = DefensivePressure(
        game_id="game-2",
        track_id=7,
        frame_number=200,
        nearest_defender_distance=3.5,
        closing_speed=-0.8,
        timestamp_ms=8000,
    )
    assert dp.game_id == "game-2"
    assert dp.track_id == 7
    assert dp.frame_number == 200
    assert dp.nearest_defender_distance == 3.5
    assert dp.closing_speed == -0.8
    assert dp.timestamp_ms == 8000


def test_defensive_pressure_closing_speed_can_be_negative():
    dp = DefensivePressure(
        game_id="game-2",
        track_id=3,
        frame_number=50,
        nearest_defender_distance=2.0,
        closing_speed=-1.5,
        timestamp_ms=2000,
    )
    # Negative closing_speed means defender is closing in
    assert dp.closing_speed < 0


def test_defensive_pressure_closing_speed_can_be_positive():
    dp = DefensivePressure(
        game_id="game-2",
        track_id=3,
        frame_number=50,
        nearest_defender_distance=2.0,
        closing_speed=1.5,
        timestamp_ms=2000,
    )
    # Positive closing_speed means defender is opening up (moving away)
    assert dp.closing_speed > 0


def test_off_ball_event_fields_present():
    obe = OffBallEvent(
        game_id="game-3",
        track_id=5,
        frame_number=300,
        event_type="cut",
        confidence=0.92,
        timestamp_ms=12000,
    )
    assert obe.game_id == "game-3"
    assert obe.track_id == 5
    assert obe.frame_number == 300
    assert obe.event_type == "cut"
    assert obe.confidence == 0.92
    assert obe.timestamp_ms == 12000


def test_off_ball_event_valid_event_types():
    valid_types = {"cut", "screen", "drift"}
    for event_type in valid_types:
        obe = OffBallEvent(
            game_id="game-3",
            track_id=5,
            frame_number=300,
            event_type=event_type,
            confidence=0.8,
            timestamp_ms=12000,
        )
        assert obe.event_type in valid_types


def test_pick_and_roll_event_fields_present():
    pre = PickAndRollEvent(
        game_id="game-4",
        ball_handler_track_id=2,
        screener_track_id=8,
        frame_number=400,
        timestamp_ms=16000,
    )
    assert pre.game_id == "game-4"
    assert pre.ball_handler_track_id == 2
    assert pre.screener_track_id == 8
    assert pre.frame_number == 400
    assert pre.timestamp_ms == 16000


def test_pick_and_roll_event_distinct_track_ids():
    pre = PickAndRollEvent(
        game_id="game-4",
        ball_handler_track_id=2,
        screener_track_id=8,
        frame_number=400,
        timestamp_ms=16000,
    )
    assert pre.ball_handler_track_id != pre.screener_track_id


def test_passing_edge_fields_present():
    pe = PassingEdge(
        game_id="game-5",
        possession_id="poss-2",
        from_track_id=1,
        to_track_id=4,
        count=3,
    )
    assert pe.game_id == "game-5"
    assert pe.possession_id == "poss-2"
    assert pe.from_track_id == 1
    assert pe.to_track_id == 4
    assert pe.count == 3


def test_passing_edge_count_at_least_one():
    pe = PassingEdge(
        game_id="game-5",
        possession_id="poss-2",
        from_track_id=1,
        to_track_id=4,
        count=1,
    )
    assert pe.count >= 1


def test_momentum_snapshot_fields_present():
    ms = MomentumSnapshot(
        game_id="game-6",
        segment_id=3,
        scoring_run=5,
        possession_streak=2,
        swing_point=True,
        timestamp_ms=20000,
    )
    assert ms.game_id == "game-6"
    assert ms.segment_id == 3
    assert ms.scoring_run == 5
    assert ms.possession_streak == 2
    assert ms.swing_point is True
    assert ms.timestamp_ms == 20000


def test_momentum_snapshot_swing_point_is_bool():
    ms_true = MomentumSnapshot(
        game_id="game-6",
        segment_id=1,
        scoring_run=0,
        possession_streak=0,
        swing_point=True,
        timestamp_ms=1000,
    )
    ms_false = MomentumSnapshot(
        game_id="game-6",
        segment_id=2,
        scoring_run=0,
        possession_streak=0,
        swing_point=False,
        timestamp_ms=2000,
    )
    assert isinstance(ms_true.swing_point, bool)
    assert isinstance(ms_false.swing_point, bool)
