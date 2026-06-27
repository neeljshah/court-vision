"""Per-file unit tests for scripts.platformkit.odds_provider.pinnacle (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_pinnacle.py -q

Every test uses CANNED payloads + an injected http_get; nothing here touches the
network. Covers: happy-path parsing, designation fallback, empty payload -> [],
network failure -> UNAVAILABLE, unsupported sport -> UNAVAILABLE, and registration
in aggregate.default_providers.
"""
from __future__ import annotations

import math
import sys
import os

# Ensure the project root is on sys.path so imports resolve correctly.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.platformkit.odds_provider.pinnacle import (
    PinnacleProvider, parse_games, _LEAGUE_ID)
from scripts.platformkit.odds_provider.base import (
    is_unavailable, VENUE_SPORTSBOOK, venue_type)


# ---------------------------------------------------------------------------
# Canned payloads -- shape mirrors live probes of guest.api.arcadia.pinnacle.com
# ---------------------------------------------------------------------------

# Minimal parent matchup for BOS vs LAL, NBA game.
MATCHUP_BOS_LAL = {
    "id": 1234567,
    "type": "matchup",
    "startTime": "2026-06-20T01:00:00Z",
    "participants": [
        {"alignment": "home", "name": "Boston Celtics"},
        {"alignment": "away", "name": "Los Angeles Lakers"},
    ],
}

# A "special" prop matchup (should be skipped by the parser).
MATCHUP_PROP_SPECIAL = {
    "id": 9999001,
    "type": "special",
    "parentId": 1234567,
    "special": {"category": "Player Props", "description": "LeBron James Total Points"},
    "units": "Points",
    "participants": [],
}

# Straight moneyline market for game 1234567, period 0 (full game).
MARKET_ML_P0 = {
    "matchupId": 1234567,
    "type": "moneyline",
    "period": 0,
    "prices": [
        {"designation": "home", "price": -150},  # Boston favored
        {"designation": "away", "price": 130},   # Lakers underdog
    ],
}

# Period 1 (Q1 line) -- should be IGNORED (period != 0).
MARKET_ML_P1 = {
    "matchupId": 1234567,
    "type": "moneyline",
    "period": 1,
    "prices": [
        {"designation": "home", "price": -120},
        {"designation": "away", "price": 100},
    ],
}

# Spread market -- not moneyline, should be ignored by the moneyline-only parser.
MARKET_SPREAD = {
    "matchupId": 1234567,
    "type": "spread",
    "period": 0,
    "prices": [
        {"designation": "home", "price": -110, "points": -3.5},
        {"designation": "away", "price": -110, "points": 3.5},
    ],
}

CANNED_MATCHUPS = [MATCHUP_BOS_LAL, MATCHUP_PROP_SPECIAL]
CANNED_MARKETS = [MARKET_ML_P0, MARKET_ML_P1, MARKET_SPREAD]


def _stub_ok(matchups_body, markets_body):
    """Return an http_get stub that serves canned bodies for the two Pinnacle URLs."""
    def _get(url):
        if "matchups" in url and "related" not in url and "markets" not in url:
            return matchups_body
        if "markets/straight" in url:
            return markets_body
        raise AssertionError(f"unexpected URL in test: {url}")
    return _get


def _stub_error():
    """An http_get that always raises OSError (simulates total network failure)."""
    def _get(url):
        raise OSError("network down")
    return _get


# ---------------------------------------------------------------------------
# Happy-path: canned fixture -> >=1 OddsEvent venue='pinnacle', decimal > 1.0
# ---------------------------------------------------------------------------

def test_parse_games_produces_odds_event():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    assert len(events) == 1
    ev = events[0]
    assert ev.home == "Boston Celtics"
    assert ev.away == "Los Angeles Lakers"
    assert ev.sport == "nba"
    assert ev.source == "pinnacle"
    assert "pinnacle" in ev.prices


def test_parse_games_decimal_prices_above_one():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    ev = events[0]
    sides = ev.prices["pinnacle"]
    # home -150 American -> 1 + 100/150 = 1.6667
    assert "home" in sides and sides["home"] > 1.0
    assert math.isclose(sides["home"], 1.0 + 100.0 / 150.0, rel_tol=1e-6)
    # away +130 American -> 1 + 130/100 = 2.30
    assert "away" in sides and sides["away"] > 1.0
    assert math.isclose(sides["away"], 2.30, rel_tol=1e-6)


