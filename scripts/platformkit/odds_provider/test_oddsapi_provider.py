"""Per-file unit tests for oddsapi_provider (NETWORK-FREE, ENV-isolated).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_oddsapi_provider.py -q

Every test uses canned payloads + an injected http_get; nothing touches the network.
ENV is overridden in-process (not globally) via monkeypatch or direct os.environ pops.

Acceptance criteria (LS-04):
  A) canned multi-book payload -> >=3 distinct venue names, all decimal prices >1.0
  B) key-absent (ODDS_API_KEY unset) -> UNAVAILABLE with informative reason
  C) malformed payload -> UNAVAILABLE (or empty event list), no crash, no fake price
  D) no $/edge fabrication -- venue labels are "oddsapi:<BookTitle>", NO price field
     contains a fabricated number (all from canned input or absent).
"""
from __future__ import annotations

import math
import os
from typing import Any, List
from unittest.mock import patch

import pytest

from scripts.platformkit.odds_provider import base
from scripts.platformkit.odds_provider.oddsapi_provider import (
    OddsApiProvider,
    _parse_h2h,
    _parse_spread,
    _parse_total,
    parse_bookmakers,
    parse_events,
)


# --------------------------------------------------------------------------- #
# Canned Odds API v4 payload (mirrors live shape; prices all >1.0 decimal).
# --------------------------------------------------------------------------- #
CANNED_EVENTS: List[Any] = [
    {
        "id": "evt_nba_001",
        "sport_key": "basketball_nba",
        "commence_time": "2026-06-20T00:00:00Z",
        "home_team": "Boston Celtics",
        "away_team": "Los Angeles Lakers",
        "bookmakers": [
            {
                "key": "draftkings", "title": "DraftKings", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.75},
                        {"name": "Los Angeles Lakers", "price": 2.15},
                    ]},
                    {"key": "spreads", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.91, "point": -4.5},
                        {"name": "Los Angeles Lakers", "price": 1.91, "point":  4.5},
                    ]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over",  "price": 1.91, "point": 222.5},
                        {"name": "Under", "price": 1.91, "point": 222.5},
                    ]},
                ],
            },
            {
                "key": "fanduel", "title": "FanDuel", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.77},
                        {"name": "Los Angeles Lakers", "price": 2.10},
                    ]},
                ],
            },
            {
                "key": "betmgm", "title": "BetMGM", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.73},
                        {"name": "Los Angeles Lakers", "price": 2.18},
                    ]},
                    {"key": "spreads", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.89, "point": -4.5},
                        {"name": "Los Angeles Lakers", "price": 1.93, "point":  4.5},
                    ]},
                ],
            },
            {
                "key": "caesars", "title": "Caesars", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.76},
                        {"name": "Los Angeles Lakers", "price": 2.12},
                    ]},
                ],
            },
            {
                "key": "pointsbetus", "title": "PointsBet (US)", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.80},
                        {"name": "Los Angeles Lakers", "price": 2.05},
                    ]},
                    {"key": "totals", "outcomes": [
                        {"name": "Over",  "price": 1.90, "point": 222.5},
                        {"name": "Under", "price": 1.92, "point": 222.5},
                    ]},
                ],
            },
        ],
    },
    {
        "id": "evt_nba_002",
        "sport_key": "basketball_nba",
        "commence_time": "2026-06-20T02:00:00Z",
        "home_team": "Golden State Warriors",
        "away_team": "Miami Heat",
        "bookmakers": [
            {
                "key": "draftkings", "title": "DraftKings", "last_update": "2026-06-20T00:00Z",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Golden State Warriors", "price": 1.65},
                        {"name": "Miami Heat",            "price": 2.30},
                    ]},
                ],
            },
        ],
    },
]

_KEY = "test-key-abc123"


def _stub_ok(url: str) -> Any:
    """Canned http_get that returns the multi-book payload."""
    return CANNED_EVENTS


def _stub_bad(url: str) -> Any:
    """Returns a malformed (non-list) payload."""
    return {"error": "bad response"}


def _stub_empty(url: str) -> Any:
    """Returns a valid list with no events."""
    return []


def _stub_crash(url: str) -> Any:
    raise OSError("network down")


# --------------------------------------------------------------------------- #
# A) canned multi-book payload -> >=3 distinct venue names, prices all >1.0
# --------------------------------------------------------------------------- #

