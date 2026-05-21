"""Tests for src/analytics/spatial_types.py

Covers instantiation, field values, and type contracts for all 7 dataclasses.
No external dependencies — pure dataclass assertions.
"""
from __future__ import annotations

import pytest

from src.analytics.spatial_types import (
    DefensivePressure,
    MomentumSnapshot,
    OffBallEvent,
    PassingEdge,
    PickAndRollEvent,
    SpacingMetrics,
)


class TestSpacingMetrics:
    def test_basic_construction(self) -> None:
        sm = SpacingMetrics(
            game_id="0022301234",
            possession_id="poss_001",
            frame_number=42,
            convex_hull_area=1250.5,
            avg_inter_player_distance=14.2,
            timestamp_ms=3600.0,
        )
        assert sm.game_id == "0022301234"
        assert sm.frame_number == 42
        assert sm.convex_hull_area == pytest.approx(1250.5)
        assert sm.avg_inter_player_distance == pytest.approx(14.2)

    def test_zero_spacing(self) -> None:
        sm = SpacingMetrics("g1", "p1", 0, 0.0, 0.0, 0.0)
        assert sm.convex_hull_area == 0.0
        assert sm.avg_inter_player_distance == 0.0

    def test_fields_are_mutable(self) -> None:
        sm = SpacingMetrics("g1", "p1", 1, 100.0, 10.0, 500.0)
        sm.convex_hull_area = 200.0
        assert sm.convex_hull_area == 200.0


class TestDefensivePressure:
    def test_basic_construction(self) -> None:
        dp = DefensivePressure(
            game_id="0022300001",
            track_id=7,
            frame_number=150,
            nearest_defender_distance=2.5,
            closing_speed=3.1,
            timestamp_ms=5000.0,
        )
        assert dp.track_id == 7
        assert dp.nearest_defender_distance == pytest.approx(2.5)
        assert dp.closing_speed == pytest.approx(3.1)

    def test_open_look(self) -> None:
        dp = DefensivePressure("g1", 1, 0, 15.0, 0.0, 0.0)
        assert dp.nearest_defender_distance == pytest.approx(15.0)
        assert dp.closing_speed == 0.0


class TestOffBallEvent:
    def test_cut_event(self) -> None:
        ev = OffBallEvent(
            game_id="g1",
            track_id=3,
            frame_number=200,
            event_type="cut",
            confidence=0.87,
            timestamp_ms=6700.0,
        )
        assert ev.event_type == "cut"
        assert 0.0 <= ev.confidence <= 1.0

    def test_screen_event(self) -> None:
        ev = OffBallEvent("g1", 5, 300, "screen", 0.92, 10000.0)
        assert ev.event_type == "screen"


class TestPickAndRollEvent:
    def test_construction(self) -> None:
        pr = PickAndRollEvent(
            game_id="g1",
            ball_handler_track_id=10,
            screener_track_id=5,
            frame_number=400,
            timestamp_ms=13333.0,
        )
        assert pr.ball_handler_track_id == 10
        assert pr.screener_track_id == 5
        assert pr.ball_handler_track_id != pr.screener_track_id

    def test_frame_positive(self) -> None:
        pr = PickAndRollEvent("g1", 1, 2, 0, 0.0)
        assert pr.frame_number == 0


class TestPassingEdge:
    def test_directed_edge(self) -> None:
        pe = PassingEdge(
            game_id="g1",
            possession_id="poss_003",
            from_track_id=1,
            to_track_id=4,
            count=3,
        )
        assert pe.from_track_id == 1
        assert pe.to_track_id == 4
        assert pe.count == 3
        assert pe.from_track_id != pe.to_track_id

    def test_count_accumulation(self) -> None:
        pe = PassingEdge("g1", "p1", 2, 3, 1)
        pe.count += 1
        assert pe.count == 2


class TestMomentumSnapshot:
    def test_construction(self) -> None:
        ms = MomentumSnapshot(
            game_id="g1",
            segment_id=4,
            scoring_run=3,
            possession_streak=2,
            swing_point=True,
            timestamp_ms=9000.0,
        )
        assert ms.segment_id == 4
        assert ms.scoring_run == 3
        assert ms.swing_point is True

    def test_no_swing(self) -> None:
        ms = MomentumSnapshot("g1", 0, 0, 0, False, 0.0)
        assert ms.swing_point is False
        assert ms.scoring_run == 0