def test_parse_games_venue_is_pinnacle():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    ev = events[0]
    assert list(ev.prices.keys()) == ["pinnacle"]


def test_parse_games_venue_type_is_sportsbook():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    ev = events[0]
    for v in ev.prices:
        assert venue_type(v) == VENUE_SPORTSBOOK


def test_parse_games_ignores_period_1_and_spread_markets():
    # Only the period=0 moneyline should produce prices; period=1 and spread skipped.
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    ev = events[0]
    # If period-1 prices were included, we might see a different decimal for home.
    sides = ev.prices["pinnacle"]
    # home from period-0 is -150 (1.6667), NOT -120 from period-1 (1.8333).
    assert math.isclose(sides["home"], 1.0 + 100.0 / 150.0, rel_tol=1e-6)


def test_parse_games_skips_special_matchup():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    # Only 1 parent game, the special prop matchup is not a separate OddsEvent.
    assert len(events) == 1


def test_parse_games_skips_missing_team_names():
    bad_matchup = {
        "id": 555, "type": "matchup",
        "startTime": "2026-06-20T02:00:00Z",
        "participants": [{"alignment": "home", "name": ""}],  # away absent
    }
    events = parse_games([bad_matchup], CANNED_MARKETS, "nba")
    assert events == []


# ---------------------------------------------------------------------------
# Empty payload -> [] (no exception)
# ---------------------------------------------------------------------------

def test_parse_games_empty_matchups_returns_empty():
    events = parse_games([], CANNED_MARKETS, "nba")
    assert events == []


def test_parse_games_empty_markets_returns_event_without_prices():
    # Event still emitted (game exists), but prices dict is empty (no ML market).
    events = parse_games(CANNED_MATCHUPS, [], "nba")
    assert len(events) == 1
    assert events[0].prices == {}


def test_provider_empty_matchups_returns_empty_list():
    http = _stub_ok([], [])
    provider = PinnacleProvider(http_get=http, use_cache=False)
    result = provider.fetch("nba")
    assert isinstance(result, list)
    assert result == []


# ---------------------------------------------------------------------------
# Designation fallback: when designation is absent, use index order.
# ---------------------------------------------------------------------------

