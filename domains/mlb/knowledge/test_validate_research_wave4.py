"""Per-file test for knowledge.validate_research_wave4. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/mlb/knowledge/test_validate_research_wave4.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.mlb.knowledge import validate_research_wave4 as vrw4


def test_verdict_rule_uses_declared_bar():
    assert vrw4._verdict(0.001, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "CONFIRMED_LOCAL"
    assert vrw4._verdict(0.5, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "NULL_LOCAL"
    assert vrw4._verdict(0.001, -0.01, "baserunning_aggression_vs_outfield_arm_deterrence") == "NULL_LOCAL"  # below 0.05 bar
    assert vrw4._verdict(None, -0.10, "baserunning_aggression_vs_outfield_arm_deterrence") == "NOT_TESTABLE"


def _toy_df() -> pd.DataFrame:
    return pd.DataFrame({
        "event_id": [1, 2, 3], "date": pd.to_datetime(["2025-04-01", "2025-04-02", "2025-04-03"]),
        "home_abbr": ["SF", "SF", "LAD"], "away_abbr": ["LAD", "LAD", "SF"],
        "home_fld_outfieldAssists": [0.0, 1.0, 2.0], "away_fld_outfieldAssists": [1.0, 0.0, 0.0],
        "home_bat_stolenBases": [1.0, 0.0, 2.0], "home_bat_caughtStealing": [0.0, 1.0, 0.0],
        "away_bat_stolenBases": [0.0, 1.0, 0.0], "away_bat_caughtStealing": [1.0, 0.0, 1.0],
    })


def test_team_game_outfield_assists_unpivots_home_and_away():
    tg = vrw4._team_game_outfield_assists(_toy_df())
    assert len(tg) == 6
    assert set(tg["team"]) == {"SF", "LAD"}


def test_leave_one_out_arm_rate_excludes_own_game():
    tg = vrw4._team_game_outfield_assists(_toy_df())
    loo = vrw4._leave_one_out_arm_rate(tg)
    sf_ev1 = loo[(loo["team"] == "SF") & (loo["event_id"] == 1)]
    # SF plays 3 games (home ev1=0.0, home ev2=1.0, away ev3=0.0); LOO for ev1
    # excludes its own 0.0: (1.0-0.0)/(3-1) = 0.5.
    assert sf_ev1["loo_rate"].iloc[0] == 0.5


def test_leave_one_out_arm_rate_drops_single_game_teams():
    tg = pd.DataFrame({"event_id": [1], "date": pd.to_datetime(["2025-04-01"]),
                        "team": ["SF"], "outfield_assists": [1.0]})
    loo = vrw4._leave_one_out_arm_rate(tg)
    assert len(loo) == 0  # count-1 == 0, LOO undefined, dropped


def test_batting_rows_pairs_batting_team_with_opponent_code():
    bat = vrw4._batting_rows(_toy_df())
    assert len(bat) == 6
    row = bat[(bat["event_id"] == 1) & (bat["bat_team"] == "SF")]
    assert row["opp_team"].iloc[0] == "LAD"
    assert row["sb_cs"].iloc[0] == 1.0  # sb=1.0 + cs=0.0


def test_merged_baserunning_arm_joins_opponent_loo_rate():
    merged = vrw4._merged_baserunning_arm(_toy_df())
    assert len(merged) == 6
    assert "loo_rate" in merged.columns


def test_baserunning_aggression_not_testable_below_row_floor():
    r = vrw4.baserunning_aggression_vs_outfield_arm_deterrence(
        pd.DataFrame({"sb_cs": [1.0], "loo_rate": [0.5]}), "h1")
    assert r["verdict"] == "NOT_TESTABLE"


def test_combine_requires_both_halves_confirmed_same_direction():
    a = {"hypothesis": "x__h1", "n": 100, "effect": -0.2, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    b = {"hypothesis": "x__h2", "n": 100, "effect": -0.2, "p": 0.0001, "verdict": "CONFIRMED_LOCAL"}
    assert vrw4._combine("x", [a, b])["verdict"] == "CONFIRMED_LOCAL"
    c = {"hypothesis": "x__h2", "n": 100, "effect": 0.01, "p": 0.5, "verdict": "NULL_LOCAL"}
    assert vrw4._combine("x", [a, c])["verdict"] == "PROVISIONAL"


def test_self_check_runs_clean():
    vrw4._self_check()
