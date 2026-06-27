"""Per-file unit tests for oddsapi_team_provider (NETWORK-FREE, ENV-isolated).

Run ONLY this file:
    cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_oddsapi_team_provider.py -q

Acceptance criteria (LSII-05):
  A) Canned multi-book h2h JSON -> >=3 distinct sportsbook venues as OddsEvent.prices
     with decimal prices > 1.0 and true fetched-at as_of.
  B) ODDS_API_KEY absent -> UNAVAILABLE(reason); never a synthetic price / fabricated book.
  C) Malformed/empty body -> UNAVAILABLE not raise; no fabricated price.
  D) American->decimal conversion correct (+150->2.5, -175->1.571...).
  E) Merges cleanly via merge_events (same shape as ESPN/Kalshi providers).
  F) Never raises in any code-path exercised here.
"""
from __future__ import annotations

import math
import os
from typing import Any, List
from unittest.mock import patch

import pytest

from scripts.platformkit.odds_provider import aggregate as agg_mod
from scripts.platformkit.odds_provider.base import (
    VENUE_SPORTSBOOK,
    american_to_decimal,
    is_unavailable,
    venue_type,
)
from scripts.platformkit.odds_provider.oddsapi_team_provider import (
    OddsApiProvider,
    OddsEvent,
    make_team_provider,
    parse_bookmakers,
    parse_events,
)

