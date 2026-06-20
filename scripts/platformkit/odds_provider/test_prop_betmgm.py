"""Per-file unit tests for prop_betmgm (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_prop_betmgm.py -q

Canned payloads mirror the REAL BetMGM CDS-API shape intercepted via Playwright
(R18 probe, 2026-06-18). All cases exercised:
  1. Full fixture with player-prop optionMarkets -> two-way priced PropLine rows.
  2. Empty/offseason fixture list -> UNAVAILABLE (honest).
  3. Malformed/partial payload -> no raise, graceful empty.
  4. Unsupported sport -> UNAVAILABLE with "unsupported" reason.
  5. Network exception -> UNAVAILABLE (no raise).
  6. No $ / roi / pnl field in any output dict.

http_get is always injected; nothing here touches the network.

Acceptance:
  - parse canned BetMGM fixture -> >=1 PropLine payout_type='sportsbook'
    over_price>1.0 + under_price>1.0
  - empty/offseason fixture -> UNAVAILABLE honest
  - malformed -> no raise
  - no $ key
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.base import is_unavailable
from scripts.platformkit.odds_provider.prop_betmgm import (
    BetMGMProvider,
    parse_fixtures,
)

# ---------------------------------------------------------------------------
# Canned fixtures (BetMGM CDS-API shape, trimmed to essentials).
# Real shape: fixtures[].{id, name: {value}, optionMarkets[].{name: {value},
#   options[].{name: {value: "Over"|"Under"}, attr: "<line>",
#              price: {americanOdds: N}}}}
# ---------------------------------------------------------------------------
FIXTURES_NBA = {
    "fixtures": [
        {
            "id": "NBA_G1",
            "name": {"value": "Boston Celtics @ Golden State Warriors"},
            "startDate": "2026-10-22T00:10:00Z",
            "optionMarkets": [
                {
                    "id": "MKT1",
                    "name": {"value": "Jayson Tatum - Player Points"},
                    "options": [
                        {
                            "name": {"value": "Over"},
                            "attr": "28.5",
                            "price": {"americanOdds": 115},
                        },
                        {
                            "name": {"value": "Under"},
                            "attr": "28.5",
                            "price": {"americanOdds": -135},
                        },
                    ],
                },
                {
                    "id": "MKT2",
                    "name": {"value": "Jayson Tatum - Player Rebounds"},
                    "options": [
                        {
                            "name": {"value": "Over"},
                            "attr": "7.5",
                            "price": {"americanOdds": 105},
                        },
                        {
                            "name": {"value": "Under"},
                            "attr": "7.5",
                            "price": {"americanOdds": -125},
                        },
                    ],
                },
                {
                    "id": "MKT3",
                    "name": {"value": "Stephen Curry - Player Points"},
                    "options": [
                        {
                            "name": {"value": "Over"},
                            "attr": "23.5",
                            "price": {"americanOdds": -120},
                        },
                        {
                            "name": {"value": "Under"},
                            "attr": "23.5",
                            "price": {"americanOdds": -100},
                        },
                    ],
                },
                # Non-prop market -- should be skipped
                {
                    "id": "MKT9",
                    "name": {"value": "Moneyline"},
                    "options": [
                        {"name": {"value": "Boston"}, "attr": "0",
                         "price": {"americanOdds": -140}},
                        {"name": {"value": "Golden State"}, "attr": "0",
                         "price": {"americanOdds": 120}},
                    ],
                },
            ],
        },
        # Outright / non-matchup event -- should be skipped (no "@" or "vs")
        {
            "id": "NBA_OUT",
            "name": {"value": "NBA Championship"},
            "optionMarkets": [],
        },
    ]
}

# Plain-string name field alternative (some regional feeds)
FIXTURES_NBA_FLATNAME = {
    "fixtures": [
        {
            "id": "NBA_G2",
            "name": "Milwaukee Bucks @ Phoenix Suns",
            "startDate": "2026-10-23T01:30:00Z",
            "optionMarkets": [
                {
                    "id": "MKT10",
                    "name": "Giannis Antetokounmpo - Player Points",
                    "options": [
                        {"name": "Over", "attr": "31.5",
                         "price": {"americanOdds": -110}},
                        {"name": "Under", "attr": "31.5",
                         "price": {"americanOdds": -110}},
                    ],
                }
            ],
        }
    ]
}

# Offseason: no fixtures in the payload
FIXTURES_EMPTY = {"fixtures": []}

# Malformed: wrong types, missing keys
FIXTURES_MALFORMED = {
    "fixtures": [
        None,
        "not a dict",
        {"id": "X", "name": {"value": "Team A @ Team B"},
         "optionMarkets": None},
        {"id": "Y", "name": {"value": "Team C @ Team D"},
         "optionMarkets": [
             {"name": {"value": "Player Points"}, "options": []},
             None,
             "bad",
         ]},
    ]
}

# Soccer World Cup fixture
FIXTURES_SOCCER = {
    "fixtures": [
        {
            "id": "WC_G1",
            "name": {"value": "Brazil @ Argentina"},
            "startDate": "2026-07-10T20:00:00Z",
            "optionMarkets": [
                {
                    "id": "SM1",
                    "name": {"value": "Neymar - Player Shots"},
                    "options": [
                        {"name": {"value": "Over"}, "attr": "2.5",
                         "price": {"americanOdds": 130}},
                        {"name": {"value": "Under"}, "attr": "2.5",
                         "price": {"americanOdds": -160}},
                    ],
                }
            ],
        }
    ]
}


# ===========================================================================
# Tests -- parse_fixtures (pure, no network)
# ===========================================================================

def test_parse_fixtures_nba_two_sided_rows():
    """Core acceptance: canned NBA fixture -> >=1 PropLine with sportsbook prices."""
    rows = parse_fixtures(FIXTURES_NBA, "nba")
    assert isinstance(rows, list)
    assert len(rows) >= 1, "expected >=1 PropLine from canned NBA fixture"
    for r in rows:
        assert r.payout_type == "sportsbook"
        assert r.over_price is not None and r.over_price > 1.0
        assert r.under_price is not None and r.under_price > 1.0
        assert r.sport == "nba"
        assert r.source == "betmgm"
        assert r.player
        assert r.line is not None
        # honesty: no dollar / roi / pnl field in the dict
        d = r.to_dict()
        for bad_key in ("dollar", "roi", "pnl", "profit", "money"):
            assert bad_key not in d, "forbidden key %r in PropLine.to_dict()" % bad_key


def test_parse_fixtures_tatum_points_correct():
    """Jayson Tatum Points O/U 28.5 parses correctly with canonical stat."""
    rows = parse_fixtures(FIXTURES_NBA, "nba")
    tatum_pts = [r for r in rows if "tatum" in r.player.lower() and r.line == 28.5]
    assert tatum_pts, "expected at least one row for Tatum Points"
    r = tatum_pts[0]
    # +115 -> 2.15 ; -135 -> 1.0 + 100/135 = 1.7407...
    assert abs(r.over_price - 2.15) < 1e-6
    assert abs(r.under_price - (1.0 + 100.0 / 135.0)) < 0.001
    assert r.match == "Boston Celtics @ Golden State Warriors"
    assert r.event_id == "NBA_G1"
    assert r.as_of is not None


def test_parse_fixtures_stat_canonicalization():
    """Points market -> canonical 'Points'; Rebounds -> 'Rebounds'."""
    rows = parse_fixtures(FIXTURES_NBA, "nba")
    stats = {r.stat for r in rows}
    assert "Points" in stats or any("point" in s.lower() for s in stats)
    assert "Rebounds" in stats or any("reb" in s.lower() for s in stats)


def test_parse_fixtures_skips_moneyline():
    """Moneyline market (no stat fragment) should not produce any PropLine."""
    rows = parse_fixtures(FIXTURES_NBA, "nba")
    # No row should have the moneyline event name but a missing stat
    assert all(r.stat for r in rows), "all rows must have a stat"


def test_parse_fixtures_skips_outright_event():
    """'NBA Championship' event lacks '@'/'vs' -> excluded."""
    rows = parse_fixtures(FIXTURES_NBA, "nba")
    assert all(r.event_id != "NBA_OUT" for r in rows)


def test_parse_fixtures_flat_name_variant():
    """Flat string name field (non-dict) parses correctly."""
    rows = parse_fixtures(FIXTURES_NBA_FLATNAME, "nba")
    assert len(rows) >= 1
    r = rows[0]
    assert "giannis" in r.player.lower() or "antetokounmpo" in r.player.lower()
    assert r.payout_type == "sportsbook"
    assert r.over_price is not None and r.over_price > 1.0
    assert r.under_price is not None and r.under_price > 1.0


def test_parse_fixtures_empty_returns_empty():
    rows = parse_fixtures(FIXTURES_EMPTY, "nba")
    assert rows == []


def test_parse_fixtures_malformed_no_raise():
    """Malformed payload -> no raise, graceful empty/partial."""
    rows = parse_fixtures(FIXTURES_MALFORMED, "nba")
    assert isinstance(rows, list)  # never raises, returns list (possibly empty)


def test_parse_fixtures_non_dict_safe():
    assert parse_fixtures(None, "nba") == []   # type: ignore[arg-type]
    assert parse_fixtures([], "nba") == []     # type: ignore[arg-type]
    assert parse_fixtures("bad", "nba") == []  # type: ignore[arg-type]


def test_parse_fixtures_soccer():
    """Soccer fixture with shots market -> PropLine with 'Shots' or canonical."""
    rows = parse_fixtures(FIXTURES_SOCCER, "soccer_intl")
    assert len(rows) >= 1
    r = rows[0]
    assert r.payout_type == "sportsbook"
    assert r.over_price is not None and r.over_price > 1.0
    assert r.under_price is not None and r.under_price > 1.0
    assert r.sport == "soccer_intl"
    assert r.source == "betmgm"


# ===========================================================================
# Tests -- BetMGMProvider (injected http_get, no network)
# ===========================================================================

def test_provider_nba_returns_sportsbook_rows():
    """End-to-end: injected HTTP -> parse -> PropLine list (core acceptance)."""
    prov = BetMGMProvider(http_get=lambda url: FIXTURES_NBA)
    result = prov.fetch_props("nba")
    assert isinstance(result, list), "expected list, got %r" % type(result)
    assert len(result) >= 1
    for r in result:
        assert r.payout_type == "sportsbook"
        assert r.over_price is not None and r.over_price > 1.0
        assert r.under_price is not None and r.under_price > 1.0
        assert r.sport == "nba"
        assert r.source == "betmgm"


def test_provider_offseason_unavailable():
    """Empty fixtures -> UNAVAILABLE (offseason honest)."""
    prov = BetMGMProvider(http_get=lambda url: FIXTURES_EMPTY)
    result = prov.fetch_props("nba")
    assert is_unavailable(result)
    reason = result.get("reason", "")
    assert "unsupported" not in reason  # wired sport, not unsupported


def test_provider_unsupported_sport_unavailable():
    """Entirely unknown sport -> UNAVAILABLE with 'unsupported' in reason."""
    prov = BetMGMProvider(http_get=lambda url: {})
    result = prov.fetch_props("cricket")
    assert is_unavailable(result)
    assert "unsupported" in result.get("reason", "")


def test_provider_network_failure_no_raise():
    """Injected exception -> UNAVAILABLE (never propagates)."""
    def boom(url):
        raise ConnectionError("network down")
    prov = BetMGMProvider(http_get=boom)
    result = prov.fetch_props("nba")
    assert is_unavailable(result)


def test_provider_empty_body_unavailable():
    """HTTP returns empty dict -> UNAVAILABLE."""
    prov = BetMGMProvider(http_get=lambda url: {})
    result = prov.fetch_props("nba")
    assert is_unavailable(result)


def test_provider_waf_403_style_returns_unavailable():
    """WAF-blocked (403-style) empty response body -> UNAVAILABLE not raise."""
    prov = BetMGMProvider(http_get=lambda url: {})
    result = prov.fetch_props("nba")
    assert is_unavailable(result)
    assert "unavailable" in result.get("status", "")


def test_provider_no_dollar_field_in_output():
    """Honesty: no $ / roi / pnl field anywhere in the output dict."""
    prov = BetMGMProvider(http_get=lambda url: FIXTURES_NBA)
    result = prov.fetch_props("nba")
    assert isinstance(result, list)
    for r in result:
        d = r.to_dict()
        for bad_key in ("dollar", "roi", "pnl", "profit", "money"):
            assert bad_key not in d


def test_provider_mlb_wired():
    """MLB is a wired sport; fixture with player-prop returns sportsbook rows."""
    fixtures_mlb = {
        "fixtures": [
            {
                "id": "MLB_G1",
                "name": {"value": "New York Yankees @ Boston Red Sox"},
                "startDate": "2026-07-04T19:05:00Z",
                "optionMarkets": [
                    {
                        "id": "ML_MKT1",
                        "name": {"value": "Aaron Judge - Player Points"},
                        "options": [
                            {"name": {"value": "Over"}, "attr": "1.5",
                             "price": {"americanOdds": -110}},
                            {"name": {"value": "Under"}, "attr": "1.5",
                             "price": {"americanOdds": -110}},
                        ],
                    }
                ],
            }
        ]
    }
    prov = BetMGMProvider(http_get=lambda url: fixtures_mlb)
    result = prov.fetch_props("mlb")
    assert isinstance(result, list)
    assert len(result) >= 1
    assert all(r.sport == "mlb" for r in result)
    assert all(r.payout_type == "sportsbook" for r in result)
