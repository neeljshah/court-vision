"""Per-file test for the ESPN->NBA id-resolution guard (root cause of the
Elfrid-Payton 2024-25 contamination).

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/domains/basketball_nba/test_id_resolution_guard.py -q
"""
from __future__ import annotations

from domains.basketball_nba.ingest_espn_player_box import (
    is_stale_resolution,
    parse_summary_players,
)

_PAYTON = 203901


def test_retired_id_flagged_ge2_seasons_stale():
    # last real activity 2021-22; a 2024-25 game -> 2024-2021=3 (>=2 full seasons
    # missed) with no adjacent-season rows -> stale.
    activity = {_PAYTON: {2019, 2020, 2021}}
    assert is_stale_resolution(_PAYTON, "2024-25", activity) is True


def test_returning_player_after_one_missed_season_accepted():
    # last 2022-23, returns 2024-25 (missed only 2023-24) -> gap 2, below the bar.
    activity = {42: {2020, 2021, 2022}}
    assert is_stale_resolution(42, "2024-25", activity) is False


def test_adjacent_season_activity_accepted():
    # rows in 2023-24 (current-1) -> a real current-era player, never stale.
    activity = {7: {2018, 2023}}
    assert is_stale_resolution(7, "2024-25", activity) is False


def test_debut_no_prior_rows_accepted():
    # only current-season rows -> a rookie, must pass (guard needs prior history).
    activity = {99: {2024}}
    assert is_stale_resolution(99, "2024-25", activity) is False
    assert is_stale_resolution(1234, "2024-25", {}) is False  # unknown id


def _payload(name: str, espn_id: str, abbr: str = "NOP") -> dict:
    return {"boxscore": {"players": [{
        "team": {"abbreviation": abbr},
        "statistics": [{
            "keys": ["points"],
            "athletes": [{
                "starter": True,
                "athlete": {"id": espn_id, "displayName": name},
                "stats": ["10"],
            }],
        }],
    }]}}


def test_parse_rejects_stale_join_to_negative_placeholder():
    pmap = {"elfrid payton": _PAYTON}
    activity = {_PAYTON: {2019, 2020, 2021}}
    recs = parse_summary_players(_payload("Elfrid Payton", "1966"),
                                 pmap, season="2024-25", activity=activity)
    r = recs[0]
    assert r["player_id_mapped"] is False
    assert r["player_id"] == -1966              # negative-placeholder convention
    assert r["resolution_flag"] == "stale_id_ge2_seasons"
    assert r["rejected_id"] == _PAYTON


def test_parse_rejects_roster_absent_join():
    pmap = {"elfrid payton": _PAYTON}
    recs = parse_summary_players(_payload("Elfrid Payton", "1966"),
                                 pmap, season="2024-25", roster_ids={"NOP": {111, 222}})
    r = recs[0]
    assert r["player_id_mapped"] is False and r["resolution_flag"] == "roster_absent"


def test_parse_guard_inert_without_season():
    # back-compat: no season -> accept the join unchanged (existing callers).
    pmap = {"elfrid payton": _PAYTON}
    recs = parse_summary_players(_payload("Elfrid Payton", "1966"), pmap)
    assert recs[0]["player_id"] == _PAYTON and recs[0]["player_id_mapped"] is True
