"""
test_garbage_time_2h.py -- Tests for garbage-time -> 2H model wiring (19.5-04).

Acceptance criterion: garbage_time_detector emits a blowout signal that routes
to second_half_adjustment_model, which produces 2H prop bets; an integration
test confirms the signal flow end-to-end.
"""

from __future__ import annotations

import os
import sys

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.garbage_time_detector import (  # noqa: E402
    detect_blowout,
    route_blowout_to_second_half,
)
from src.prediction.second_half_adjustment_model import produce_2h_prop_bets  # noqa: E402


def _players() -> list:
    return [
        {"player_id": 1, "player_name": "Lead Starter", "team": "BOS", "role": "starter"},
        {"player_id": 2, "player_name": "Lead Bench", "team": "BOS", "role": "bench"},
        {"player_id": 3, "player_name": "Trail Starter", "team": "NYK", "role": "starter"},
        {"player_id": 4, "player_name": "Bystander", "team": "LAL", "role": "starter"},
    ]


# ── detect_blowout ────────────────────────────────────────────────────────────

def test_blowout_detected_on_large_late_margin():
    """A 22-pt margin with 14 min left fires a blowout signal."""
    signal = detect_blowout({
        "point_differential": 22.0, "period": 3, "minutes_remaining": 14.0,
        "leading_team": "BOS", "trailing_team": "NYK",
    })
    assert signal is not None
    assert signal["event"] == "BLOWOUT"
    assert signal["leading_team"] == "BOS"


def test_no_blowout_when_margin_small():
    """An 8-pt margin is not a blowout regardless of time."""
    assert detect_blowout({
        "point_differential": 8.0, "period": 3, "minutes_remaining": 14.0,
    }) is None


def test_no_blowout_early_in_game():
    """A big margin with most of the game left does not yet qualify."""
    assert detect_blowout({
        "point_differential": 22.0, "period": 1, "minutes_remaining": 40.0,
    }) is None


def test_leading_team_derived_from_scores():
    """leading/trailing teams are derived from team names + scores."""
    signal = detect_blowout({
        "point_differential": 25.0, "period": 4, "minutes_remaining": 8.0,
        "home_team": "BOS", "away_team": "NYK",
        "home_score": 110, "away_score": 85,
    })
    assert signal["leading_team"] == "BOS"
    assert signal["trailing_team"] == "NYK"


# ── produce_2h_prop_bets ──────────────────────────────────────────────────────

def test_starters_get_under_bench_gets_over():
    """In a blowout, starters get 2H alt-under and bench gets 2H alt-over."""
    signal = {"event": "BLOWOUT", "point_differential": 22.0,
              "leading_team": "BOS", "trailing_team": "NYK"}
    bets = produce_2h_prop_bets(signal, _players())
    by_id = {b["player_id"]: b for b in bets}
    assert by_id[1]["recommendation"] == "alt_under"   # leading starter
    assert by_id[2]["recommendation"] == "alt_over"    # leading bench
    assert by_id[3]["recommendation"] == "alt_under"   # trailing starter
    assert all(b["half"] == "2H" for b in bets)
    assert 4 not in by_id   # uninvolved team excluded


def test_no_bets_without_blowout_signal():
    """produce_2h_prop_bets returns [] for a non-blowout signal."""
    assert produce_2h_prop_bets({}, _players()) == []
    assert produce_2h_prop_bets({"event": "OTHER"}, _players()) == []


# ── end-to-end signal flow ────────────────────────────────────────────────────

def test_end_to_end_blowout_routes_to_2h_bets():
    """Integration: a blowout game state routes through to 2H prop bets."""
    game_state = {
        "point_differential": 24.0, "period": 3, "minutes_remaining": 12.0,
        "leading_team": "BOS", "trailing_team": "NYK",
    }
    bets = route_blowout_to_second_half(game_state, _players())
    assert len(bets) == 3            # BOS x2 + NYK x1, LAL excluded
    assert {b["recommendation"] for b in bets} == {"alt_under", "alt_over"}


def test_end_to_end_no_blowout_no_bets():
    """A non-blowout game state routes to an empty bet list."""
    game_state = {"point_differential": 6.0, "period": 3, "minutes_remaining": 12.0}
    assert route_blowout_to_second_half(game_state, _players()) == []


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
