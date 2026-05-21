"""Tests for src/analytics/momentum_events.py

Covers:
  - compute_momentum: empty input, single segment, multi-segment
  - scoring_run calculation
  - possession_streak calculation
  - swing_point detection across segments
  - output types and ordering
"""
from __future__ import annotations

import pytest

from src.analytics.momentum_events import compute_momentum
from src.analytics.spatial_types import MomentumSnapshot


def _ev(team: str, made: bool, possession_num: int, ts: float = 0.0) -> dict:
    return {"team": team, "made": made, "possession_num": possession_num,
            "timestamp_ms": ts, "game_id": "test_game"}


class TestComputeMomentumEmpty:
    def test_empty_returns_empty_list(self) -> None:
        result = compute_momentum([], game_id="g1")
        assert result == []

    def test_no_made_shots(self) -> None:
        events = [_ev("home", False, 0), _ev("away", False, 1)]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert isinstance(result, list)
        assert all(isinstance(s, MomentumSnapshot) for s in result)


class TestScoringRun:
    def test_consecutive_made_shots_same_team(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("home", True, 1, 2.0),
            _ev("home", True, 2, 3.0),
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        assert len(result) == 1
        assert result[0].scoring_run == 3

    def test_run_resets_on_miss(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("home", True, 1, 2.0),
            _ev("home", False, 2, 3.0),  # miss resets run
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        assert result[0].scoring_run == 0

    def test_run_resets_on_opponent_score(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("away", True, 1, 2.0),  # opponent scores → resets home run
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        assert result[0].scoring_run == 1  # away is now on a run of 1

    def test_mixed_team_alternating(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("away", True, 1, 2.0),
            _ev("home", True, 2, 3.0),
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        # Final streak is home scoring → run = 1
        assert result[0].scoring_run == 1


class TestPossessionStreak:
    def test_same_team_consecutive_possessions(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("home", True, 1, 2.0),
            _ev("home", True, 2, 3.0),
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        assert result[0].possession_streak == 3

    def test_alternating_possessions(self) -> None:
        events = [
            _ev("home", True, 0, 1.0),
            _ev("away", True, 1, 2.0),
            _ev("home", True, 2, 3.0),
            _ev("away", True, 3, 4.0),
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        # Max consecutive = 1
        assert result[0].possession_streak == 1


class TestMultipleSegments:
    def test_multiple_segments_returned(self) -> None:
        events = [_ev("home", True, i, float(i)) for i in range(10)]
        # With segment_size=5, should produce 2 segments (poss 0-4 → seg 0, 5-9 → seg 1)
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert len(result) == 2

    def test_segments_sorted_by_id(self) -> None:
        events = [_ev("home", True, i, float(i)) for i in range(15)]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        seg_ids = [s.segment_id for s in result]
        assert seg_ids == sorted(seg_ids)

    def test_game_id_propagated(self) -> None:
        events = [_ev("home", True, 0, 1.0)]
        result = compute_momentum(events, game_id="GAME_XYZ")
        assert result[0].game_id == "GAME_XYZ"


class TestSwingPoint:
    def test_first_segment_never_swing(self) -> None:
        events = [_ev("home", True, 0, 1.0), _ev("home", True, 1, 2.0)]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert result[0].swing_point is False

    def test_swing_detected_when_leader_changes(self) -> None:
        # Seg 0: home dominates; seg 1: away dominates → swing
        seg0 = [_ev("home", True, i, float(i)) for i in range(5)]
        seg1 = [_ev("away", True, i, float(i)) for i in range(5, 10)]
        result = compute_momentum(seg0 + seg1, game_id="g1", segment_size_possessions=5)
        assert len(result) == 2
        # The second segment should be a swing point
        assert result[1].swing_point is True

    def test_no_swing_when_same_leader(self) -> None:
        # Home leads both segments
        events = [_ev("home", True, i, float(i)) for i in range(10)]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=5)
        assert result[1].swing_point is False


class TestOutputShape:
    def test_result_is_list_of_snapshots(self) -> None:
        events = [_ev("home", True, 0, 1.0)]
        result = compute_momentum(events, game_id="g1")
        assert isinstance(result, list)
        assert all(isinstance(s, MomentumSnapshot) for s in result)

    def test_timestamp_taken_from_last_event_in_segment(self) -> None:
        events = [
            _ev("home", True, 0, 100.0),
            _ev("home", True, 1, 200.0),
        ]
        result = compute_momentum(events, game_id="g1", segment_size_possessions=10)
        assert result[0].timestamp_ms == pytest.approx(200.0)
