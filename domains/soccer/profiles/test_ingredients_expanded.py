"""Per-file test for the 07-08 soccer expansion (domains.soccer.profiles.
ingredients_expanded): defensive-mirror math (conceded_snap is the OPPONENT's
own possessions reassigned, so defensive_counter_threat/set_piece_threat must
reuse counter_threat/set_piece_threat's formula unchanged), half-xg-share,
footballdata rate/ratio factories, and floor-relevant edge cases.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/soccer/profiles/test_ingredients_expanded.py -q
"""
from __future__ import annotations

import math

import pandas as pd

from domains.soccer.profiles.ingredients_expanded import (
    _away_strength,
    _clean_sheet_rate,
    _comeback_rate,
    _corner_rate,
    _defensive_counter_threat,
    _defensive_set_piece_threat,
    _first_half_xg_share,
    _formation_primary_xg,
    _formation_secondary_xg,
    _home_goal_rate,
    _possessions_per_match,
    _second_half_xg_share,
    _shot_accuracy,
    _shot_conversion_rate,
    _shots_per_possession,
)


def _conceded_snap():
    # Team A concedes 2 possessions to opponent (1 counter, 1 regular);
    # Team B concedes 1 possession (set-piece).
    return pd.DataFrame([
        {"entity_id": "A", "match_id": 1, "xg": 0.4, "counter_xg": 0.4, "regular_xg": None, "set_piece_xg": 0.0},
        {"entity_id": "A", "match_id": 1, "xg": 0.1, "counter_xg": None, "regular_xg": 0.1, "set_piece_xg": 0.0},
        {"entity_id": "B", "match_id": 2, "xg": 0.3, "counter_xg": None, "regular_xg": None, "set_piece_xg": 0.3},
    ])


def test_defensive_counter_threat_mirrors_offense_formula():
    """Same sum(counter_xg)/count(xg) formula as offensive counter_threat,
    just on the CONCEDED snapshot -- Team A concedes 0.4 counter xg over 2
    total conceded possessions -> 0.2."""
    snap = _conceded_snap()
    float_cols = ["xg", "counter_xg", "regular_xg", "set_piece_xg"]
    snap[float_cols] = snap[float_cols].astype(float)
    names = pd.Series({"A": "Team A", "B": "Team B"})
    out = _defensive_counter_threat(snap, names).set_index("entity_id")
    assert math.isclose(out.loc["A", "raw_value"], 0.4 / 2, rel_tol=1e-9)
    assert out.loc["A", "entity_name"] == "Team A"


def test_defensive_set_piece_threat_mirrors_offense_formula():
    snap = _conceded_snap()
    float_cols = ["xg", "counter_xg", "regular_xg", "set_piece_xg"]
    snap[float_cols] = snap[float_cols].astype(float)
    names = pd.Series({"A": "Team A", "B": "Team B"})
    out = _defensive_set_piece_threat(snap, names).set_index("entity_id")
    # Team B: all conceded xg (0.3) is set-piece -> share = 1.0
    assert math.isclose(out.loc["B", "raw_value"], 1.0, rel_tol=1e-9)
    # Team A: 0 of 0.5 conceded xg is set-piece -> share = 0.0
    assert math.isclose(out.loc["A", "raw_value"], 0.0, abs_tol=1e-9)


def test_half_xg_share_hand_computed():
    poss_snap = pd.DataFrame([
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.6, "first_half_xg": 0.6, "second_half_xg": 0.0},
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.4, "first_half_xg": 0.0, "second_half_xg": 0.4},
    ])
    first = _first_half_xg_share(poss_snap).set_index("entity_id")
    second = _second_half_xg_share(poss_snap).set_index("entity_id")
    assert math.isclose(first.loc["A", "raw_value"], 0.6)
    assert math.isclose(second.loc["A", "raw_value"], 0.4)
    assert math.isclose(first.loc["A", "raw_value"] + second.loc["A", "raw_value"], 1.0)


