"""Per-file test for knowledge.validate_research_wave3. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_research_wave3.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.knowledge import validate_research_wave3 as vrw3


def test_verdict_rule_uses_per_hypothesis_min_effect():
    assert vrw3._verdict(0.001, 0.20, "bullpen_day_scoring_structure") == "CONFIRMED_LOCAL"
    assert vrw3._verdict(0.5, 0.20, "bullpen_day_scoring_structure") == "NULL_LOCAL"
    assert vrw3._verdict(0.001, 0.01, "mid_inning_pitching_change_interrupt") == "NULL_LOCAL"  # below 0.02 bar
    assert vrw3._verdict(None, 0.1, "pinch_sub_platoon_targeting") == "NOT_TESTABLE"


def test_flag_bullpen_day_maps_team_codes_and_applies_ip_floor():
    pg = pd.DataFrame({"game_pk": [1, 1, 2], "team": ["SF", "LAD", "AL"],
                        "date": pd.to_datetime(["2025-04-01", "2025-04-01", "2025-04-02"]),
                        "is_pitcher": [True, True, True], "inningsPitched": [3.0, 6.0, 5.0]})
    flagged = vrw3._flag_bullpen_day(pg)
    assert set(flagged["team_mapped"]) == {"SFO", "LAD"}  # AL all-star row dropped
    assert flagged.loc[flagged["team_mapped"] == "SFO", "bullpen_day"].iloc[0]
    assert not flagged.loc[flagged["team_mapped"] == "LAD", "bullpen_day"].iloc[0]


def test_flag_bullpen_day_drops_doubleheader_ambiguous_rows():
    pg = pd.DataFrame({"game_pk": [1, 2], "team": ["SF", "SF"],
                        "date": pd.to_datetime(["2025-04-01", "2025-04-01"]),
                        "is_pitcher": [True, True], "inningsPitched": [3.0, 6.0]})
    flagged = vrw3._flag_bullpen_day(pg)
    assert len(flagged) == 0  # both rows share (date,team_mapped) -- ambiguous, both dropped


def test_team_game_legs_unpivots_home_away_and_flips_away_win():
    gc = pd.DataFrame({"date": pd.to_datetime(["2025-04-01"]), "home_team": ["SFO"], "away_team": ["LAD"],
                        "home_runs": [5], "away_runs": [3], "target_home_win": [1]})
    legs = vrw3._team_game_legs(gc)
    assert set(legs["team"]) == {"SFO", "LAD"}
    assert legs.loc[legs["team"] == "SFO", "own_win"].iloc[0] == 1
    assert legs.loc[legs["team"] == "LAD", "own_win"].iloc[0] == 0


def test_bullpen_day_scoring_structure_not_testable_below_group_floor():
    merged = pd.DataFrame({"bullpen_day": [True, False], "own_runs": [4, 5], "own_win": [1, 0]})
    r = vrw3.bullpen_day_scoring_structure(merged, "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_mid_inning_change_events_flags_only_mid_inning_outs_gt_zero():
    pa = pd.DataFrame({
        "game_pk": [1] * 5, "inning": [1] * 5, "inning_topbot": ["Bot"] * 5, "pitcher": [10, 10, 20, 20, 20],
        "at_bat_number": [1, 2, 3, 4, 5], "outs_when_up": [0, 1, 2, 0, 1],
        "home_score": [0, 1, 3, 3, 3], "post_home_score": [1, 3, 3, 3, 4],
        "away_score": [0, 0, 0, 0, 0], "post_away_score": [0, 0, 0, 0, 0],
    })
    ev = vrw3._mid_inning_change_events(pa)
    assert len(ev) == 1  # pitcher 10->20 at i=2 with outs_when_up=2>0 qualifies


def test_mid_inning_pitching_change_interrupt_not_testable_below_event_floor():
    r = vrw3.mid_inning_pitching_change_interrupt(pd.DataFrame({
        "game_pk": [1], "inning": [1], "inning_topbot": ["Bot"], "pitcher": [10], "at_bat_number": [1],
        "outs_when_up": [0], "home_score": [0], "post_home_score": [0], "away_score": [0], "post_away_score": [0],
    }), "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_pinch_sub_first_pa_picks_lower_atbats_player_in_shared_slot():
    pg = pd.DataFrame({"game_pk": [1, 1], "team": ["TB", "TB"], "batting_order": [9.0, 9.0],
                        "player_id": [100, 200], "atBats": [3.0, 1.0]})
    sv = pd.DataFrame({"game_pk": [1, 1], "batter": [100, 200], "at_bat_number": [2, 5],
                        "stand": ["R", "R"], "p_throws": ["L", "R"]})
    subs = vrw3._pinch_sub_first_pa(pg, sv)
    assert list(subs["player_id"]) == [200]  # lower atBats (1.0) is the substitute
    assert subs["p_throws"].iloc[0] == "R"


def test_pinch_sub_platoon_targeting_not_testable_below_floor():
    r = vrw3.pinch_sub_platoon_targeting(pd.DataFrame({"stand": ["R"], "p_throws": ["L"]}),
                                          pd.DataFrame({"stand": ["R"], "p_throws": ["L"]}), "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_combine_requires_both_halves_confirmed_same_direction():
    a = {"hypothesis": "x__h1", "n": 100, "effect": 0.2, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    b = {"hypothesis": "x__h2", "n": 100, "effect": 0.2, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    assert vrw3._combine("x", [a, b])["verdict"] == "CONFIRMED_LOCAL"
    c = {"hypothesis": "x__h2", "n": 100, "effect": 0.01, "p": 0.5, "verdict": "NULL_LOCAL"}
    assert vrw3._combine("x", [a, c])["verdict"] == "PROVISIONAL"


def test_self_check_runs_clean():
    vrw3._self_check()
