"""Tests for features/momentum.py.

Tests cover:
- Scoring run computation (consecutive points by same team)
- Possession streak computation (consecutive possessions won)
- Swing point detection (lead change between segments)
- Segment grouping by possession_num // segment_size_possessions
- Edge cases: empty list, single segment, segment count
"""

import math
import pytest
from features.momentum import compute_momentum
from features.types import MomentumSnapshot


GAME_ID = "game-bbb"


def make_shot(team: str, made: bool, possession_num: int, timestamp_ms: float = 1000.0) -> dict:
    return {
        "team": team,
        "made": made,
        "possession_num": possession_num,
        "timestamp_ms": timestamp_ms,
        "game_id": GAME_ID,
    }


# ---------------------------------------------------------------------------
# Return type and structure
# ---------------------------------------------------------------------------

class TestComputeMomentumReturnType:

    def test_returns_list(self):
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID)
        assert isinstance(result, list)

    def test_returns_momentum_snapshots(self):
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID)
        for s in result:
            assert isinstance(s, MomentumSnapshot)

    def test_empty_returns_empty(self):
        """Empty shot list → returns []."""
        result = compute_momentum([], GAME_ID)
        assert result == []

    def test_sorted_by_segment_id(self):
        """Result is sorted by segment_id ascending."""
        shots = [make_shot("A", True, i) for i in range(15)]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        ids = [s.segment_id for s in result]
        assert ids == sorted(ids)

    def test_segment_id_is_zero_based(self):
        """segment_id starts at 0."""
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID)
        assert result[0].segment_id == 0


# ---------------------------------------------------------------------------
# Segment counting
# ---------------------------------------------------------------------------

class TestSegmentCounting:

    def test_twelve_possessions_five_per_segment_yields_three_segments(self):
        """12 possessions → ceil(12/5) = 3 segments (0..4, 5..9, 10..11)."""
        shots = [make_shot("A", True, i) for i in range(12)]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert len(result) == 3

    def test_five_possessions_five_per_segment_yields_one_segment(self):
        shots = [make_shot("A", True, i) for i in range(5)]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert len(result) == 1

    def test_ten_possessions_five_per_segment_yields_two_segments(self):
        shots = [make_shot("A", True, i) for i in range(10)]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert len(result) == 2

    def test_one_possession_returns_one_segment(self):
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert len(result) == 1

    def test_game_id_propagated(self):
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID)
        assert result[0].game_id == GAME_ID


# ---------------------------------------------------------------------------
# Scoring run
# ---------------------------------------------------------------------------

class TestScoringRun:

    def test_three_made_by_same_team_scoring_run_3(self):
        """Three made shots by team A in same segment → scoring_run=3."""
        shots = [
            make_shot("A", True, 0),
            make_shot("A", True, 1),
            make_shot("A", True, 2),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert result[0].scoring_run == 3

    def test_scoring_run_resets_on_different_team_score(self):
        """scoring_run resets to 0 when a different team scores."""
        shots = [
            make_shot("A", True, 0),
            make_shot("A", True, 1),
            make_shot("B", True, 2),  # B scores → run resets
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        # run should reflect final run by B: 1
        assert result[0].scoring_run == 1

    def test_missed_shots_not_counted_in_run(self):
        """Missed shots do not contribute to scoring run."""
        shots = [
            make_shot("A", False, 0),
            make_shot("A", False, 1),
            make_shot("A", True, 2),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        # Only 1 consecutive made shot by A at end
        assert result[0].scoring_run == 1

    def test_alternating_teams_no_run(self):
        """A,B,A,B alternating → each run length is 1."""
        shots = [
            make_shot("A", True, 0),
            make_shot("B", True, 1),
            make_shot("A", True, 2),
            make_shot("B", True, 3),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert result[0].scoring_run == 1

    def test_scoring_run_zero_if_no_made_shots(self):
        """Segment with only missed shots → scoring_run=0."""
        shots = [
            make_shot("A", False, 0),
            make_shot("B", False, 1),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert result[0].scoring_run == 0


# ---------------------------------------------------------------------------
# Possession streak
# ---------------------------------------------------------------------------

class TestPossessionStreak:

    def test_three_consecutive_possessions_by_same_team(self):
        """Three made shots by A in same segment → possession_streak=3."""
        shots = [
            make_shot("A", True, 0),
            make_shot("A", True, 1),
            make_shot("A", True, 2),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert result[0].possession_streak == 3

    def test_possession_streak_breaks_when_other_team_scores(self):
        """A,A,B,A streak — B breaks A's streak; longest is 2 for A."""
        shots = [
            make_shot("A", True, 0),
            make_shot("A", True, 1),
            make_shot("B", True, 2),
            make_shot("A", True, 3),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        # max streak = 2 (A,A)
        assert result[0].possession_streak == 2


# ---------------------------------------------------------------------------
# Swing point
# ---------------------------------------------------------------------------

class TestSwingPoint:

    def test_no_swing_when_same_team_leads_both_segments(self):
        """A leads in both segments → swing_point=False in second segment."""
        shots_seg0 = [make_shot("A", True, i, 1000.0 * i) for i in range(5)]
        shots_seg1 = [make_shot("A", True, 5 + i, 2000.0 + 1000.0 * i) for i in range(5)]
        result = compute_momentum(shots_seg0 + shots_seg1, GAME_ID, segment_size_possessions=5)
        assert len(result) == 2
        # First segment has no previous → swing_point=False
        assert result[0].swing_point is False
        # Second segment: A leads both → no swing
        assert result[1].swing_point is False

    def test_swing_when_lead_changes_between_segments(self):
        """A leads in seg0, B leads in seg1 → swing_point=True in seg1."""
        shots_seg0 = [make_shot("A", True, i) for i in range(5)]
        shots_seg1 = [
            make_shot("B", True, 5),
            make_shot("B", True, 6),
            make_shot("B", True, 7),
            make_shot("B", True, 8),
            make_shot("A", False, 9),  # A misses — B still leads
        ]
        result = compute_momentum(shots_seg0 + shots_seg1, GAME_ID, segment_size_possessions=5)
        assert len(result) == 2
        assert result[0].swing_point is False
        assert result[1].swing_point is True

    def test_first_segment_always_no_swing(self):
        """First segment has no predecessor → swing_point=False."""
        shots = [make_shot("A", True, 0)]
        result = compute_momentum(shots, GAME_ID)
        assert result[0].swing_point is False

    def test_tied_segment_no_swing(self):
        """If both teams score equally → no clear leader change → swing_point=False."""
        shots_seg0 = [make_shot("A", True, i) for i in range(3)]  # A leads seg0
        shots_seg1 = [
            make_shot("A", True, 5),
            make_shot("B", True, 6),  # tie in seg1
        ]
        result = compute_momentum(shots_seg0 + shots_seg1, GAME_ID, segment_size_possessions=5)
        # seg1 is tied: no clear leader change from A → no swing
        assert result[1].swing_point is False


# ---------------------------------------------------------------------------
# Timestamp
# ---------------------------------------------------------------------------

class TestTimestamp:

    def test_timestamp_is_last_event_in_segment(self):
        """timestamp_ms = timestamp_ms of last event in segment."""
        shots = [
            make_shot("A", True, 0, timestamp_ms=100.0),
            make_shot("A", True, 1, timestamp_ms=200.0),
            make_shot("A", True, 2, timestamp_ms=350.0),
        ]
        result = compute_momentum(shots, GAME_ID, segment_size_possessions=5)
        assert result[0].timestamp_ms == 350.0