def test_canned_payload_distinct_venues_and_prices():
    """Acceptance A: canned payload -> >=3 distinct venue names, all prices >1.0."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        provider = OddsApiProvider(http_get=_stub_ok, use_cache=False)
        result = provider.fetch("nba")
    assert isinstance(result, list), "expected list of OddsEvent, not UNAVAILABLE"
    assert len(result) >= 1

    first_ev = result[0]
    venues = list(first_ev.prices.keys())
    assert len(venues) >= 3, (
        f"expected >=3 distinct venues in first event, got {len(venues)}: {venues}")

    # All venue labels are "oddsapi:<BookTitle>" -- no raw sportsbook keys leaked
    for v in venues:
        assert v.startswith("oddsapi:"), f"venue label '{v}' missing 'oddsapi:' prefix"

    # All prices are decimal > 1.0 (no fabricated sub-1 probabilities)
    for venue, sides in first_ev.prices.items():
        for side, val in sides.items():
            if side in ("spread", "total"):
                continue  # nested dicts, checked below
            if val is not None:
                assert isinstance(val, float), f"{venue}.{side} is not a float"
                assert val > 1.0, f"{venue}.{side}={val} is not > 1.0"

    # Spread and total sub-nodes carry >1.0 odds where present
    for venue, sides in first_ev.prices.items():
        for mkt_key, mkt_val in sides.items():
            if mkt_key == "spread" and isinstance(mkt_val, dict):
                for team_key, node in mkt_val.items():
                    assert node["odds"] > 1.0, (
                        f"spread odds for {venue}.{team_key}={node['odds']} not >1.0")
            if mkt_key == "total" and isinstance(mkt_val, dict):
                for side_key, node in mkt_val.items():
                    assert node["odds"] > 1.0, (
                        f"total odds for {venue}.{side_key}={node['odds']} not >1.0")


def test_five_venues_returned_for_first_event():
    """All 5 canned bookmakers appear as distinct venues in the first event."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert isinstance(result, list)
    venues = set(result[0].prices.keys())
    assert "oddsapi:DraftKings" in venues
    assert "oddsapi:FanDuel" in venues
    assert "oddsapi:BetMGM" in venues
    assert "oddsapi:Caesars" in venues
    assert "oddsapi:PointsBet (US)" in venues


def test_home_away_prices_match_canned_values():
    """Prices for the first event / DraftKings match the canned payload exactly."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    ev = result[0]
    dk = ev.prices["oddsapi:DraftKings"]
    assert math.isclose(dk["home"], 1.75, rel_tol=1e-6)
    assert math.isclose(dk["away"], 2.15, rel_tol=1e-6)


def test_spread_and_total_parsed_for_draftkings():
    """Spread and total sub-nodes present for DraftKings (both sides quoted in canned)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    dk = result[0].prices["oddsapi:DraftKings"]
    assert "spread" in dk
    assert "total" in dk
    assert math.isclose(dk["spread"]["home"]["line"], -4.5)
    assert math.isclose(dk["total"]["over"]["line"], 222.5)


def test_source_and_as_of_set():
    """Event source is 'oddsapi' and as_of is a non-empty ISO timestamp."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    ev = result[0]
    assert ev.source == "oddsapi"
    assert ev.as_of  # non-empty
    assert ev.commence_time == "2026-06-20T00:00:00Z"


# --------------------------------------------------------------------------- #
# B) key-absent -> UNAVAILABLE with reason
# --------------------------------------------------------------------------- #

def test_key_absent_returns_unavailable():
    """Acceptance B: ODDS_API_KEY absent -> unavailable sentinel, reason stated."""
    env = {k: v for k, v in os.environ.items() if k != "ODDS_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert base.is_unavailable(result), "expected UNAVAILABLE when key absent"
    assert "ODDS_API_KEY" in result.get("reason", ""), (
        f"reason should mention the missing key, got: {result}")


def test_key_blank_returns_unavailable():
    """Blank/whitespace ODDS_API_KEY treated as absent."""
    with patch.dict(os.environ, {"ODDS_API_KEY": "   "}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert base.is_unavailable(result)


# --------------------------------------------------------------------------- #
# C) malformed payload -> UNAVAILABLE or empty list, no crash, no fake price
# --------------------------------------------------------------------------- #

def test_malformed_payload_returns_unavailable():
    """Acceptance C: non-list payload -> UNAVAILABLE (not a crash)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_bad, use_cache=False).fetch("nba")
    assert base.is_unavailable(result), "non-list payload should be UNAVAILABLE"
    assert "shape" in result.get("reason", "")


def test_network_error_returns_unavailable():
    """Network exception -> UNAVAILABLE with error class in reason."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_crash, use_cache=False).fetch("nba")
    assert base.is_unavailable(result)
    assert "OSError" in result.get("reason", "")


def test_empty_payload_returns_empty_list():
    """Empty list payload -> empty list (not UNAVAILABLE -- just no games)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_empty, use_cache=False).fetch("nba")
    assert isinstance(result, list)
    assert result == []


