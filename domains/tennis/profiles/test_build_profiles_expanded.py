"""Per-file test for domains.tennis.profiles.ingredients_expanded /
build_profiles_expanded. Covers: within-game court-side parity derivation,
game-point identification (mirror of the existing break-point test),
tiebreak share math, and window/floor enforcement -- all on synthetic
frames, no writes to any production path.

Run: python -m pytest domains/tennis/profiles/test_build_profiles_expanded.py -q
"""
from __future__ import annotations

import pandas as pd

from domains.tennis.profiles.attribute_registry import (
    ATTRIBUTES, MATCH_AGG_BUCKETS, MATCH_AGG_METRICS, concrete_attributes,
)
from domains.tennis.profiles.ingredients_expanded import (
    _won_rollup, courtside_points, game_point_points, service_games, set_bucket_points,
    tiebreak_points, tiebreak_serve_points,
)

_MID = "20240101-m-evt-R1-Player_One-Player_Two"


def _pts(rows: list[dict]) -> pd.DataFrame:
    """Fills in the charting_points columns a test doesn't care about."""
    base = {"match_id": _MID, "date": "2024-01-01", "date_source": "match_date", "tour": "m",
            "is_second_serve": False, "rally_length": pd.NA, "set1": 0, "set2": 0}
    return pd.DataFrame([{**base, **r} for r in rows])


def test_registry_grew_to_49_and_new_families_present():
    # registry now carries the WINDOW/OPPONENT-TIER/FORM families too (see
    # test_build_profiles_windows.py) -- 49 was this module's own delivered
    # count; the live total is asserted there (72) so this file doesn't need
    # editing every time a sibling module adds attributes.
    assert len(concrete_attributes()) >= 49
    for attr in ("courtside_serve_deuce", "courtside_serve_ad", "serve_by_set_set1",
                 "momentum_bounceback", "momentum_streakiness", "tiebreak_points_won_share",
                 "tiebreak_serve_win_rate", "second_serve_aggression_delta", "game_point_conversion"):
        assert attr in ATTRIBUTES and ATTRIBUTES[attr]["status"] == "DESCRIPTIVE"
    assert len(MATCH_AGG_METRICS) == 7 and len(MATCH_AGG_BUCKETS) == 4
    for metric in MATCH_AGG_METRICS:
        for bucket in MATCH_AGG_BUCKETS:
            assert f"match_agg_{metric}_{bucket}" in ATTRIBUTES


def test_courtside_parity_matches_within_game_point_order():
    """4-point game: points 0,2 (0-indexed) are deuce court, 1,3 are ad court --
    the same alternation verified against real charting_points data this session."""
    pts = _pts([
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "0-0"},   # idx0 deuce
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "15-0"},  # idx1 ad
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 2, "score_state": "30-0"},  # idx2 deuce
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "30-15"}, # idx3 ad
    ])
    out = courtside_points(pts)
    assert list(out["side"]) == ["deuce", "ad", "deuce", "ad"]
    assert list(out["won"]) == [1, 1, 0, 1]


def test_set_bucket_from_sets_won_so_far():
    pts = pd.concat([
        _pts([{"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "0-0"}]).assign(set1=0, set2=0),
        _pts([{"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "0-0"}]).assign(set1=1, set2=0),
        _pts([{"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "0-0"}]).assign(set1=1, set2=1),
    ], ignore_index=True)
    out = set_bucket_points(pts)
    assert list(out["set_bucket"]) == ["set1", "set2", "set3plus"]


def test_game_point_identification_mirrors_break_point():
    """40-0/AD-40 (server one point from the game) ARE game points; 40-40 (deuce,
    only advantage) and 15-0 are NOT -- exact mirror of the existing break-point rule."""
    pts = _pts([
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "40-0"},
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "AD-40"},
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 2, "score_state": "40-40"},
        {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 1, "score_state": "15-0"},
    ])
    out = game_point_points(pts)
    assert list(out["game_point"]) == [True, True, False, False]


def test_tiebreak_share_math_excludes_standard_scores():
    """5-3 / AD-6-style raw-integer scores ARE tiebreak points; 30-15 (standard) is not."""
    pts = _pts([
        {"gm1": 6, "gm2": 6, "server": 1, "point_winner": 1, "score_state": "5-3"},
        {"gm1": 6, "gm2": 6, "server": 2, "point_winner": 2, "score_state": "6-3"},
        {"gm1": 5, "gm2": 5, "server": 1, "point_winner": 1, "score_state": "30-15"},  # standard -- excluded
    ])
    share = tiebreak_points(pts)
    # 2 tiebreak points x 2 participants (slot1/slot2) = 4 rows; standard-score row absent
    assert len(share) == 4
    assert share["won"].sum() == 2  # one won-point row per TB point (winner's row)
    serve = tiebreak_serve_points(pts)
    assert len(serve) == 2
    assert list(serve["won"]) == [1, 1]  # server=1 won pt1 (as server), server=2 won pt2 (as server)


def test_won_rollup_enforces_floor_and_bucket_filter():
    df = pd.DataFrame([
        {"entity_id": "a", "entity_name": "A", "year": 2023, "side": "deuce", "won": 1},
        {"entity_id": "a", "entity_name": "A", "year": 2023, "side": "deuce", "won": 0},
        {"entity_id": "a", "entity_name": "A", "year": 2023, "side": "ad", "won": 1},
    ])
    deuce = _won_rollup(df, floor=2, bucket_col="side", bucket_val="deuce")
    assert (deuce["entity_id"] == "a").any()
    ad_below_floor = _won_rollup(df, floor=2, bucket_col="side", bucket_val="ad")
    assert ad_below_floor.empty  # only 1 ad point, floor=2 excludes it


def test_service_games_requires_a_preceding_own_service_game():
    """Player 'one_p' serves games 1 and 3 (alternating); game 3 is the first row
    WITH a valid preceding own service game (game 1 has none -> dropped)."""
    pts = pd.concat([
        _pts([{"gm1": 0, "gm2": 0, "server": 1, "point_winner": 2, "score_state": "0-0"},
              {"gm1": 0, "gm2": 0, "server": 1, "point_winner": 2, "score_state": "0-15"}]),  # game1: server1 broken
        _pts([{"gm1": 1, "gm2": 0, "server": 2, "point_winner": 1, "score_state": "0-0"},
              {"gm1": 1, "gm2": 0, "server": 2, "point_winner": 1, "score_state": "0-15"}]),  # game2 (server2)
        _pts([{"gm1": 1, "gm2": 1, "server": 1, "point_winner": 1, "score_state": "0-0"},
              {"gm1": 1, "gm2": 1, "server": 1, "point_winner": 1, "score_state": "15-0"},
              {"gm1": 1, "gm2": 1, "server": 1, "point_winner": 1, "score_state": "30-0"},
              {"gm1": 1, "gm2": 1, "server": 1, "point_winner": 1, "score_state": "40-0"}]),  # game3: server1 holds
    ], ignore_index=True)
    sg = service_games(pts)
    one_p = sg[sg["entity_id"] == "one_p"]
    assert len(one_p) == 1  # game1 dropped (no preceding own service game)
    assert bool(one_p["prev_broken"].iloc[0]) is True  # game1 was a break
    assert int(one_p["won"].iloc[0]) == 1  # game3 held
