"""Per-file test for knowledge.validate_research_wave5. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/knowledge/test_validate_research_wave5.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.basketball_nba.knowledge import validate_research_wave5 as vrw5


def test_self_check():
    vrw5._self_check()


def test_build_team_game_frame_computes_opening_lineup_and_point_diff():
    stints = pd.DataFrame([
        {"game_id": "g1", "team_id": 1, "period": 1, "lineup_key": "A", "start_s": 0.0, "pts_for": 10, "pts_against": 4},
        {"game_id": "g1", "team_id": 1, "period": 1, "lineup_key": "B", "start_s": 100.0, "pts_for": 2, "pts_against": 1},
        {"game_id": "g1", "team_id": 1, "period": 2, "lineup_key": "A", "start_s": 0.0, "pts_for": 5, "pts_against": 3},
    ])
    tg = vrw5.build_team_game_frame(stints)
    assert len(tg) == 1
    row = tg.iloc[0]
    assert row["lineup_key"] == "A"  # earliest period-1 stint by start_s
    assert row["point_diff"] == (10 + 2 + 5) - (4 + 1 + 3)


def test_streak_within_team_counts_consecutive_prior_identical():
    s = pd.Series(["A", "A", "A", "B", "B"])
    assert vrw5._streak_within_team(s).tolist() == [0, 1, 2, 0, 1]


def test_add_continuity_streak_sorts_per_team_by_game_id():
    tg = pd.DataFrame({
        "game_id": ["g2", "g1", "g3"], "team_id": [1, 1, 1],
        "lineup_key": ["A", "A", "B"], "point_diff": [1, 2, 3]})
    out = vrw5.add_continuity_streak(tg).sort_values("game_id")
    # chronological order g1,g2,g3 -> lineup A,A,B -> streak 0,1,0
    assert out["continuity_streak"].tolist() == [0, 1, 0]


def test_combine_needs_both_seasons_same_sign():
    confirmed = {"hypothesis": "x__a", "n": 100, "effect": 0.1, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    out = vrw5._combine([confirmed, dict(confirmed, hypothesis="x__b")])
    assert out["verdict"] == "CONFIRMED_LOCAL"
    null = {"hypothesis": "x__b", "n": 100, "effect": 0.01, "p": 0.5, "verdict": "NULL_LOCAL"}
    out2 = vrw5._combine([confirmed, null])
    assert out2["verdict"] == "PROVISIONAL"  # one confirmed, one not -> provisional not confirmed
    opposite_sign = dict(confirmed, hypothesis="x__b", effect=-0.1)
    out3 = vrw5._combine([confirmed, opposite_sign])
    assert out3["verdict"] == "NULL_LOCAL"  # both confirmed but opposite sign -> not a real replication
