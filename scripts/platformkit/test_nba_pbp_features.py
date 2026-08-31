"""Synthetic tests for NBA PBP-only team-game features."""
import pandas as pd

from scripts.platformkit.nba_pbp_features import build_asof_features, estimate_possessions


def test_boxscore_possessions_are_exact_and_asof_is_shifted():
    rows = pd.DataFrame([
        {"game_id": "g1", "game_date": "2025-01-01", "team_id": "A", "opponent_id": "B", "fga": 80, "fta": 20, "orb": 10, "tov": 12, "stl": 8},
        {"game_id": "g2", "game_date": "2025-01-03", "team_id": "A", "opponent_id": "C", "fga": 90, "fta": 10, "orb": 8, "tov": 11, "stl": 7},
        {"game_id": "g3", "game_date": "2025-01-04", "team_id": "A", "opponent_id": "D", "fga": 70, "fta": 30, "orb": 12, "tov": 9, "stl": 6},
    ])
    features, available = build_asof_features(rows)
    first, second, third = features.to_dict("records")
    assert estimate_possessions(80, 20, 10, 12) == 90.0
    assert first["pace_proxy"] == 90.0
    assert pd.isna(first["pace_l5_asof"])
    assert second["pace_l5_asof"] == 90.0
    assert third["pace_l5_asof"] == (90.0 + 97.0) / 2
    assert second["rest_days_asof"] == 2.0 and third["b2b_asof"] == 1
    assert available["transition_proxy"] is True