def test_possessions_per_match_and_shots_per_possession():
    poss_snap = pd.DataFrame([
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.1},
        {"entity_id": "A", "entity_name": "Team A", "match_id": 1, "xg": 0.2},
        {"entity_id": "A", "entity_name": "Team A", "match_id": 2, "xg": 0.3},
    ])
    out = _possessions_per_match(poss_snap).set_index("entity_id")
    assert out.loc["A", "raw_value"] == 1.5  # 3 possessions / 2 matches
    assert out.loc["A", "n"] == 2

    shot_counts = pd.DataFrame([{"match_id": 1, "team_id": "A", "n_shots": 4}, {"match_id": 2, "team_id": "A", "n_shots": 2}])
    spp = _shots_per_possession(poss_snap, shot_counts).set_index("entity_id")
    assert spp.loc["A", "raw_value"] == 2.0  # 6 shots / 3 possessions


def test_formation_rank_floor_excludes_thin_formations():
    """A team's 2nd-most-used formation with <10 matches must be dropped --
    rank() alone isn't enough, the MIN_FORMATION_MATCHES floor gates it too."""
    form_snap = pd.DataFrame(
        [{"entity_id": "A", "entity_name": "Team A", "match_id": m, "formation": "4-3-3", "is_primary": 1.0} for m in range(1, 13)]
        + [{"entity_id": "A", "entity_name": "Team A", "match_id": m, "formation": "4-4-2", "is_primary": 0.0} for m in range(13, 16)]
    )
    poss_snap = pd.DataFrame([
        {"entity_id": "A", "entity_name": "Team A", "match_id": m, "xg": 0.2} for m in range(1, 16)
    ])
    primary = _formation_primary_xg(poss_snap, form_snap)
    secondary = _formation_secondary_xg(poss_snap, form_snap)
    assert len(primary) == 1 and primary.iloc[0]["ingredients"]["formation"] == "4-3-3"
    assert secondary.empty  # 4-4-2 only has 3 matches, below MIN_FORMATION_MATCHES=10


def test_footballdata_rate_and_ratio_factories():
    snap = pd.DataFrame([
        {"entity_id": "A", "season": 2020, "match_id": 1, "is_home": True,
         "goals_for": 2.0, "goals_against": 1.0, "shots_for": 10.0, "sot_for": 5.0,
         "corners_for": 6.0, "fouls_for": 8.0, "cards_for": 2.0,
         "clean_sheet": 0.0, "trailed_ht": 1.0, "won_or_drew": 1.0},
        {"entity_id": "A", "season": 2020, "match_id": 2, "is_home": False,
         "goals_for": 0.0, "goals_against": 0.0, "shots_for": 8.0, "sot_for": 2.0,
         "corners_for": 4.0, "fouls_for": 10.0, "cards_for": 1.0,
         "clean_sheet": 1.0, "trailed_ht": 0.0, "won_or_drew": 1.0},
    ])
    home_rate = _home_goal_rate(snap).set_index("entity_id")
    assert home_rate.loc["A", "raw_value"] == 2.0  # only the home row
    clean = _clean_sheet_rate(snap).set_index("entity_id")
    assert clean.loc["A", "raw_value"] == 0.5  # 1 of 2 matches
    comeback = _comeback_rate(snap).set_index("entity_id")
    assert comeback.loc["A", "raw_value"] == 1.0  # trailed once, won/drew that match
    conv = _shot_conversion_rate(snap).set_index("entity_id")
    assert math.isclose(conv.loc["A", "raw_value"], 2.0 / 18.0)
    acc = _shot_accuracy(snap).set_index("entity_id")
    assert math.isclose(acc.loc["A", "raw_value"], 7.0 / 18.0)
    corners = _corner_rate(snap).set_index("entity_id")
    assert corners.loc["A", "raw_value"] == 5.0  # mean(6,4)
    away = _away_strength(snap).set_index("entity_id")
    assert math.isclose(away.loc["A", "raw_value"], 1.0 / 3.0)  # 1 away draw = 1pt / 1 match / 3


if __name__ == "__main__":
    import sys
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