def test_parse_games_designation_fallback():
    market_no_desig = {
        "matchupId": 1234567,
        "type": "moneyline",
        "period": 0,
        "prices": [
            {"price": -110},   # index 0 -> home
            {"price": -110},   # index 1 -> away
        ],
    }
    events = parse_games([MATCHUP_BOS_LAL], [market_no_desig], "nba")
    assert len(events) == 1
    sides = events[0].prices["pinnacle"]
    assert "home" in sides and "away" in sides
    assert math.isclose(sides["home"], 1.0 + 100.0 / 110.0, rel_tol=1e-6)
    assert math.isclose(sides["away"], 1.0 + 100.0 / 110.0, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Network / key absent -> UNAVAILABLE sentinel, honest, never raises.
# ---------------------------------------------------------------------------

def test_provider_network_failure_returns_unavailable():
    provider = PinnacleProvider(http_get=_stub_error(), use_cache=False)
    result = provider.fetch("nba")
    assert is_unavailable(result)
    assert "failed" in result.get("reason", "")


def test_provider_markets_failure_returns_unavailable():
    """Matchups OK but markets call fails -> UNAVAILABLE (no partial data)."""
    call_count = [0]
    def _get(url):
        call_count[0] += 1
        if "matchups" in url and "markets" not in url:
            return CANNED_MATCHUPS
        raise OSError("markets down")
    provider = PinnacleProvider(http_get=_get, use_cache=False)
    result = provider.fetch("nba")
    assert is_unavailable(result)


def test_provider_unexpected_matchups_shape_returns_unavailable():
    # If the API returns a non-list (e.g. an error dict), degrade honestly.
    def _get(url):
        return {"error": "unavailable"}
    provider = PinnacleProvider(http_get=_get, use_cache=False)
    result = provider.fetch("nba")
    assert is_unavailable(result)


def test_provider_unexpected_markets_shape_returns_unavailable():
    def _get(url):
        if "matchups" in url and "markets" not in url:
            return CANNED_MATCHUPS
        return "not a list"
    provider = PinnacleProvider(http_get=_get, use_cache=False)
    result = provider.fetch("nba")
    assert is_unavailable(result)


# ---------------------------------------------------------------------------
# Unsupported sport -> UNAVAILABLE.
# ---------------------------------------------------------------------------

def test_provider_unsupported_sport_returns_unavailable():
    provider = PinnacleProvider(http_get=_stub_error(), use_cache=False)
    result = provider.fetch("cricket")
    assert is_unavailable(result)
    assert "unsupported" in result.get("reason", "")


def test_provider_fetch_never_raises():
    provider = PinnacleProvider(http_get=_stub_error(), use_cache=False)
    try:
        result = provider.fetch("nba")
    except Exception as exc:
        raise AssertionError(f"fetch() raised unexpectedly: {exc}") from exc
    assert is_unavailable(result)


# ---------------------------------------------------------------------------
# No $ field anywhere in results.
# ---------------------------------------------------------------------------

def test_no_dollar_field_in_event():
    events = parse_games(CANNED_MATCHUPS, CANNED_MARKETS, "nba")
    for ev in events:
        d = ev.to_dict()
        for key in d:
            assert "$" not in key, f"Dollar field found in event dict key: {key}"
        for v, sides in ev.prices.items():
            for k in sides:
                assert "$" not in k, f"Dollar field in price sides key: {k}"


# ---------------------------------------------------------------------------
# Provider is registerable in aggregate.default_providers pattern.
# ---------------------------------------------------------------------------

def test_provider_satisfies_protocol():
    """PinnacleProvider has .name and .fetch() -- satisfies the Provider protocol."""
    from scripts.platformkit.odds_provider.base import Provider
    provider = PinnacleProvider(http_get=_stub_ok(CANNED_MATCHUPS, CANNED_MARKETS),
                                use_cache=False)
    assert isinstance(provider, Provider)
    assert provider.name == "pinnacle"
    result = provider.fetch("nba")
    assert isinstance(result, list) and len(result) >= 1


def test_league_id_map_covers_expected_sports():
    for sport in ("nba", "mlb", "soccer", "soccer_intl", "tennis"):
        assert sport in _LEAGUE_ID, f"Missing league ID for sport '{sport}'"
        assert isinstance(_LEAGUE_ID[sport], int)


def test_provider_integrates_with_aggregate():
    """PinnacleProvider can be passed as a provider to aggregate.aggregate()."""
    from scripts.platformkit.odds_provider.aggregate import aggregate

    http = _stub_ok(CANNED_MATCHUPS, CANNED_MARKETS)
    provider = PinnacleProvider(http_get=http, use_cache=False)
    payload = aggregate("nba", [provider])
    assert payload["sport"] == "nba"
    assert payload["sources"].get("pinnacle") == "ok"
    assert len(payload["events"]) >= 1
    ev = payload["events"][0]
    assert "pinnacle" in ev["prices"]


def test_provider_in_default_providers_registration():
    """PinnacleProvider can be added to the default stack and runs through aggregate."""
    from scripts.platformkit.odds_provider.aggregate import default_providers, aggregate

    http = _stub_ok(CANNED_MATCHUPS, CANNED_MARKETS)

    # Construct the standard stack + add our Pinnacle provider.
    def _noop(url):
        # Stub for the other providers -- return empty/valid bodies.
        if "espn" in url or "site.api" in url:
            return {"events": []}
        if "kalshi" in url or "elections" in url:
            return {"markets": []}
        if "gamma" in url or "polymarket" in url:
            return []
        # Pinnacle calls handled by http
        return http(url)

    pin_provider = PinnacleProvider(http_get=http, use_cache=False)
    from scripts.platformkit.odds_provider.espn import EspnProvider
    from scripts.platformkit.odds_provider.kalshi import KalshiProvider
    from scripts.platformkit.odds_provider.polymarket import PolymarketProvider
    providers = [
        EspnProvider(http_get=_noop, use_cache=False),
        KalshiProvider(http_get=_noop, use_cache=False),
        PolymarketProvider(http_get=_noop, use_cache=False),
        pin_provider,
    ]
    payload = aggregate("nba", providers)
    assert payload["sources"].get("pinnacle") == "ok"
    assert any("pinnacle" in ev["prices"] for ev in payload["events"])
