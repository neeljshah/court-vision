"""test_feed_bovada.py — acceptance tests for the FREE Bovada odds feed.

NO network: http_get is INJECTED with synthetic Bovada-shaped payloads, or
_normalize is exercised directly.  Tests confirm BovadaFreeFeed conforms to the
feed.py contract (Quote/GameOdds/OddsFeed), normalizes decimal + American prices,
parses h2h/spreads/totals, handles date filtering, empty/garbage payloads, tennis,
book label, and is_live.  Python 3.9 compatible.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from scripts.platformkit.frontend.feed import GameOdds, Quote, american_to_decimal
from scripts.platformkit.frontend.feed_bovada import BovadaFreeFeed, _SPORT_PATHS


# --- Synthetic Bovada payload builders ---

def _price(american: str, decimal: str, handicap: str = None) -> Dict[str, Any]:
    return {"american": american, "decimal": decimal, "handicap": handicap}


def _outcome(desc: str, american: str, decimal: str, handicap: str = None) -> Dict[str, Any]:
    return {"description": desc, "price": _price(american, decimal, handicap)}


def _market(description: str, outcomes: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"description": description, "outcomes": outcomes}


def _event(
    eid: str = "1234",
    start_ms: int = 1750000000000,
    home: str = "San Antonio Spurs",
    away: str = "New York Knicks",
    markets: List[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if markets is None:
        markets = _default_markets(home, away)
    return {
        "id": eid,
        "startTime": start_ms,
        "competitors": [
            {"name": home, "home": True},
            {"name": away, "home": False},
        ],
        "displayGroups": [{"markets": markets}],
    }


def _default_markets(home: str, away: str) -> List[Dict[str, Any]]:
    """Three markets with real decimal AND american prices (nominal SAS vs NYK game)."""
    return [
        _market("Moneyline", [
            _outcome("home team", "-198", "1.5051"),
            _outcome("away team", "+164", "2.64"),
        ]),
        _market("Point Spread", [
            _outcome("home team", "-110", "1.9091", "-5.5"),
            _outcome("away team", "-110", "1.9091", "5.5"),
        ]),
        _market("Total", [
            _outcome("Over", "-110", "1.9091", "216.5"),
            _outcome("Under", "-110", "1.9091", "216.5"),
        ]),
    ]


def _group(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{"events": events}]


def _injected_http(payload: Any):
    """Return an http_get callable that always returns the given payload."""
    def _get(url: str) -> Any:
        return payload
    return _get


# --- 1. _normalize: synthetic NBA coupon -> correct GameOdds ---

def test_normalize_returns_correct_gameodds() -> None:
    home = "San Antonio Spurs"
    away = "New York Knicks"
    payload = _group([_event(home=home, away=away)])
    games = BovadaFreeFeed._normalize(payload, "basketball_nba")
    assert len(games) == 1
    g = games[0]
    assert isinstance(g, GameOdds)
    assert g.home == home
    assert g.away == away
    assert g.sport == "basketball_nba"
    assert g.source == "bovada_free"
    assert len(g.quotes) > 0


def test_normalize_h2h_quotes_correct() -> None:
    payload = _group([_event()])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    by = {(q.market, q.side): q for q in g.quotes}
    assert ("h2h", "home") in by
    assert ("h2h", "away") in by
    assert by[("h2h", "home")].decimal_odds == pytest.approx(1.5051, abs=1e-3)
    assert by[("h2h", "away")].decimal_odds == pytest.approx(2.64, abs=1e-3)


def test_normalize_spreads_quotes_correct() -> None:
    payload = _group([_event()])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    by = {(q.market, q.side): q for q in g.quotes}
    assert ("spreads", "home") in by
    assert ("spreads", "away") in by
    assert by[("spreads", "home")].line == pytest.approx(-5.5, abs=1e-3)
    assert by[("spreads", "away")].line == pytest.approx(5.5, abs=1e-3)
    assert by[("spreads", "home")].decimal_odds == pytest.approx(1.9091, abs=1e-3)


def test_normalize_totals_quotes_correct() -> None:
    payload = _group([_event()])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    by = {(q.market, q.side): q for q in g.quotes}
    assert ("totals", "over") in by
    assert ("totals", "under") in by
    assert by[("totals", "over")].line == pytest.approx(216.5, abs=1e-3)
    assert by[("totals", "under")].line == pytest.approx(216.5, abs=1e-3)


def test_normalize_quote_types_are_correct() -> None:
    payload = _group([_event()])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    assert all(isinstance(q, Quote) for q in g.quotes)


# --- 2. American fallback when decimal is missing / empty ---

def test_american_fallback_when_decimal_missing() -> None:
    """When price.decimal is absent or non-numeric, fall back to american_to_decimal."""
    markets = [
        _market("Moneyline", [
            {"description": "home team", "price": {"american": "-200", "decimal": None}},
            {"description": "away team", "price": {"american": "+170", "decimal": ""}},
        ])
    ]
    payload = _group([_event(markets=markets)])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    by = {(q.market, q.side): q for q in g.quotes}
    assert ("h2h", "home") in by
    assert ("h2h", "away") in by
    assert by[("h2h", "home")].decimal_odds == pytest.approx(american_to_decimal(-200), abs=1e-4)
    assert by[("h2h", "away")].decimal_odds == pytest.approx(american_to_decimal(170), abs=1e-4)


def test_no_quote_when_both_decimal_and_american_absent() -> None:
    """Outcome with no parseable price at all is silently dropped."""
    markets = [
        _market("Moneyline", [
            {"description": "home team", "price": {"american": None, "decimal": None}},
        ])
    ]
    payload = _group([_event(markets=markets)])
    games = BovadaFreeFeed._normalize(payload, "basketball_nba")
    # event has no quotes -> skipped
    assert games == []


# --- 3. fetch() with injected http_get -> games + date filter ---

def test_fetch_with_injected_getter_returns_games() -> None:
    start_ms = 1750000000000  # 2025-06-15T13:46:40Z roughly
    payload = _group([_event(start_ms=start_ms)])
    feed = BovadaFreeFeed(http_get=_injected_http(payload))
    games = feed.fetch("basketball_nba")
    assert len(games) == 1
    assert isinstance(games[0], GameOdds)


def test_fetch_date_filter_keeps_matching() -> None:
    # startTime 1750000000000 ms = 2025-06-15T...
    payload = _group([_event(start_ms=1750000000000)])
    feed = BovadaFreeFeed(http_get=_injected_http(payload))
    # Derive the date from what the feed actually parsed
    assert len(feed.fetch("basketball_nba")) == 1
    date = feed.fetch("basketball_nba")[0].commence_time[:10]
    result = feed.fetch("basketball_nba", date=date)
    assert len(result) == 1


def test_fetch_date_filter_drops_non_matching() -> None:
    payload = _group([_event(start_ms=1750000000000)])
    feed = BovadaFreeFeed(http_get=_injected_http(payload))
    # Use a date that is clearly in the past (will not match)
    games = feed.fetch("basketball_nba", date="2000-01-01")
    assert games == []


# --- 4. Empty / garbage payload -> [] no raise ---

def test_empty_list_payload_returns_empty() -> None:
    assert BovadaFreeFeed._normalize([], "basketball_nba") == []


def test_none_payload_returns_empty() -> None:
    assert BovadaFreeFeed._normalize(None, "basketball_nba") == []


def test_garbage_string_payload_returns_empty() -> None:
    assert BovadaFreeFeed._normalize("garbage", "basketball_nba") == []


def test_empty_events_list_returns_empty() -> None:
    payload = [{"events": []}]
    assert BovadaFreeFeed._normalize(payload, "basketball_nba") == []


def test_event_with_no_quotes_skipped() -> None:
    """An event whose markets produce no valid quotes is dropped."""
    ev = _event(markets=[_market("Moneyline", [])])
    payload = _group([ev])
    assert BovadaFreeFeed._normalize(payload, "basketball_nba") == []


def test_garbage_event_entry_skipped_gracefully() -> None:
    """Malformed event entries are skipped; valid sibling still returned."""
    valid = _event()
    payload = [{"events": [None, "bad", {}, valid]}]
    games = BovadaFreeFeed._normalize(payload, "basketball_nba")
    assert len(games) == 1


def test_fetch_returns_empty_on_http_returning_garbage() -> None:
    feed = BovadaFreeFeed(http_get=_injected_http("not a list"))
    games = feed.fetch("basketball_nba")
    assert games == []


# --- 5. tennis -> [] gracefully ---

def test_tennis_returns_empty_list() -> None:
    """tennis_atp has no Bovada routes; fetch must return [] without network."""
    calls: List[str] = []

    def _boom(url: str) -> Any:
        calls.append(url)
        raise AssertionError("network must NOT be called for tennis")

    feed = BovadaFreeFeed(http_get=_boom)
    result = feed.fetch("tennis_atp")
    assert result == []
    assert calls == []  # no URL was attempted


def test_tennis_not_in_sport_paths() -> None:
    assert _SPORT_PATHS.get("tennis_atp") == []


# --- 6. is_live True ---

def test_is_live_true() -> None:
    feed = BovadaFreeFeed(http_get=_injected_http([]))
    assert feed.is_live() is True


# --- 7. book label is lowercase "bovada" ---

def test_book_label_is_bovada_lowercase() -> None:
    payload = _group([_event()])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    assert all(q.book == "bovada" for q in g.quotes)


# --- 8. commence_time parsed from epoch ms ---

def test_commence_time_is_iso_string() -> None:
    payload = _group([_event(start_ms=1750000000000)])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    assert g.commence_time is not None
    assert "T" in g.commence_time
    assert g.commence_time.endswith("Z")


# --- 9. game_id conforms to contract: {sport}:{date}:{away}@{home} ---

def test_game_id_format() -> None:
    home = "San Antonio Spurs"
    away = "New York Knicks"
    payload = _group([_event(home=home, away=away, start_ms=1750000000000)])
    g = BovadaFreeFeed._normalize(payload, "basketball_nba")[0]
    parts = g.game_id.split(":")
    assert parts[0] == "basketball_nba"
    assert parts[2] == f"{away}@{home}"
