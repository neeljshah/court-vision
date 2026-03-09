"""Tests for features/defensive_pressure.py — Defensive Pressure Metrics (FE-02).

TDD RED phase: tests written before implementation.
All tests verify the behavior spec in the plan.
"""
import math
import pytest
from features.defensive_pressure import compute_defensive_pressure
from features.types import DefensivePressure


GAME_ID = "game-001"
FRAME = 42
TS = 1400.0


def _make_row(track_id: int, x: float, y: float, team: str | None) -> dict:
    return {"track_id": track_id, "x": x, "y": y, "team": team}


# ── Basic distance computation ────────────────────────────────────────────

def test_nearest_defender_distance_basic():
    """Offensive player at (0,0), defenders at (3,4) and (10,0) → nearest = 5.0."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 3.0, 4.0, "defense"),
        _make_row(3, 10.0, 0.0, "defense"),
    ]
    prev = {}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    # Only offensive player should appear in results
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, DefensivePressure)
    assert r.track_id == 1
    assert abs(r.nearest_defender_distance - 5.0) < 1e-6


def test_nearest_defender_distance_multiple_offensive():
    """Two offensive players each get their own nearest defender distance."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 10.0, 0.0, "offense"),
        _make_row(3, 1.0, 0.0, "defense"),   # nearest to player 1
        _make_row(4, 9.0, 0.0, "defense"),   # nearest to player 2
    ]
    prev = {}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert len(results) == 2
    by_track = {r.track_id: r for r in results}
    assert abs(by_track[1].nearest_defender_distance - 1.0) < 1e-6
    assert abs(by_track[2].nearest_defender_distance - 1.0) < 1e-6


# ── Closing speed ────────────────────────────────────────────────────────

def test_closing_speed_negative_when_closing():
    """Previous distance 8.0, current 5.0 → closing_speed = -3.0."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 3.0, 4.0, "defense"),
    ]
    prev = {1: 8.0}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert len(results) == 1
    assert abs(results[0].closing_speed - (-3.0)) < 1e-6


def test_closing_speed_positive_when_opening():
    """Previous distance 3.0, current 5.0 → closing_speed = 2.0."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 3.0, 4.0, "defense"),
    ]
    prev = {1: 3.0}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert len(results) == 1
    assert abs(results[0].closing_speed - 2.0) < 1e-6


def test_closing_speed_zero_on_first_frame():
    """No previous distance → closing_speed = 0.0."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 3.0, 4.0, "defense"),
    ]
    prev = {}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert len(results) == 1
    assert results[0].closing_speed == 0.0


# ── Empty / degenerate ───────────────────────────────────────────────────

def test_empty_defender_list():
    """No defenders → nearest_defender_distance = inf, closing_speed = 0.0."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
    ]
    prev = {}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert len(results) == 1
    assert results[0].nearest_defender_distance == float("inf")
    assert results[0].closing_speed == 0.0


def test_empty_player_rows_returns_empty_list():
    """Empty row list → empty result list."""
    prev = {}
    results = compute_defensive_pressure([], GAME_ID, FRAME, TS, prev)
    assert results == []


# ── prev_distances mutation ───────────────────────────────────────────────

def test_prev_distances_mutated_after_call():
    """prev_distances dict is updated in place with new distances."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 3.0, 4.0, "defense"),
    ]
    prev = {}
    compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    assert 1 in prev
    assert abs(prev[1] - 5.0) < 1e-6


# ── team=None fallback ───────────────────────────────────────────────────

def test_team_none_uses_all_others_as_defenders():
    """When team is None for all, every player is pressured by all others."""
    rows = [
        _make_row(1, 0.0, 0.0, None),
        _make_row(2, 3.0, 4.0, None),
        _make_row(3, 10.0, 0.0, None),
    ]
    prev = {}
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, prev)
    # All three should appear in results
    assert len(results) == 3
    by_track = {r.track_id: r for r in results}
    # Player 1 nearest is player 2 at distance 5.0
    assert abs(by_track[1].nearest_defender_distance - 5.0) < 1e-6


# ── Metadata pass-through ─────────────────────────────────────────────────

def test_metadata_passthrough():
    """game_id, frame_number, timestamp_ms pass through correctly."""
    rows = [
        _make_row(7, 0.0, 0.0, "offense"),
        _make_row(8, 1.0, 0.0, "defense"),
    ]
    prev = {}
    results = compute_defensive_pressure(rows, "g-42", 99, 8888.0, prev)
    assert len(results) == 1
    r = results[0]
    assert r.game_id == "g-42"
    assert r.frame_number == 99
    assert r.timestamp_ms == 8888.0


def test_returns_defensive_pressure_type():
    """Each result is a DefensivePressure instance."""
    rows = [
        _make_row(1, 0.0, 0.0, "offense"),
        _make_row(2, 5.0, 0.0, "defense"),
    ]
    results = compute_defensive_pressure(rows, GAME_ID, FRAME, TS, {})
    assert all(isinstance(r, DefensivePressure) for r in results)
