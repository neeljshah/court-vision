"""Per-file test for domains.basketball_wnba.profiles: percentile/rating math,
floor application, and hand-computed checks for one player builder
(on_court_impact + gravity's compound floor) and two lineup builders
(minutes_together, matchup_net's two-sided melt) on synthetic frames -- no
parquet reads, no network.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/profiles/test_build_profiles.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from domains.basketball_wnba.profiles.attribute_registry import ATTRIBUTES, rating_2k
from domains.basketball_wnba.profiles.build_profiles import _percentile_and_rating
from domains.basketball_wnba.profiles.ingredients_lineup import build_matchup_net, build_minutes_together
from domains.basketball_wnba.profiles.ingredients_player import build_gravity, build_on_court_impact


def test_percentile_and_rating_math():
    df = pd.DataFrame({
        "entity_id": ["1", "2", "3", "4"], "entity_name": ["a", "b", "c", "d"],
        "raw_value": [0.10, 0.30, 0.20, 0.40], "n": [500, 500, 500, 500], "ingredients": [{}] * 4,
    })
    out = _percentile_and_rating(df)
    row = out.set_index("entity_id")
    assert row.loc["1", "percentile"] == pytest.approx(25.0)
    assert row.loc["4", "percentile"] == pytest.approx(100.0)
    assert row.loc["4", "rating_2k"] == pytest.approx(rating_2k(100.0))


def test_percentile_drops_nan_raw_value():
    df = pd.DataFrame({"entity_id": ["1", "2"], "entity_name": ["a", "b"],
                        "raw_value": [0.5, float("nan")], "n": [500, 500], "ingredients": [{}, {}]})
    out = _percentile_and_rating(df)
    assert len(out) == 1
    assert out.iloc[0]["entity_id"] == "1"


def test_on_court_impact_floor_and_hand_computed():
    """floor=300 min_on. Player 1 clears it, player 2 does not."""
    df = pd.DataFrame({
        "player_id": [10, 20], "team_id": [1, 1], "player_name": ["A", "B"],
        "min_on": [400.0, 50.0], "min_off": [100.0, 200.0],
        "net_rating_on_per48": [6.5, -3.0], "net_rating_off_per48": [1.0, 2.0],
        "teammate_efg_on": [0.5, 0.5], "teammate_efg_off": [0.4, 0.4],
        "teammate_fga_on": [300, 300], "teammate_fga_off": [300, 300],
    })
    raw = build_on_court_impact(df)
    floor = ATTRIBUTES["on_court_impact"]["floor"]
    qualified = raw[raw["n"] >= floor]
    assert set(qualified["entity_id"]) == {"10"}
    row = raw.set_index("entity_id").loc["10"]
    assert row["raw_value"] == pytest.approx(6.5)
    assert row["n"] == pytest.approx(400.0)


def test_gravity_compound_floor_prefilters_min_on():
    """gravity pre-filters min_on>=300 INSIDE the builder (a compound floor
    the registry's single-int floor column can't express alone) -- a player
    below min_on must never reach the registry floor check at all."""
    df = pd.DataFrame({
        "player_id": [10, 20], "team_id": [1, 1], "player_name": ["A", "B"],
        "min_on": [400.0, 50.0],
        "teammate_efg_on": [0.55, 0.55], "teammate_efg_off": [0.45, 0.45],
        "teammate_fga_on": [250, 250], "teammate_fga_off": [250, 250],
    })
    out = build_gravity(df)
    assert set(out["entity_id"]) == {"10"}
    assert out.set_index("entity_id").loc["10", "raw_value"] == pytest.approx(0.10)
    assert out.set_index("entity_id").loc["10", "n"] == 250


def test_minutes_together_hand_computed():
    df = pd.DataFrame({
        "game_id": ["g1", "g1", "g2"], "team_id": [1, 1, 1],
        "lineup_key": ["1,2,3,4,5", "1,2,3,4,5", "1,2,3,4,5"],
        "elapsed_s": [200.0, 100.0, 150.0],
    })
    out = build_minutes_together(df).set_index("entity_id")
    assert out.loc["1:1,2,3,4,5", "n"] == pytest.approx(450.0)
    assert out.loc["1:1,2,3,4,5", "raw_value"] == pytest.approx(450.0 / 60.0)


def test_matchup_net_melts_both_sides():
    """A lineup appearing as BOTH lineup_key_a (one row) and lineup_key_b
    (another row) must have both sides summed into one entity row."""
    df = pd.DataFrame({
        "team_id_a": [1, 2], "team_id_b": [2, 1],
        "lineup_key_a": ["L1", "L2"], "lineup_key_b": ["L2", "L1"],
        "pts_a": [10.0, 4.0], "pts_b": [6.0, 8.0], "overlap_s": [120.0, 180.0],
    })
    out = build_matchup_net(df).set_index("entity_id")
    # L1/team1: side-a row0 (for=10,against=6,ov=120) + side-b row1 (for=8,against=4,ov=180)
    assert out.loc["1:L1", "n"] == pytest.approx(300.0)
    expected_net = (18.0 - 10.0) / (300.0 / 60.0) * 48.0
    assert out.loc["1:L1", "raw_value"] == pytest.approx(expected_net)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
