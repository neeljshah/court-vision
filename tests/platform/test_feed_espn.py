"""test_feed_espn.py — acceptance tests for the FREE ESPN odds feed.

NO network: http_get is INJECTED with synthetic ESPN-shaped JSON dicts.  Confirms
EspnFreeFeed conforms to feed.py's contract (Quote/GameOdds/OddsFeed), normalizes
American moneyLine -> decimal, parses spreads/totals, handles multi-provider +
empty-odds + date filter, and that get_feed_auto selects the right feed by env.

Python 3.9 compatible.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from scripts.platformkit.frontend.feed import GameOdds, Quote, american_to_decimal
from scripts.platformkit.frontend import feed_espn
from scripts.platformkit.frontend.feed_espn import EspnFreeFeed, get_feed_auto


# --------------------------------------------------------------------------- #
# Synthetic ESPN payload builders (scoreboard + core)                          #
# --------------------------------------------------------------------------- #

def _scoreboard(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"events": events}


def _event(eid: str, date: str, odds: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "id": eid,
        "name": "New York Knicks at San Antonio Spurs",
        "date": date,
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "San Antonio Spurs",
                                              "abbreviation": "SAS"}},
                {"homeAway": "away", "team": {"displayName": "New York Knicks",
                                              "abbreviation": "NYK"}},
            ],
            "odds": odds,
        }],
    }


def _dk_odds(name: str = "DraftKings") -> Dict[str, Any]:
    # home (SAS) -198 favorite, away (NYK) +164, spread -5.5 home, OU 216.5
    return {
        "provider": {"name": name},
        "details": "SAS -5.5",
        "overUnder": 216.5,
        "spread": -5.5,
        "homeTeamOdds": {"moneyLine": -198},
        "awayTeamOdds": {"moneyLine": 164},
    }


def _injected_get(scoreboard: Dict[str, Any], core_items: List[Dict[str, Any]] = None):
    """Return an http_get(url) closure: scoreboard URLs -> scoreboard, else core."""
    calls: List[str] = []

    def _get(url: str) -> Dict[str, Any]:
        calls.append(url)
        if "scoreboard" in url:
            return scoreboard
        return {"items": core_items or []}

    _get.calls = calls  # type: ignore[attr-defined]
    return _get


# --------------------------------------------------------------------------- #
# 1. Single DK event -> h2h/spreads/totals quotes, decimal conversion correct  #
# --------------------------------------------------------------------------- #

def test_single_event_normalizes_all_markets() -> None:
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [_dk_odds()])])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    games = feed.fetch("basketball_nba")
    assert len(games) == 1
    g = games[0]
    assert isinstance(g, GameOdds)
    assert g.home == "San Antonio Spurs"
    assert g.away == "New York Knicks"
    assert g.source == "espn_free"
    by = {(q.book, q.market, q.side): q for q in g.quotes}
    assert by[("draftkings", "h2h", "home")].decimal_odds == pytest.approx(
        american_to_decimal(-198))
    assert by[("draftkings", "h2h", "home")].decimal_odds == pytest.approx(1.50505, abs=1e-4)
    assert by[("draftkings", "h2h", "away")].decimal_odds == pytest.approx(2.64, abs=1e-4)
    assert by[("draftkings", "spreads", "home")].line == -5.5
    assert by[("draftkings", "spreads", "away")].line == 5.5
    assert by[("draftkings", "totals", "over")].line == 216.5
    assert by[("draftkings", "totals", "under")].line == 216.5
    assert all(isinstance(q, Quote) for q in g.quotes)


# --------------------------------------------------------------------------- #
# 2. Book name normalized to lowercase                                         #
# --------------------------------------------------------------------------- #

def test_book_name_lowercased() -> None:
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [_dk_odds("DraftKings")])])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    g = feed.fetch("basketball_nba")[0]
    assert {q.book for q in g.quotes} == {"draftkings"}


# --------------------------------------------------------------------------- #
# 3. Multi-provider event -> multiple books light up automatically            #
# --------------------------------------------------------------------------- #

def test_multi_provider_yields_multiple_books() -> None:
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z",
                             [_dk_odds("DraftKings"), _dk_odds("Caesars")])])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    g = feed.fetch("basketball_nba")[0]
    assert {q.book for q in g.quotes} == {"draftkings", "caesars"}


# --------------------------------------------------------------------------- #
# 4. Core endpoint adds books (and dedups identical book/market/side)         #
# --------------------------------------------------------------------------- #

def test_core_endpoint_adds_books_and_dedups() -> None:
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [_dk_odds("DraftKings")])])
    core = [_dk_odds("DraftKings"), _dk_odds("BetMGM")]  # DK dup + a new book
    feed = EspnFreeFeed(http_get=_injected_get(sb, core_items=core), fetch_core=True)
    g = feed.fetch("basketball_nba")[0]
    assert {q.book for q in g.quotes} == {"draftkings", "betmgm"}
    # dedup: only one DK h2h home quote despite appearing in scoreboard + core
    dk_home = [q for q in g.quotes if q.book == "draftkings"
               and q.market == "h2h" and q.side == "home"]
    assert len(dk_home) == 1


# --------------------------------------------------------------------------- #
# 5. Empty-odds event is skipped and counted                                   #
# --------------------------------------------------------------------------- #

def test_empty_odds_event_skipped_and_counted() -> None:
    sb = _scoreboard([
        _event("401", "2026-06-14T23:00Z", [_dk_odds()]),
        _event("402", "2026-06-14T23:00Z", []),  # no odds
    ])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    games = feed.fetch("basketball_nba")
    assert len(games) == 1
    assert feed.skipped_no_odds == 1


# --------------------------------------------------------------------------- #
# 6. Missing moneyLine/spread/OU -> that market skipped, others survive        #
# --------------------------------------------------------------------------- #

def test_missing_fields_skip_only_that_market() -> None:
    odds = {"provider": {"name": "DraftKings"}, "overUnder": 210.0,
            "spread": None, "homeTeamOdds": {"moneyLine": None},
            "awayTeamOdds": {"moneyLine": 150}}
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [odds])])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    g = feed.fetch("basketball_nba")[0]
    markets = {(q.market, q.side) for q in g.quotes}
    assert ("h2h", "away") in markets       # away ML present
    assert ("h2h", "home") not in markets   # home ML was None
    assert ("spreads", "home") not in markets  # spread None -> no spread quotes
    assert ("totals", "over") in markets    # OU present


# --------------------------------------------------------------------------- #
# 7. Date filter (YYYY-MM-DD prefix on commence_time)                          #
# --------------------------------------------------------------------------- #

def test_date_filter() -> None:
    sb = _scoreboard([
        _event("401", "2026-06-14T23:00Z", [_dk_odds()]),
        _event("402", "2026-06-15T23:00Z", [_dk_odds()]),
    ])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    games = feed.fetch("basketball_nba", date="2026-06-15")
    assert len(games) == 1
    assert games[0].commence_time.startswith("2026-06-15")


# --------------------------------------------------------------------------- #
# 8. is_live True; tennis -> [] gracefully; no urllib called when injected     #
# --------------------------------------------------------------------------- #

def test_is_live_and_tennis_empty_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # If the default urllib path were touched, this would explode the test.
    def _boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError("network must NOT be called when http_get is injected")

    monkeypatch.setattr(feed_espn.urllib.request, "urlopen", _boom)
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [_dk_odds()])])
    getter = _injected_get(sb)
    feed = EspnFreeFeed(http_get=getter, fetch_core=True)
    assert feed.is_live() is True
    # tennis_atp has no routes -> [] and no calls
    assert feed.fetch("tennis_atp") == []
    assert getter.calls == []  # type: ignore[attr-defined]
    # nba still works through the injected getter, urllib never touched
    assert len(feed.fetch("basketball_nba")) == 1


# --------------------------------------------------------------------------- #
# 9. to_board_books shape for "h2h"                                            #
# --------------------------------------------------------------------------- #

def test_to_board_books_h2h_shape() -> None:
    sb = _scoreboard([_event("401", "2026-06-14T23:00Z", [_dk_odds()])])
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    g = feed.fetch("basketball_nba")[0]
    books = feed.to_board_books(g, "h2h")
    assert len(books) == 2
    for b in books:
        assert set(b.keys()) == {"book", "market", "side", "decimal_odds", "line"}
        assert b["market"] == "h2h"


# --------------------------------------------------------------------------- #
# 10. get_feed_auto: no key -> EspnFreeFeed; key -> TheOddsApiFeed; stub force #
# --------------------------------------------------------------------------- #

def test_get_feed_auto_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.platformkit.frontend.feed import StubFeed, TheOddsApiFeed
    monkeypatch.delenv("ODDS_API_KEY", raising=False)
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    assert isinstance(get_feed_auto(), EspnFreeFeed)  # free live default

    monkeypatch.setenv("ODDS_API_KEY", "abc123")
    assert isinstance(get_feed_auto(), TheOddsApiFeed)  # paid key -> multi-book

    # force_stub overrides everything
    assert isinstance(get_feed_auto(force_stub=True), StubFeed)


# --------------------------------------------------------------------------- #
# 11. Robust: bad event / missing competitions never raises                    #
# --------------------------------------------------------------------------- #

def test_bad_events_do_not_raise() -> None:
    sb = {"events": [{"id": "x"}, {"competitions": []}, None,
                     _event("401", "2026-06-14T23:00Z", [_dk_odds()])]}
    feed = EspnFreeFeed(http_get=_injected_get(sb), fetch_core=False)
    games = feed.fetch("basketball_nba")  # must not raise
    assert len(games) == 1
