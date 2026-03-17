"""Tests for features/spacing.py — Player Spacing Metrics (FE-01).

TDD RED phase: tests written before implementation.
All tests verify the behavior spec in the plan.
"""
import math
import pytest
from features.spacing import compute_spacing
from features.types import SpacingMetrics


GAME_ID = "game-001"
POSSESSION_ID = "poss-001"
FRAME = 42
TS = 1400.0


# ── Happy-path geometric fixtures ──────────────────────────────────────────

def test_square_four_corners_hull_area():
    """Square with side 10 → convex hull area = 100.0."""
    positions = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert isinstance(result, SpacingMetrics)
    assert abs(result.convex_hull_area - 100.0) < 1e-6


def test_five_player_avg_distance():
    """Five players in a known configuration — avg distance matches hand-computed value."""
    positions = [(0.0, 0.0), (3.0, 4.0), (6.0, 0.0), (3.0, 0.0), (0.0, 4.0)]
    # Hand-compute all pairwise distances:
    pairs = [
        (0, 1), (0, 2), (0, 3), (0, 4),
        (1, 2), (1, 3), (1, 4),
        (2, 3), (2, 4),
        (3, 4),
    ]
    dists = [math.hypot(positions[i][0] - positions[j][0],
                        positions[i][1] - positions[j][1])
             for i, j in pairs]
    expected_avg = sum(dists) / len(dists)

    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert abs(result.avg_inter_player_distance - expected_avg) < 1e-6


# ── Degenerate inputs ──────────────────────────────────────────────────────

def test_two_points_hull_area_is_zero():
    """Fewer than 3 players → hull area = 0.0."""
    positions = [(0.0, 0.0), (3.0, 4.0)]
    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert result.convex_hull_area == 0.0


def test_two_points_avg_distance_is_distance_between_them():
    """Two players → avg_inter_player_distance is the Euclidean distance between them."""
    positions = [(0.0, 0.0), (3.0, 4.0)]
    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert abs(result.avg_inter_player_distance - 5.0) < 1e-6


def test_single_point_both_metrics_zero():
    """One player → both metrics = 0.0."""
    positions = [(5.0, 7.0)]
    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert result.convex_hull_area == 0.0
    assert result.avg_inter_player_distance == 0.0


def test_empty_list_both_metrics_zero():
    """No players → both metrics = 0.0."""
    result = compute_spacing([], GAME_ID, POSSESSION_ID, FRAME, TS)
    assert result.convex_hull_area == 0.0
    assert result.avg_inter_player_distance == 0.0


def test_collinear_points_hull_area_is_zero():
    """Collinear players → QhullError caught; hull area = 0.0."""
    positions = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    result = compute_spacing(positions, GAME_ID, POSSESSION_ID, FRAME, TS)
    assert result.convex_hull_area == 0.0


# ── Metadata pass-through ─────────────────────────────────────────────────

def test_metadata_passthrough():
    """game_id, possession_id, frame_number, timestamp_ms pass through unchanged."""
    positions = [(0.0, 0.0), (10.0, 0.0), (5.0, 8.0)]
    result = compute_spacing(positions, "g-99", "p-77", 7, 9999.5)
    assert result.game_id == "g-99"
    assert result.possession_id == "p-77"
    assert result.frame_number == 7
    assert result.timestamp_ms == 9999.5


def test_returns_spacing_metrics_type():
    """compute_spacing always returns SpacingMetrics instance."""
    result = compute_spacing([(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)], GAME_ID, POSSESSION_ID, FRAME, TS)
    assert isinstance(result, SpacingMetrics)
