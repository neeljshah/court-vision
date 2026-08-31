"""Focused tests for NBA screen-candidate detection."""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.tracking.screens import detect_screens, per_game_counts


def _tracks(moving_screener: bool = False) -> pd.DataFrame:
    rows = []
    for frame in range(12):
        screener_x = 43.0 + (frame if moving_screener else 0.0)
        if not moving_screener and frame < 2:
            screener_x = 50.0
        rows.extend([
            {"game_id": "game-1", "frame": frame, "player_id": "handler", "team_id": "A",
             "ft_x": 40.0, "ft_y": 25.0, "has_possession": True},
            {"game_id": "game-1", "frame": frame, "player_id": "screener", "team_id": "A",
             "ft_x": screener_x, "ft_y": 25.0},
            {"game_id": "game-1", "frame": frame, "player_id": "defender", "team_id": "B",
             "ft_x": 41.0, "ft_y": 25.0},
        ])
    return pd.DataFrame(rows)


def test_engineered_stationary_convergence_is_detected_once() -> None:
    events = detect_screens(_tracks())
    assert events[["handler_id", "screener_id"]].to_dict("records") == [
        {"handler_id": "handler", "screener_id": "screener"}
    ]
    assert events.iloc[0]["frame"] == 3
    assert per_game_counts(events).iloc[0]["screen_candidate_count"] == 1


def test_moving_pair_is_not_a_screen_candidate() -> None:
    events = detect_screens(_tracks(moving_screener=True))
    assert events.empty
