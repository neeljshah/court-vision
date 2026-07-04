"""Per-file test for Pinnacle sport -> league id resolution (regression guard).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/odds_provider/test_pinnacle_league_ids.py -q

Context: Pinnacle DELISTS a league id when a tournament rotates (401, not a
404 -- see pinnacle_league_resolver's docstring). soccer_intl rotated from
2764 (pre-kickoff) to 2686 ("FIFA - World Cup") once the 2026 World Cup proper
started; tennis's OLD hardcoded id 12 is dead entirely (live-verified 401 on
2026-07-03) -- tennis is now resolved LIVE per round (e.g. 'ATP Wimbledon -
R3') via pinnacle_league_resolver instead of a single static id. This file
locks in: the static ids still on _LEAGUE_ID, AND that tennis/multi-league
fetch is resolver-driven with per-league 401 isolation + invalidation.
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.pinnacle import _LEAGUE_ID, PinnacleProvider
from scripts.platformkit.odds_provider import pinnacle_league_resolver


def test_soccer_intl_league_id_is_current_world_cup():
    assert _LEAGUE_ID["soccer_intl"] == 2686


def test_soccer_intl_league_id_not_stale_pre_kickoff_id():
    assert _LEAGUE_ID["soccer_intl"] != 2764


def test_wnba_league_id_is_static_578():
    """LANE 2, probed live 2026-07-03: GET /sports/4/leagues found WNBA as a
    persistent named league (id 578, matchupCount=3) -- static, not rotating."""
    assert _LEAGUE_ID["wnba"] == 578


def test_wnba_resolves_via_static_fast_path_no_network():
    ids = pinnacle_league_resolver.resolve_league_ids(
        "wnba", http_get=lambda url: (_ for _ in ()).throw(
            AssertionError("wnba is static -- must not hit the network")))
    assert ids == [578]


def test_unsupported_sport_still_degrades_honestly():
    res = PinnacleProvider(http_get=lambda url: (_ for _ in ()).throw(
        AssertionError("should not fetch for an unsupported sport"))).fetch("curling")
    assert res == {"status": "unavailable",
                    "reason": "pinnacle: no live league ids for 'curling'"}


_WIMBLEDON_LEAGUES = [
    {"id": 3336, "name": "ATP Wimbledon - R3", "matchupCount": 20},
    {"id": 3824, "name": "WTA Wimbledon - R3", "matchupCount": 14},
    {"id": 9999, "name": "ATP Wimbledon - Doubles R2", "matchupCount": 8},
]


def test_tennis_not_served_from_stale_static_id_12(tmp_path):
    cache = tmp_path / "leagues.json"
    ids = pinnacle_league_resolver.resolve_league_ids(
        "tennis", http_get=lambda url: _WIMBLEDON_LEAGUES, cache_path=cache)
    assert 12 not in ids
    assert set(ids) == {3336, 3824}


def _matchups(mid, home, away):
    return [{"id": mid, "parentId": None, "type": "matchup",
             "startTime": "2026-07-05T13:00:00Z",
             "participants": [{"alignment": "home", "name": home},
                               {"alignment": "away", "name": away}]}]


def _ml(mid):
    return [{"type": "moneyline", "period": 0, "matchupId": mid,
              "prices": [{"designation": "home", "price": -150},
                         {"designation": "away", "price": 130}]}]


def test_fetch_emits_events_from_both_tennis_leagues(tmp_path, monkeypatch):
    cache = tmp_path / "leagues.json"
    monkeypatch.setattr(pinnacle_league_resolver, "_DEFAULT_CACHE_PATH", cache)

    def http_get(url):
        if "/leagues?" in url:
            return _WIMBLEDON_LEAGUES
        if "/leagues/3336/matchups" in url:
            return _matchups(1, "Player A", "Player B")
        if "/leagues/3336/markets/straight" in url:
            return _ml(1)
        if "/leagues/3824/matchups" in url:
            return _matchups(2, "Player C", "Player D")
        if "/leagues/3824/markets/straight" in url:
            return _ml(2)
        raise AssertionError(f"unexpected url: {url}")

    provider = PinnacleProvider(http_get=http_get, use_cache=False)
    events = provider.fetch("tennis")
    assert isinstance(events, list)
    assert len(events) == 2
    ids = {e.event_id for e in events}
    assert ids == {"1", "2"}


def test_one_league_401_still_yields_other_and_invalidates(tmp_path, monkeypatch):
    import urllib.error

    cache = tmp_path / "leagues.json"
    monkeypatch.setattr(pinnacle_league_resolver, "_DEFAULT_CACHE_PATH", cache)
    invalidated = {"called": False}

    def fake_invalidate(sport, cache_path=None):
        invalidated["called"] = True

    monkeypatch.setattr(pinnacle_league_resolver, "invalidate", fake_invalidate)

    def http_get(url):
        if "/leagues?" in url:
            return _WIMBLEDON_LEAGUES
        if "/leagues/3336/matchups" in url:
            raise urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
        if "/leagues/3824/matchups" in url:
            return _matchups(2, "Player C", "Player D")
        if "/leagues/3824/markets/straight" in url:
            return _ml(2)
        raise AssertionError(f"unexpected url: {url}")

    provider = PinnacleProvider(http_get=http_get, use_cache=False)
    events = provider.fetch("tennis")
    assert isinstance(events, list)
    assert len(events) == 1
    assert events[0].event_id == "2"
    assert invalidated["called"] is True
