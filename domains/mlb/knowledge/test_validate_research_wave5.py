"""Per-file test for knowledge.validate_research_wave5. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_research_wave5.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_research_wave5 as vrw5


def test_self_check():
    vrw5._self_check()


def test_per_game_putaway_frame_filters_2strike_and_floor():
    df = pd.DataFrame({
        "game_pk": [1] * 25 + [2] * 5,  # game 2 below the 20-pitch floor
        "strikes": [2] * 30,
        "description": (["ball"] * 10 + ["swinging_strike"] * 15) + (["ball"] * 5),
    })
    g = vrw5.per_game_putaway_frame(df)
    assert list(g["game_pk"]) == [1]
    assert g.iloc[0]["n"] == 25
    assert g.iloc[0]["whiffs"] == 15


def test_combine_dispersion_needs_both_confirmed():
    confirmed = {"hypothesis": "x__a", "n": 100, "effect": 1.5, "p": 0.001, "verdict": "CONFIRMED_LOCAL"}
    out = vrw5._combine_dispersion([confirmed, dict(confirmed, hypothesis="x__b")], "x")
    assert out["verdict"] == "CONFIRMED_LOCAL"
    null = dict(confirmed, hypothesis="x__b", verdict="NULL_LOCAL")
    out2 = vrw5._combine_dispersion([confirmed, null], "x")
    assert out2["verdict"] == "PROVISIONAL"


def test_half_inning_scoring_drops_games_missing_a_half():
    df = pd.DataFrame({
        "game_pk": [1, 1, 2],  # game 2 only has a Top half -> dropped
        "inning": [10, 10, 10],
        "inning_topbot": ["Top", "Bot", "Top"],
        "at_bat_number": [1, 1, 1], "pitch_number": [1, 1, 1],
        "home_score": [3, 3, 5], "away_score": [3, 4, 5],
        "post_home_score": [3, 4, 5], "post_away_score": [4, 4, 5],
    })
    out = vrw5.half_inning_scoring(df)
    assert set(out["game_pk"]) == {1}
    assert len(out) == 2
    top = out[out["inning_topbot"] == "Top"].iloc[0]
    assert bool(top["scored"]) is True  # away_score 3->4
    bot = out[out["inning_topbot"] == "Bot"].iloc[0]
    assert bool(bot["scored"]) is True  # home_score 3->4


def test_zombie_runner_scoring_rate_not_testable_below_floor():
    half = pd.DataFrame({"game_pk": [1], "inning_topbot": ["Top"], "scored": [True]})
    out = vrw5.zombie_runner_home_away_scoring_rate(half)
    assert out["verdict"] == "NOT_TESTABLE"