def test_unsupported_sport_returns_unavailable():
    """Unknown sport key -> UNAVAILABLE with sport name in reason."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = OddsApiProvider(http_get=_stub_ok, use_cache=False).fetch("cricket")
    assert base.is_unavailable(result)
    assert "cricket" in result.get("reason", "")


def test_malformed_bookmaker_entry_skipped_not_crash():
    """A bookmaker entry that is completely bad (None / wrong type) is skipped."""
    bad_payload = [
        {
            "id": "x1",
            "home_team": "Team A", "away_team": "Team B",
            "commence_time": None,
            "bookmakers": [
                None,                       # None entry
                {"key": "dk", "title": "DraftKings",
                 "markets": [{"key": "h2h", "outcomes": [
                     {"name": "Team A", "price": 1.95},
                     {"name": "Team B", "price": 1.90},
                 ]}]},
            ],
        }
    ]
    # parse_events should not crash and should surface the valid DK entry
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        def _stub_bad_bk(_url: str) -> Any:
            return bad_payload
        result = OddsApiProvider(http_get=_stub_bad_bk, use_cache=False).fetch("nba")
    assert isinstance(result, list)
    assert len(result) == 1
    assert "oddsapi:DraftKings" in result[0].prices


def test_event_missing_home_away_skipped():
    """Event missing home_team/away_team is silently skipped."""
    bad = [{"id": "y1", "bookmakers": []}]
    events = parse_events(bad, "nba")
    assert events == []


# --------------------------------------------------------------------------- #
# D) No fabricated prices -- pure parser unit tests
# --------------------------------------------------------------------------- #

def test_parse_h2h_correct_values():
    outcomes = [
        {"name": "Boston Celtics", "price": 1.75},
        {"name": "Los Angeles Lakers", "price": 2.15},
    ]
    result = _parse_h2h(outcomes, "Boston Celtics", "Los Angeles Lakers")
    assert math.isclose(result["home"], 1.75)
    assert math.isclose(result["away"], 2.15)


def test_parse_h2h_missing_side_not_fabricated():
    """If one team is missing from h2h, its side is absent (not fabricated)."""
    outcomes = [{"name": "Boston Celtics", "price": 1.75}]
    result = _parse_h2h(outcomes, "Boston Celtics", "Los Angeles Lakers")
    assert "home" in result
    assert "away" not in result  # not fabricated


def test_parse_h2h_sub1_price_rejected():
    """A price <= 1.0 from the API is rejected as invalid decimal odds."""
    outcomes = [
        {"name": "Boston Celtics", "price": 0.60},   # implied prob, not decimal
        {"name": "Los Angeles Lakers", "price": 2.10},
    ]
    result = _parse_h2h(outcomes, "Boston Celtics", "Los Angeles Lakers")
    assert "home" not in result   # 0.60 rejected
    assert math.isclose(result["away"], 2.10)


def test_parse_spread_both_sides():
    outcomes = [
        {"name": "Boston Celtics",     "price": 1.91, "point": -4.5},
        {"name": "Los Angeles Lakers", "price": 1.91, "point":  4.5},
    ]
    node = _parse_spread(outcomes, "Boston Celtics", "Los Angeles Lakers")
    assert node is not None
    assert math.isclose(node["home"]["line"], -4.5)
    assert math.isclose(node["away"]["line"],  4.5)
    assert math.isclose(node["home"]["odds"], 1.91)


def test_parse_spread_missing_side_returns_none():
    """If only one side of spread is quoted, the node is omitted (never half-fabricated)."""
    outcomes = [{"name": "Boston Celtics", "price": 1.91, "point": -4.5}]
    assert _parse_spread(outcomes, "Boston Celtics", "Los Angeles Lakers") is None


def test_parse_total_both_sides():
    outcomes = [
        {"name": "Over",  "price": 1.91, "point": 222.5},
        {"name": "Under", "price": 1.91, "point": 222.5},
    ]
    node = _parse_total(outcomes)
    assert node is not None
    assert math.isclose(node["over"]["line"], 222.5)
    assert math.isclose(node["under"]["odds"], 1.91)


def test_parse_total_missing_under_returns_none():
    outcomes = [{"name": "Over", "price": 1.91, "point": 222.5}]
    assert _parse_total(outcomes) is None


def test_parse_bookmakers_no_dollar_field():
    """parse_bookmakers output has no 'edge', 'roi', or '$' key anywhere."""
    event = CANNED_EVENTS[0]
    result = parse_bookmakers(event)
    for venue, sides in result.items():
        for k in sides:
            assert "$" not in k
            assert k not in ("edge", "roi", "profit", "return")


def test_parse_events_pure_on_canned():
    """parse_events on the full canned payload returns correct team names + event ids."""
    events = parse_events(CANNED_EVENTS, "nba")
    assert len(events) == 2
    assert events[0].home == "Boston Celtics"
    assert events[0].away == "Los Angeles Lakers"
    assert events[0].event_id == "evt_nba_001"
    assert len(events[0].venues()) >= 5


# --------------------------------------------------------------------------- #
# venue_type -- oddsapi venues are sportsbooks (not prediction markets)
# --------------------------------------------------------------------------- #

def test_oddsapi_venues_are_sportsbooks():
    """oddsapi: prefix classifies as VENUE_SPORTSBOOK (real books, not PMs)."""
    for label in ("oddsapi:DraftKings", "oddsapi:FanDuel", "oddsapi:BetMGM"):
        assert base.venue_type(label) == base.VENUE_SPORTSBOOK, (
            f"{label} should be VENUE_SPORTSBOOK")
        assert not base.is_prediction_market(label)
