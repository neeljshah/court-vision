"""Per-file unit tests for prop_prizepicks (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_prizepicks.py -q

Canned payloads mirror the REAL shapes probed 2026-06-17 (trimmed): a /leagues
list (so league-id is resolved BY NAME) + a /projections pair. http_get is
injected; nothing here touches the network.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_prizepicks import (
    PrizePicksProvider, find_league_id, parse_props)

LEAGUES = {
    "data": [
        {"id": "7", "attributes": {"name": "NBA"}},
        {"id": "241", "attributes": {"name": "WORLD CUP"}},
        {"id": "458", "attributes": {"name": "WORLD CUP 1H"}},
        {"id": "82", "attributes": {"name": "SOCCER"}},
        # MLB and its lookalikes (exact-name match must pick id 2, not these).
        {"id": "2", "attributes": {"name": "MLB"}},
        {"id": "231", "attributes": {"name": "MLBLIVE"}},
        {"id": "190", "attributes": {"name": "MLBSZN"}},
        {"id": "261", "attributes": {"name": "MLBSZN2"}},
    ]
}

PROJECTIONS = {
    "data": [
        {"type": "projection", "id": "PJ1",
         "attributes": {"stat_type": "Shots on Target", "line_score": 1.5,
                        "odds_type": "standard", "description": "Colombia"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "322280"}},
             "game": {"data": {"type": "game", "id": "164820"}}}},
        {"type": "projection", "id": "PJ2",
         "attributes": {"stat_type": "Passes Attempted", "line_score": 45.5,
                        "odds_type": "demon", "description": "Colombia"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "322280"}},
             "game": {"data": {"type": "game", "id": "164820"}}}},
    ],
    "included": [
        {"type": "new_player", "id": "322280",
         "attributes": {"name": "Luis Diaz", "team": "Colombia",
                        "league": "WORLD CUP"}},
        {"type": "game", "id": "164820",
         "attributes": {"metadata": {"game_info": {"teams": {
             "home": {"abbreviation": "Canada"},
             "away": {"abbreviation": "Qatar"}}}}}},
    ],
}


def test_find_league_id_exact_name():
    assert find_league_id(LEAGUES, "WORLD CUP") == "241"
    # must not collide with "WORLD CUP 1H"
    assert find_league_id(LEAGUES, "world cup") == "241"
    assert find_league_id(LEAGUES, "NOPE") is None


def test_parse_props_pickem_rows():
    rows = parse_props(PROJECTIONS, "soccer_intl")
    assert isinstance(rows, list)
    assert len(rows) == 2
    by_stat = {r.stat: r for r in rows}
    assert set(by_stat) == {"Shots On Target", "Passes Attempted"}

    sot = by_stat["Shots On Target"]
    assert sot.player == "Luis Diaz"
    assert sot.team == "Colombia"
    assert sot.match == "Canada v Qatar"
    assert sot.line == 1.5
    # pick'em: no fabricated two-sided price
    assert sot.over_price is None
    assert sot.under_price is None
    assert sot.payout_type == "dfs_pickem"
    assert sot.source == "prizepicks"
    assert sot.as_of is not None


def test_provider_two_call_flow():
    def http_get(url):
        return LEAGUES if "leagues" in url else PROJECTIONS

    prov = PrizePicksProvider(http_get=http_get)
    rows = prov.fetch_props("soccer_intl")
    assert isinstance(rows, list)
    assert all(r.sport == "soccer_intl" for r in rows)
    assert all(r.over_price is None and r.under_price is None for r in rows)


def test_league_id_cached():
    calls = {"leagues": 0}

    def http_get(url):
        if "leagues" in url:
            calls["leagues"] += 1
            return LEAGUES
        return PROJECTIONS

    prov = PrizePicksProvider(http_get=http_get)
    prov.fetch_props("soccer_intl")
    prov.fetch_props("soccer_intl")
    assert calls["leagues"] == 1  # league lookup cached in-instance


def test_unsupported_sport_unavailable():
    prov = PrizePicksProvider(http_get=lambda url: PROJECTIONS)
    assert is_unavailable(prov.fetch_props("cricket"))


def test_league_not_found_unavailable():
    prov = PrizePicksProvider(http_get=lambda url: {"data": []})
    assert is_unavailable(prov.fetch_props("soccer_intl"))


def test_injected_failure_degrades_no_raise():
    def boom(url):
        raise RuntimeError("network down")

    prov = PrizePicksProvider(http_get=boom)
    assert is_unavailable(prov.fetch_props("soccer_intl"))


def test_find_league_id_mlb_exact_not_lookalike():
    # "MLB" must resolve to id 2, never MLBLIVE / MLBSZN / MLBSZN2.
    assert find_league_id(LEAGUES, "MLB") == "2"
    assert find_league_id(LEAGUES, "mlb") == "2"
    assert find_league_id(LEAGUES, "NBA") == "7"


# Canned MLB /projections (probed 2026-06-18 stat_type labels): "Hits+Runs+RBIs",
# "Hitter Strikeouts" -> Batter Strikeouts, "Pitcher Strikeouts", "Earned Runs
# Allowed" -> Earned Runs. All pick'em (no two-sided price in payload).
PROJ_MLB = {
    "data": [
        {"type": "projection", "id": "MJ1",
         "attributes": {"stat_type": "Hits+Runs+RBIs", "line_score": 1.5,
                        "odds_type": "standard"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "9001"}},
             "game": {"data": {"type": "game", "id": "G1"}}}},
        {"type": "projection", "id": "MJ2",
         "attributes": {"stat_type": "Hitter Strikeouts", "line_score": 0.5,
                        "odds_type": "standard"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "9001"}},
             "game": {"data": {"type": "game", "id": "G1"}}}},
        {"type": "projection", "id": "MJ3",
         "attributes": {"stat_type": "Pitcher Strikeouts", "line_score": 6.5,
                        "odds_type": "standard"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "9002"}},
             "game": {"data": {"type": "game", "id": "G1"}}}},
        {"type": "projection", "id": "MJ4",
         "attributes": {"stat_type": "Earned Runs Allowed", "line_score": 2.5,
                        "odds_type": "standard"},
         "relationships": {
             "new_player": {"data": {"type": "new_player", "id": "9002"}},
             "game": {"data": {"type": "game", "id": "G1"}}}},
    ],
    "included": [
        {"type": "new_player", "id": "9001",
         "attributes": {"name": "Aaron Judge", "team": "NYY"}},
        {"type": "new_player", "id": "9002",
         "attributes": {"name": "Gerrit Cole", "team": "NYY"}},
        {"type": "game", "id": "G1",
         "attributes": {"metadata": {"game_info": {"teams": {
             "home": {"abbreviation": "BOS"},
             "away": {"abbreviation": "NYY"}}}}}},
    ],
}


def test_parse_props_mlb_canonical_stats():
    rows = parse_props(PROJ_MLB, "mlb")
    assert isinstance(rows, list)
    assert len(rows) == 4
    by_stat = {r.stat: r for r in rows}
    assert set(by_stat) == {
        "Hits+Runs+RBIs", "Batter Strikeouts", "Pitcher Strikeouts",
        "Earned Runs"}
    hrr = by_stat["Hits+Runs+RBIs"]
    assert hrr.player == "Aaron Judge"
    assert hrr.match == "BOS v NYY"
    assert hrr.line == 1.5
    assert hrr.payout_type == "dfs_pickem"
    assert hrr.over_price is None and hrr.under_price is None
    assert hrr.source == "prizepicks"


def test_provider_two_call_flow_mlb():
    def http_get(url):
        return LEAGUES if "leagues" in url else PROJ_MLB

    prov = PrizePicksProvider(http_get=http_get)
    rows = prov.fetch_props("mlb")
    assert isinstance(rows, list)
    assert all(r.sport == "mlb" for r in rows)


def test_nba_sport_wired_offseason_empty():
    # NBA league is wired; an empty projections payload -> UNAVAILABLE (not error,
    # not unsupported-sport).
    def http_get(url):
        return LEAGUES if "leagues" in url else {"data": [], "included": []}

    prov = PrizePicksProvider(http_get=http_get)
    res = prov.fetch_props("nba")
    assert is_unavailable(res)
    assert "unsupported" not in res.get("reason", "")


def test_no_rows_unavailable():
    res = parse_props({"data": [], "included": []}, "soccer_intl")
    assert is_unavailable(res)


def test_leagues_fetch_failure_reason_not_mislabeled_as_not_found():
    # A blocked/failed /leagues call (e.g. the live 2026-07-02 403 WAF block) must
    # surface its REAL reason, never the generic "league 'X' not found" message --
    # that would mislead diagnosis into thinking the league name is wrong.
    def http_get(url):
        if "leagues" in url:
            return {"status": "unavailable", "reason": "prizepicks GET failed (HTTPError)"}
        return PROJECTIONS

    prov = PrizePicksProvider(http_get=http_get)
    res = prov.fetch_props("mlb")
    assert is_unavailable(res)
    assert "not found" not in res.get("reason", "")
    assert "leagues lookup failed" in res.get("reason", "")
