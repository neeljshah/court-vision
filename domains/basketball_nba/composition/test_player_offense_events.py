"""Per-file test: composition/player_offense_events.py -- clutch definition
edge cases (pure function, no disk I/O) + a zone-classification reuse smoke
test on a tiny synthetic game.

Run: python -m pytest domains/basketball_nba/composition/test_player_offense_events.py -q
"""
from __future__ import annotations

from domains.basketball_nba.composition.player_offense_events import (
    is_clutch_row, load_game_events,
)
from domains.basketball_nba.composition.zone_geometry import ZONES


def test_clutch_boundary_inclusive():
    assert is_clutch_row(period=4, remaining_s=300.0, margin=10.0) is True


def test_clutch_period3_never_clutch():
    assert is_clutch_row(period=3, remaining_s=10.0, margin=1.0) is False


def test_clutch_remaining_over_5min_excluded():
    assert is_clutch_row(period=4, remaining_s=301.0, margin=0.0) is False


def test_clutch_margin_over_10_excluded():
    assert is_clutch_row(period=4, remaining_s=100.0, margin=11.0) is False


def test_clutch_ot_counts():
    assert is_clutch_row(period=5, remaining_s=200.0, margin=5.0) is True


def test_clutch_none_inputs_excluded():
    assert is_clutch_row(period=4, remaining_s=None, margin=5.0) is False
    assert is_clutch_row(period=4, remaining_s=200.0, margin=None) is False


def _synthetic_game(actions):
    return {"game": {"gameId": "0099900001", "actions": actions}}


def test_load_game_events_zone_classification_reuse():
    """A near-basket shot and a corner three both classify via the SAME
    classify_zone reused from zone_geometry.py -- not a reimplementation."""
    actions = [
        {
            "actionNumber": 1, "period": 1, "clock": "PT11M12.00S", "teamId": 1, "personId": 100,
            "actionType": "2pt", "x": 5.0, "y": 50.0, "shotResult": "Made", "description": "makes shot",
            "scoreHome": "2", "scoreAway": "0",
        },
        {
            "actionNumber": 2, "period": 1, "clock": "PT10M50.00S", "teamId": 2, "personId": 200,
            "actionType": "3pt", "x": 5.0, "y": 3.0, "shotResult": "Made", "description": "makes 3pt shot",
            "scoreHome": "2", "scoreAway": "3",
        },
    ]
    df = load_game_events(_synthetic_game(actions))
    assert set(df["zone"].dropna().unique()) <= set(ZONES)
    assert (df["zone"] == "rim").any()
    assert (df["zone"] == "corner3").any()
