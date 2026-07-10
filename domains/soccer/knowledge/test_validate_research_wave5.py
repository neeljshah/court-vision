"""Per-file test for knowledge.validate_research_wave5. Run:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/knowledge/test_validate_research_wave5.py -q
"""
from __future__ import annotations

from domains.soccer.knowledge import validate_research_wave5 as vrw5


def test_self_check():
    vrw5._self_check()


def test_match_goal_kick_buildup_xg_no_shot_in_possession():
    events = [
        {"type": {"name": "Pass"}, "possession": 5,
         "pass": {"type": {"name": "Goal Kick"}, "height": {"name": "Low Pass"}}},
    ]
    gk = vrw5._match_goal_kick_buildup_xg(events)
    assert gk == [("Low Pass", 0.0)]


def test_match_goal_kick_buildup_xg_ignores_non_goal_kick_passes():
    events = [
        {"type": {"name": "Pass"}, "possession": 1,
         "pass": {"type": {"name": "Corner"}, "height": {"name": "High Pass"}}},
    ]
    assert vrw5._match_goal_kick_buildup_xg(events) == []


def test_gk_distribution_not_testable_below_floor():
    r = vrw5.gk_distribution_vs_buildup_xg([("Ground Pass", 0.1)] * 5 + [("High Pass", 0.0)] * 5)
    assert r["verdict"] == "NOT_TESTABLE"


def test_gk_distribution_null_when_no_gap():
    same = [("Ground Pass", 0.05)] * 40 + [("High Pass", 0.05)] * 40
    r = vrw5.gk_distribution_vs_buildup_xg(same)
    assert r["verdict"] == "NULL_LOCAL"
