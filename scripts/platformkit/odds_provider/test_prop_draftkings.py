"""Per-file unit tests for prop_draftkings (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_draftkings.py -q

Canned payloads mirror the REAL DraftKings public-API shape (trimmed):
  - events payload: one NBA game event
  - offers payload: NBA player-prop lines (Points O/U, Rebounds O/U) with two-
    sided American + decimal odds
  - empty/offseason payloads -> UNAVAILABLE

http_get is always injected; nothing here touches the network.
Acceptance:
  - parse canned fixture -> >=1 PropLine with payout_type="sportsbook",
    over_price>1.0, under_price>1.0
  - empty events payload -> UNAVAILABLE (offseason honest)
  - unsupported sport -> UNAVAILABLE
  - network exception -> UNAVAILABLE (no raise)
  - no $ field in any output
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_draftkings import (
    DraftKingsProvider,
    parse_event_offers,
    parse_events,
)

# ---------------------------------------------------------------------------
# Canned events payload (DK league-categories shape, trimmed).
# Real shape: eventGroup.events[]: {eventId, name, startDate}
# ---------------------------------------------------------------------------
EVENTS_NBA = {
    "eventGroup": {
        "id": "42648",
        "name": "NBA",
        "events": [
            {
                "eventId": 29837241,
                "name": "Boston Celtics at Golden State Warriors",
                "startDate": "2026-10-22T00:10:00Z",
            }
        ],
    }
}

# ---------------------------------------------------------------------------
# Canned offers payload (DK event player-prop shape, trimmed).
# Real shape: eventGroup.offerCategories[].offerSubcategory.offers[][]:
#   each offer is a list of market rows; each row has outcomes[].
#   outcome: {label "Over"|"Under", oddsAmerican "+115", oddsDecimal "2.15",
#              participant "Jayson Tatum", line "28.5"}
# ---------------------------------------------------------------------------
OFFERS_NBA = {
    "eventGroup": {
        "id": "42648",
        "name": "NBA",
        "offerCategories": [
            {
                "name": "Player Props",
                "offerSubcategory": {
                    "name": "Points O/U",
                    "offers": [
                        # First prop: Jayson Tatum Points O/U 28.5
                        [
                            {
                                "id": "O1",
                                "label": "Points O/U",
                                "outcomes": [
                                    {
                                        "label": "Over",
                                        "oddsAmerican": "+115",
                                        "oddsDecimal": "2.15",
                                        "participant": "Jayson Tatum",
                                        "line": "28.5",
                                    },
                                    {
                                        "label": "Under",
                                        "oddsAmerican": "-135",
                                        "oddsDecimal": "1.74",
                                        "participant": "Jayson Tatum",
                                        "line": "28.5",
                                    },
                                ],
                            }
                        ],
                        # Second prop: Stephen Curry Points O/U 23.5
                        [
                            {
                                "id": "O2",
                                "label": "Points O/U",
                                "outcomes": [
                                    {
                                        "label": "Over",
                                        "oddsAmerican": "-120",
                                        "oddsDecimal": "1.83",
                                        "participant": "Stephen Curry",
                                        "line": "23.5",
                                    },
                                    {
                                        "label": "Under",
                                        "oddsAmerican": "-100",
                                        "oddsDecimal": "1.91",
                                        "participant": "Stephen Curry",
                                        "line": "23.5",
                                    },
                                ],
                            }
                        ],
                    ],
                },
            },
            {
                "name": "Player Props",
                "offerSubcategory": {
                    "name": "Rebounds O/U",
                    "offers": [
                        [
                            {
                                "id": "O3",
                                "label": "Rebounds O/U",
                                "outcomes": [
                                    {
                                        "label": "Over",
                                        "oddsAmerican": "+105",
                                        "oddsDecimal": "2.05",
                                        "participant": "Jayson Tatum",
                                        "line": "7.5",
                                    },
                                    {
                                        "label": "Under",
                                        "oddsAmerican": "-125",
                                        "oddsDecimal": "1.80",
                                        "participant": "Jayson Tatum",
                                        "line": "7.5",
                                    },
                                ],
                            }
                        ]
                    ],
                },
            },
        ],
    }
}

# Empty offers (no prop rows -- e.g. only team-market tabs posted)
OFFERS_EMPTY = {
    "eventGroup": {
        "id": "42648",
        "name": "NBA",
        "offerCategories": [],
    }
}

# Offseason events payload (no events in the league)
EVENTS_EMPTY = {
    "eventGroup": {
        "id": "42648",
        "name": "NBA",
        "events": [],
    }
}

# MLB canned events + offers (to verify multi-sport wiring)
EVENTS_MLB = {
    "eventGroup": {
        "id": "84240",
        "name": "MLB",
        "events": [
            {"eventId": 33112, "name": "Boston Red Sox at New York Yankees",
             "startDate": "2026-07-04T19:05:00Z"}
        ],
    }
}

OFFERS_MLB = {
    "eventGroup": {
        "id": "84240",
        "name": "MLB",
        "offerCategories": [
            {
                "name": "Player Props",
                "offerSubcategory": {
                    "name": "Hits O/U",
                    "offers": [
                        [
                            {
                                "id": "M1",
                                "label": "Hits O/U",
                                "outcomes": [
                                    {
                                        "label": "Over",
                                        "oddsAmerican": "-110",
                                        "oddsDecimal": "1.91",
                                        "participant": "Aaron Judge",
                                        "line": "1.5",
                                    },
                                    {
                                        "label": "Under",
                                        "oddsAmerican": "-110",
                                        "oddsDecimal": "1.91",
                                        "participant": "Aaron Judge",
                                        "line": "1.5",
                                    },
                                ],
                            }
                        ]
                    ],
                },
            }
        ],
    }
}


# ===========================================================================
# Tests -- parse_events (pure)
# ===========================================================================

def test_parse_events_returns_event_list():
    events = parse_events(EVENTS_NBA)
    assert len(events) == 1
    assert events[0]["eventId"] == 29837241
    assert "Celtics" in events[0]["name"]


def test_parse_events_empty_returns_empty_list():
    events = parse_events(EVENTS_EMPTY)
    assert events == []


def test_parse_events_non_dict_safe():
    assert parse_events(None) == []  # type: ignore[arg-type]
    assert parse_events([]) == []    # type: ignore[arg-type]


# ===========================================================================
# Tests -- parse_event_offers (pure, core acceptance)
# ===========================================================================

def test_parse_event_offers_nba_sportsbook_rows():
    """Core acceptance: canned fixture -> PropLine list with sportsbook prices."""
    event = EVENTS_NBA["eventGroup"]["events"][0]
    rows = parse_event_offers(OFFERS_NBA, "nba", event, "2026-10-22T00:00:00+00:00")
    assert isinstance(rows, list)
    assert len(rows) >= 1, "expected >=1 PropLine from canned fixture"

    # All rows must carry two-sided sportsbook pricing
    for r in rows:
        assert r.payout_type == "sportsbook", (
            "expected payout_type=sportsbook, got %r" % r.payout_type)
        assert r.over_price is not None and r.over_price > 1.0, (
            "over_price must be decimal > 1.0, got %r" % r.over_price)
        assert r.under_price is not None and r.under_price > 1.0, (
            "under_price must be decimal > 1.0, got %r" % r.under_price)
        assert r.sport == "nba"
        assert r.source == "draftkings"
        assert r.player
        assert r.line is not None
        # honesty: no dollar / roi / pnl field in the dict
        d = r.to_dict()
        for key in ("dollar", "roi", "pnl", "profit"):
            assert key not in d, "forbidden key %r in PropLine.to_dict()" % key


def test_parse_event_offers_tatum_points():
    """Jayson Tatum Points O/U 28.5 parses correctly with canonical stat."""
    event = EVENTS_NBA["eventGroup"]["events"][0]
    rows = parse_event_offers(OFFERS_NBA, "nba", event, "2026-10-22T00:00:00+00:00")
    tatum_pts = [r for r in rows if r.player == "Jayson Tatum" and r.line == 28.5]
    assert tatum_pts, "expected at least one row for Tatum Points"
    r = tatum_pts[0]
    assert abs(r.over_price - 2.15) < 1e-6
    assert abs(r.under_price - 1.74) < 1e-6
    assert r.match == "Boston Celtics at Golden State Warriors"
    assert r.as_of is not None


def test_parse_event_offers_empty_cats_returns_empty():
    event = EVENTS_NBA["eventGroup"]["events"][0]
    rows = parse_event_offers(OFFERS_EMPTY, "nba", event, "2026-10-22T00:00:00+00:00")
    assert rows == []


def test_parse_event_offers_non_dict_safe():
    event = EVENTS_NBA["eventGroup"]["events"][0]
    assert parse_event_offers(None, "nba", event, "") == []  # type: ignore[arg-type]
    assert parse_event_offers("bad", "nba", event, "") == []  # type: ignore[arg-type]


def test_parse_event_offers_fallback_american_to_decimal():
    """When oddsDecimal absent/invalid, fall back to oddsAmerican conversion."""
    event = {"eventId": 999, "name": "Test Game"}
    body = {
        "eventGroup": {
            "offerCategories": [
                {
                    "name": "Player Props",
                    "offerSubcategory": {
                        "name": "Points O/U",
                        "offers": [
                            [
                                {
                                    "id": "X1",
                                    "outcomes": [
                                        {"label": "Over", "oddsAmerican": "+100",
                                         "participant": "Player A", "line": "15.5"},
                                        {"label": "Under", "oddsAmerican": "-120",
                                         "participant": "Player A", "line": "15.5"},
                                    ],
                                }
                            ]
                        ],
                    },
                }
            ]
        }
    }
    rows = parse_event_offers(body, "nba", event, "2026-10-01T00:00:00+00:00")
    assert len(rows) == 1
    r = rows[0]
    assert r.payout_type == "sportsbook"
    assert abs(r.over_price - 2.0) < 1e-6   # +100 -> 2.0 decimal
    assert abs(r.under_price - 1.8333) < 0.001  # -120 -> 100/120+1 = 1.8333...


# ===========================================================================
# Tests -- DraftKingsProvider (injected http_get, no network)
# ===========================================================================

def _make_provider(events_body, offers_body):
    """Build a provider that returns the given bodies with no network calls."""
    def _http_get(url):
        if "categories" in url and "events" not in url.split("?")[0].split("/")[-2:]:
            # heuristic: events-listing URL contains league_id in path
            return events_body
        return offers_body

    return DraftKingsProvider(http_get=_http_get)


def test_provider_nba_returns_sportsbook_rows():
    """End-to-end: injected HTTP -> parse -> PropLine list (core acceptance)."""
    def http_get(url):
        if "subcategories" in url and len(url.split("/events/")) == 1:
            # events listing (no event_id segment)
            return EVENTS_NBA
        return OFFERS_NBA

    prov = DraftKingsProvider(http_get=http_get)
    result = prov.fetch_props("nba")
    assert isinstance(result, list), "expected list, got %r" % type(result)
    assert len(result) >= 1
    for r in result:
        assert r.payout_type == "sportsbook"
        assert r.over_price is not None and r.over_price > 1.0
        assert r.under_price is not None and r.under_price > 1.0
        assert r.sport == "nba"
        assert r.source == "draftkings"


def test_provider_mlb_wired():
    def http_get(url):
        if "/events/" not in url:
            return EVENTS_MLB
        return OFFERS_MLB

    prov = DraftKingsProvider(http_get=http_get)
    result = prov.fetch_props("mlb")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(r.sport == "mlb" for r in result)
    assert all(r.payout_type == "sportsbook" for r in result)


def test_provider_soccer_intl_wired_as_unavailable_when_empty():
    """Soccer_intl is wired; empty events -> UNAVAILABLE (not unsupported error)."""
    def http_get(url):
        if "/events/" not in url:
            return EVENTS_EMPTY
        return OFFERS_EMPTY

    prov = DraftKingsProvider(http_get=http_get)
    result = prov.fetch_props("soccer_intl")
    assert is_unavailable(result)
    assert "unsupported" not in result.get("reason", "")


def test_provider_offseason_empty_events_unavailable():
    """NBA off-season: no events in the payload -> UNAVAILABLE (offseason honest)."""
    prov = DraftKingsProvider(http_get=lambda url: EVENTS_EMPTY)
    result = prov.fetch_props("nba")
    assert is_unavailable(result)
    reason = result.get("reason", "")
    # must not say "unsupported" -- this is a wired-but-empty sport
    assert "unsupported" not in reason


def test_provider_unsupported_sport_unavailable():
    """Entirely unknown sport -> UNAVAILABLE."""
    prov = DraftKingsProvider(http_get=lambda url: {})
    result = prov.fetch_props("cricket")
    assert is_unavailable(result)
    assert "unsupported" in result.get("reason", "")


def test_provider_network_failure_no_raise():
    """Injected exception -> UNAVAILABLE (never propagates)."""
    def boom(url):
        raise ConnectionError("network down")

    prov = DraftKingsProvider(http_get=boom)
    result = prov.fetch_props("nba")
    assert is_unavailable(result)


def test_provider_empty_body_unavailable():
    """HTTP returns empty dict -> UNAVAILABLE."""
    prov = DraftKingsProvider(http_get=lambda url: {})
    result = prov.fetch_props("nba")
    assert is_unavailable(result)


def test_provider_offers_all_empty_unavailable():
    """Events present but offers return no rows -> UNAVAILABLE."""
    def http_get(url):
        if "/events/" not in url:
            return EVENTS_NBA
        return OFFERS_EMPTY

    prov = DraftKingsProvider(http_get=http_get)
    result = prov.fetch_props("nba")
    assert is_unavailable(result)


def test_provider_no_dollar_field_in_output():
    """Honesty: no $ / roi / pnl field anywhere in the output dict."""
    def http_get(url):
        if "/events/" not in url:
            return EVENTS_NBA
        return OFFERS_NBA

    prov = DraftKingsProvider(http_get=http_get)
    result = prov.fetch_props("nba")
    assert isinstance(result, list)
    for r in result:
        d = r.to_dict()
        for bad_key in ("dollar", "roi", "pnl", "profit", "money"):
            assert bad_key not in d