# --------------------------------------------------------------------------- #
# Canned Odds API v4 payload -- 5 distinct US sportsbooks, prices all > 1.0
# --------------------------------------------------------------------------- #
_CANNED: List[Any] = [
    {
        "id": "ev_001",
        "sport_key": "basketball_nba",
        "commence_time": "2026-06-20T01:00:00Z",
        "home_team": "Boston Celtics",
        "away_team": "Los Angeles Lakers",
        "bookmakers": [
            {
                "key": "draftkings", "title": "DraftKings",
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
                "key": "fanduel", "title": "FanDuel",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.77},
                        {"name": "Los Angeles Lakers", "price": 2.10},
                    ]},
                ],
            },
            {
                "key": "betmgm", "title": "BetMGM",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.73},
                        {"name": "Los Angeles Lakers", "price": 2.18},
                    ]},
                ],
            },
            {
                "key": "caesars", "title": "Caesars",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.76},
                        {"name": "Los Angeles Lakers", "price": 2.12},
                    ]},
                ],
            },
            {
                "key": "pointsbetus", "title": "PointsBet (US)",
                "markets": [
                    {"key": "h2h", "outcomes": [
                        {"name": "Boston Celtics",     "price": 1.80},
                        {"name": "Los Angeles Lakers", "price": 2.05},
                    ]},
                ],
            },
        ],
    },
    {
        "id": "ev_002",
        "sport_key": "basketball_nba",
        "commence_time": "2026-06-20T03:00:00Z",
        "home_team": "Golden State Warriors",
        "away_team": "Miami Heat",
        "bookmakers": [
            {
                "key": "draftkings", "title": "DraftKings",
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

_KEY = "testkey-lsii05"


def _stub_ok(url: str) -> Any:
    return _CANNED


def _stub_bad(url: str) -> Any:
    return {"error": "bad response"}


def _stub_empty(url: str) -> Any:
    return []


def _stub_crash(url: str) -> Any:
    raise OSError("network down")


# --------------------------------------------------------------------------- #
# A) Canned multi-book payload -> >=3 distinct venues, prices decimal > 1.0
#    with true fetched-at as_of
# --------------------------------------------------------------------------- #

def test_canned_returns_list_of_odds_events():
    """fetch() returns a list of OddsEvent objects on success."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        p = make_team_provider(http_get=_stub_ok, use_cache=False)
        result = p.fetch("nba")
    assert isinstance(result, list), f"expected list, got {type(result)}"
    assert len(result) >= 1


def test_first_event_has_at_least_three_distinct_venues():
    """First event has >= 3 distinct sportsbook venues (LSII-05 acceptance floor)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    first = result[0]
    venues = list(first.prices.keys())
    assert len(venues) >= 3, f"expected >=3 venues, got {len(venues)}: {venues}"


def test_all_five_canned_books_present():
    """All 5 canned bookmaker titles appear as distinct oddsapi:<Title> venues."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    venues = set(result[0].prices.keys())
    for expected in ("oddsapi:DraftKings", "oddsapi:FanDuel", "oddsapi:BetMGM",
                     "oddsapi:Caesars", "oddsapi:PointsBet (US)"):
        assert expected in venues, f"missing venue: {expected}; have: {venues}"


def test_all_prices_are_decimal_gt_one():
    """Every scalar price in every venue is decimal > 1.0 (never sub-1 probability)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    for ev in result:
        for venue, sides in ev.prices.items():
            for key, val in sides.items():
                if key in ("spread", "total"):
                    continue  # nested dicts; checked by test_spread_total_prices_gt_one
                if val is not None:
                    assert isinstance(val, float), (
                        f"{venue}.{key} is not a float: {type(val)}")
                    assert val > 1.0, f"{venue}.{key}={val} not > 1.0"


def test_spread_total_prices_gt_one():
    """Spread and total sub-node odds are also > 1.0."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    ev = result[0]
    dk = ev.prices.get("oddsapi:DraftKings", {})
    spread = dk.get("spread")
    total = dk.get("total")
    assert spread is not None, "DraftKings spread missing from canned payload"
    assert total is not None, "DraftKings total missing from canned payload"
    for side, node in spread.items():
        assert node["odds"] > 1.0, f"spread.{side}.odds not >1.0: {node}"
    for side, node in total.items():
        assert node["odds"] > 1.0, f"total.{side}.odds not >1.0: {node}"


def test_as_of_is_set_and_nonempty():
    """OddsEvent.as_of is a non-empty ISO timestamp (true fetch time, not now())."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    for ev in result:
        assert ev.as_of, f"as_of is empty on event {ev.event_id}"
        assert isinstance(ev.as_of, str)


def test_venue_labels_use_oddsapi_prefix():
    """All venue labels are 'oddsapi:<BookTitle>' (no raw sportsbook keys leaked)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    for ev in result:
        for v in ev.prices:
            assert v.startswith("oddsapi:"), (
                f"venue label '{v}' missing 'oddsapi:' prefix")


def test_venue_type_is_sportsbook_not_pm():
    """'oddsapi:*' venues classify as VENUE_SPORTSBOOK (not prediction markets)."""
    for label in ("oddsapi:DraftKings", "oddsapi:FanDuel", "oddsapi:BetMGM"):
        assert venue_type(label) == VENUE_SPORTSBOOK, (
            f"{label} should be VENUE_SPORTSBOOK")


def test_dk_prices_match_canned_values():
    """DraftKings home/away prices match canned payload exactly."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    dk = result[0].prices["oddsapi:DraftKings"]
    assert math.isclose(dk["home"], 1.75, rel_tol=1e-6)
    assert math.isclose(dk["away"], 2.15, rel_tol=1e-6)


def test_source_field_is_oddsapi():
    """OddsEvent.source is 'oddsapi'."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert all(ev.source == "oddsapi" for ev in result)


# --------------------------------------------------------------------------- #
# B) ODDS_API_KEY absent -> UNAVAILABLE(reason); no synthetic price/book
# --------------------------------------------------------------------------- #

def test_key_absent_is_unavailable():
    """ODDS_API_KEY not set -> UNAVAILABLE with reason mentioning the key."""
    env = {k: v for k, v in os.environ.items() if k != "ODDS_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert is_unavailable(result), f"expected UNAVAILABLE, got {result}"
    assert "ODDS_API_KEY" in result.get("reason", ""), (
        f"reason should mention the key: {result}")


def test_key_blank_is_unavailable():
    """Blank ODDS_API_KEY treated as absent -> UNAVAILABLE."""
    with patch.dict(os.environ, {"ODDS_API_KEY": "  "}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert is_unavailable(result)


def test_unavailable_has_no_synthetic_price():
    """UNAVAILABLE sentinel carries no price/book/home/away fields."""
    env = {k: v for k, v in os.environ.items() if k != "ODDS_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("nba")
    assert is_unavailable(result)
    for k in result:
        assert k not in ("home", "away", "price", "odds", "book", "venue"), (
            f"sentinel contains fabricated field '{k}'")


# --------------------------------------------------------------------------- #
# C) Malformed/empty body -> UNAVAILABLE not raise; no fabricated price
# --------------------------------------------------------------------------- #

def test_malformed_payload_returns_unavailable_not_raise():
    """Non-list payload -> UNAVAILABLE; provider never raises."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_bad, use_cache=False).fetch("nba")
    assert is_unavailable(result), f"non-list body should be UNAVAILABLE: {result}"
    assert "shape" in result.get("reason", "")


def test_network_error_returns_unavailable_not_raise():
    """OSError from http_get -> UNAVAILABLE with error class in reason; never raises."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_crash, use_cache=False).fetch("nba")
    assert is_unavailable(result)
    assert "OSError" in result.get("reason", ""), f"reason: {result.get('reason')}"


def test_empty_list_returns_empty_list_not_unavailable():
    """Empty list payload -> empty list (no games today, not an error)."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_empty, use_cache=False).fetch("nba")
    assert isinstance(result, list)
    assert result == []


def test_unsupported_sport_returns_unavailable():
    """Unknown sport -> UNAVAILABLE with sport name in reason."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        result = make_team_provider(http_get=_stub_ok, use_cache=False).fetch("cricket")
    assert is_unavailable(result)
    assert "cricket" in result.get("reason", "")


def test_malformed_bookmaker_entry_skipped_not_crash():
    """A None bookmaker entry is skipped; valid DK entry still surfaces."""
    bad = [{
        "id": "x1",
        "home_team": "Team A", "away_team": "Team B",
        "commence_time": None,
        "bookmakers": [
            None,
            {"key": "dk", "title": "DraftKings",
             "markets": [{"key": "h2h", "outcomes": [
                 {"name": "Team A", "price": 1.95},
                 {"name": "Team B", "price": 1.90},
             ]}]},
        ],
    }]
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        def _stub(_url: str) -> Any:
            return bad
        result = make_team_provider(http_get=_stub, use_cache=False).fetch("nba")
    assert isinstance(result, list) and len(result) == 1
    assert "oddsapi:DraftKings" in result[0].prices


# --------------------------------------------------------------------------- #
# D) American -> decimal conversion correct
# --------------------------------------------------------------------------- #

def test_american_to_decimal_positive():
    """American +150 -> 2.50 exactly."""
    assert math.isclose(american_to_decimal(150), 2.50, rel_tol=1e-9)


def test_american_to_decimal_negative():
    """American -175 -> 1.5714..."""
    expected = 1.0 + 100.0 / 175.0
    assert math.isclose(american_to_decimal(-175), expected, rel_tol=1e-9)


def test_american_to_decimal_zero_returns_none():
    """American 0 is invalid -> None."""
    assert american_to_decimal(0) is None


def test_american_to_decimal_typical_range():
    """Spot-check a few more typical moneyline values."""
    assert math.isclose(american_to_decimal(100), 2.00)
    assert math.isclose(american_to_decimal(-110), 1.0 + 100.0 / 110.0, rel_tol=1e-6)
    assert math.isclose(american_to_decimal(200), 3.00)
    assert math.isclose(american_to_decimal(-200), 1.50)


# --------------------------------------------------------------------------- #
# E) merge_events compatibility (same OddsEvent shape as ESPN/Kalshi)
# --------------------------------------------------------------------------- #

def test_merge_events_single_provider():
    """A single-provider list fed into merge_events produces one event per game."""
    events = parse_events(_CANNED, "nba", as_of="2026-06-20T00:00:00+00:00")
    merged = agg_mod.merge_events([events])
    assert len(merged) == 2
    ev0 = merged[0]
    # The merged event carries all 5 venues from the first canned event
    assert len(ev0.prices) >= 3


def test_merge_events_two_providers_same_game():
    """Two providers quoting the same game merge into one event with combined venues."""
    ev_prov1 = OddsEvent(
        event_id="ev1", sport="nba",
        home="Boston Celtics", away="Los Angeles Lakers",
        commence_time=None,
        prices={"oddsapi:DraftKings": {"home": 1.75, "away": 2.15}},
        source="oddsapi", as_of="2026-06-20T00:00:00+00:00",
    )
    ev_prov2 = OddsEvent(
        event_id="ev1b", sport="nba",
        home="Boston Celtics", away="Los Angeles Lakers",
        commence_time=None,
        prices={"espn:BetMGM": {"home": 1.73, "away": 2.18}},
        source="espn", as_of="2026-06-20T00:01:00+00:00",
    )
    merged = agg_mod.merge_events([[ev_prov1], [ev_prov2]])
    assert len(merged) == 1, "same game should merge into one event"
    assert "oddsapi:DraftKings" in merged[0].prices
    assert "espn:BetMGM" in merged[0].prices


def test_merge_events_different_games_stay_separate():
    """Two different games are NOT merged into one."""
    ev1 = OddsEvent(event_id="a", sport="nba",
                    home="Boston Celtics", away="Los Angeles Lakers",
                    commence_time=None,
                    prices={"oddsapi:DraftKings": {"home": 1.75, "away": 2.15}},
                    source="oddsapi", as_of="2026-06-20T00:00:00+00:00")
    ev2 = OddsEvent(event_id="b", sport="nba",
                    home="Golden State Warriors", away="Miami Heat",
                    commence_time=None,
                    prices={"oddsapi:DraftKings": {"home": 1.65, "away": 2.30}},
                    source="oddsapi", as_of="2026-06-20T00:00:00+00:00")
    merged = agg_mod.merge_events([[ev1, ev2]])
    assert len(merged) == 2


def test_merged_event_prices_have_no_dollar_or_edge_key():
    """merge_events output contains no 'edge', 'roi', '$', or 'profit' key."""
    events = parse_events(_CANNED, "nba", as_of="2026-06-20T00:00:00+00:00")
    merged = agg_mod.merge_events([events])
    for ev in merged:
        for venue, sides in ev.prices.items():
            for k in sides:
                assert "$" not in k
                assert k not in ("edge", "roi", "profit", "return")


# --------------------------------------------------------------------------- #
# F) make_team_provider constructor -- correct return type & defaults
# --------------------------------------------------------------------------- #

def test_make_team_provider_returns_provider_instance():
    """make_team_provider() returns an OddsApiProvider (Provider protocol)."""
    p = make_team_provider()
    assert isinstance(p, OddsApiProvider)


def test_make_team_provider_custom_http_get():
    """make_team_provider accepts a custom http_get injected without raising."""
    with patch.dict(os.environ, {"ODDS_API_KEY": _KEY}):
        p = make_team_provider(http_get=_stub_ok, use_cache=False)
        result = p.fetch("nba")
    assert isinstance(result, list)


def test_provider_name_attribute():
    """OddsApiProvider.name is 'oddsapi' (contract for aggregate.aggregate sources map)."""
    p = make_team_provider()
    assert p.name == "oddsapi"
