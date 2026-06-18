"""Per-file unit tests for scripts.platformkit.odds_provider (NETWORK-FREE).

Run ONLY this file (full pytest freezes the box):
    python -m pytest scripts/platformkit/odds_provider/test_odds_provider.py -q

Every test uses CANNED payloads + an injected http_get; nothing here touches the
network. Covers: price conversions, each provider's parser, the merge, the
to_odds_lookup odds_shop shape, and the unavailable degrade path.
"""
from __future__ import annotations

import math

from scripts.platformkit import odds_shop
from scripts.platformkit.odds_provider import base, aggregate
from scripts.platformkit.odds_provider.espn import EspnProvider, parse_pickcenter
from scripts.platformkit.odds_provider.kalshi import KalshiProvider, parse_events
from scripts.platformkit.odds_provider.polymarket import (
    PolymarketProvider, parse_market)


# --------------------------------------------------------------------------- #
# Canned payloads (shapes mirror live probes performed during the build).
# --------------------------------------------------------------------------- #
ESPN_SCOREBOARD = {
    "events": [{
        "id": "401815778",
        "date": "2026-06-16T23:15Z",
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "team": {"displayName": "Atlanta Braves"}},
                {"homeAway": "away", "team": {"displayName": "San Francisco Giants"}},
            ],
        }],
    }],
}
ESPN_SUMMARY = {
    "pickcenter": [{
        "provider": {"name": "DraftKings"},
        "homeTeamOdds": {"moneyLine": -175},
        "awayTeamOdds": {"moneyLine": 144},
    }],
}

KALSHI_MARKETS = {
    "markets": [
        {"event_ticker": "KXNBAGAME-26JUN17BOSLAL", "yes_sub_title": "Boston Celtics",
         "yes_ask_dollars": "0.60", "close_time": "2026-06-17T23:00Z"},
        {"event_ticker": "KXNBAGAME-26JUN17BOSLAL", "yes_sub_title": "Los Angeles Lakers",
         "yes_ask_dollars": "0.45", "close_time": "2026-06-17T23:00Z"},
        # unrelated single-leg market -> skipped
        {"event_ticker": "KXMVE-X", "yes_sub_title": "noise", "yes_ask_dollars": "0.5"},
    ],
}

POLY_MARKET = {
    "id": "999",
    "slug": "nba-celtics-vs-lakers-2026-06-17",
    "question": "NBA: Celtics vs Lakers",
    "outcomes": "[\"Boston Celtics\", \"Los Angeles Lakers\"]",
    "outcomePrices": "[\"0.58\", \"0.42\"]",
    "startDate": "2026-06-17T23:00Z",
}


def _stub(mapping):
    """An http_get that returns a canned body keyed by substring match in the URL."""
    def _get(url):
        for needle, body in mapping.items():
            if needle in url:
                return body
        raise AssertionError(f"unexpected URL in test: {url}")
    return _get


# --------------------------------------------------------------------------- #
# Price conversions.
# --------------------------------------------------------------------------- #
def test_american_to_decimal():
    assert math.isclose(base.american_to_decimal(150), 2.5)
    assert math.isclose(base.american_to_decimal(-175), 1.0 + 100.0 / 175.0)
    assert base.american_to_decimal(0) is None
    assert base.american_to_decimal(None) is None


def test_prob_to_decimal():
    assert math.isclose(base.prob_to_decimal(0.5), 2.0)
    assert math.isclose(base.prob_to_decimal(0.25), 4.0)
    assert base.prob_to_decimal(0.0) is None
    assert base.prob_to_decimal(1.0) is None
    assert base.prob_to_decimal("x") is None


# --------------------------------------------------------------------------- #
# ESPN provider parses canned payload into OddsEvent.
# --------------------------------------------------------------------------- #
def test_espn_parse_pickcenter():
    venues = parse_pickcenter(ESPN_SUMMARY, "Atlanta Braves", "San Francisco Giants")
    assert "espn:DraftKings" in venues
    v = venues["espn:DraftKings"]
    assert math.isclose(v["home"], 1.0 + 100.0 / 175.0)
    assert math.isclose(v["away"], 2.44)


def test_espn_fetch_builds_event():
    http = _stub({"scoreboard": ESPN_SCOREBOARD, "summary": ESPN_SUMMARY})
    events = EspnProvider(http_get=http, use_cache=False).fetch("mlb")
    assert isinstance(events, list) and len(events) == 1
    ev = events[0]
    assert ev.event_id == "401815778"
    assert ev.home == "Atlanta Braves" and ev.away == "San Francisco Giants"
    assert "espn:DraftKings" in ev.prices
    assert ev.source == "espn" and ev.as_of


# --------------------------------------------------------------------------- #
# Kalshi provider parses canned markets into a two-team OddsEvent.
# --------------------------------------------------------------------------- #
def test_kalshi_parse_events():
    events = parse_events(KALSHI_MARKETS["markets"], "nba")
    assert len(events) == 1  # the single-leg KXMVE market is skipped
    ev = events[0]
    assert ev.home == "Boston Celtics" and ev.away == "Los Angeles Lakers"
    k = ev.prices["kalshi"]
    assert math.isclose(k["home"], 1.0 / 0.60)
    assert math.isclose(k["away"], 1.0 / 0.45)
    assert k["draw"] is None


def test_kalshi_fetch_filters_by_series():
    http = _stub({"markets": KALSHI_MARKETS})
    events = KalshiProvider(http_get=http, use_cache=False).fetch("nba")
    assert isinstance(events, list) and len(events) == 1


# --------------------------------------------------------------------------- #
# Polymarket best-effort parser.
# --------------------------------------------------------------------------- #
def test_poly_parse_market():
    ev = parse_market(POLY_MARKET, "nba")
    assert ev is not None
    assert ev.home == "Boston Celtics" and ev.away == "Los Angeles Lakers"
    p = ev.prices["polymarket"]
    assert math.isclose(p["home"], 1.0 / 0.58)
    assert math.isclose(p["away"], 1.0 / 0.42)


def test_poly_skips_non_two_way():
    bad = {"id": "1", "outcomes": "[\"A\",\"B\",\"C\"]",
           "outcomePrices": "[\"0.3\",\"0.3\",\"0.4\"]"}
    assert parse_market(bad, "nba") is None


def test_poly_fetch_list_shape():
    http = _stub({"markets": [POLY_MARKET]})
    events = PolymarketProvider(http_get=http, use_cache=False).fetch("nba")
    assert isinstance(events, list) and len(events) == 1


# --------------------------------------------------------------------------- #
# Aggregate merges two venues into one event.
# --------------------------------------------------------------------------- #
def test_merge_two_venues():
    kalshi = parse_events(KALSHI_MARKETS["markets"], "nba")
    poly = [parse_market(POLY_MARKET, "nba")]
    merged = aggregate.merge_events([kalshi, poly])
    assert len(merged) == 1  # same game (Celtics vs Lakers) collapses to one entry
    ev = merged[0]
    assert set(ev.prices.keys()) == {"kalshi", "polymarket"}


def test_merge_flips_orientation():
    # Same game, opposite home/away ordering -> second venue's sides get flipped.
    a = base.OddsEvent("1", "nba", "Boston Celtics", "Los Angeles Lakers", None,
                       {"kalshi": {"home": 1.67, "away": 2.22}})
    b = base.OddsEvent("2", "nba", "Los Angeles Lakers", "Boston Celtics", None,
                       {"polymarket": {"home": 2.0, "away": 1.5}})
    merged = aggregate.merge_events([[a], [b]])
    assert len(merged) == 1
    poly = merged[0].prices["polymarket"]
    # poly home was Lakers (2.0); after flip it should sit on the AWAY side.
    assert math.isclose(poly["away"], 2.0) and math.isclose(poly["home"], 1.5)


# --------------------------------------------------------------------------- #
# to_odds_lookup returns the odds_shop shape and feeds summarise_twoway.
# --------------------------------------------------------------------------- #
def test_to_odds_lookup_feeds_odds_shop():
    http = _stub({
        "scoreboard": {"events": []},  # espn empty (no games today)
        "markets": KALSHI_MARKETS,     # kalshi + poly both hit "markets"
    })
    providers = aggregate.default_providers(http_get=http, use_cache=False)
    lookup = aggregate.to_odds_lookup("nba", providers)
    book_prices = lookup("nba", "Boston Celtics", "Los Angeles Lakers")
    assert book_prices is not None
    # Inner dict keyed by the caller's team-name strings (odds_shop contract).
    venue = next(iter(book_prices.values()))
    assert "Boston Celtics" in venue and "Los Angeles Lakers" in venue
    # And it flows straight into the existing pure engine:
    summary = odds_shop.summarise_twoway(
        book_prices, "Boston Celtics", "Los Angeles Lakers")
    assert summary["best_a_price"] is not None
    assert summary["fair_prob_a"] is not None


def test_lookup_no_match_returns_none():
    http = _stub({"scoreboard": {"events": []}, "markets": KALSHI_MARKETS})
    providers = aggregate.default_providers(http_get=http, use_cache=False)
    lookup = aggregate.to_odds_lookup("nba", providers)
    assert lookup("nba", "Phoenix Suns", "Miami Heat") is None


# --------------------------------------------------------------------------- #
# Feed-down / missing -> unavailable (no fabricated price).
# --------------------------------------------------------------------------- #
def test_provider_feed_down_is_unavailable():
    def boom(url):
        raise OSError("network down")
    res = EspnProvider(http_get=boom, use_cache=False).fetch("nba")
    assert base.is_unavailable(res)
    assert "failed" in res["reason"]


def test_aggregate_all_down_is_unavailable():
    def boom(url):
        raise OSError("down")
    providers = aggregate.default_providers(http_get=boom, use_cache=False)
    payload = aggregate.aggregate("nba", providers)
    assert payload["status"] == "unavailable"
    assert payload["events"] == []
    # every source recorded honestly, none "ok"
    assert all(v != "ok" for v in payload["sources"].values())


def test_unsupported_sport_is_unavailable():
    res = KalshiProvider(http_get=_stub({}), use_cache=False).fetch("cricket")
    assert base.is_unavailable(res)


# --------------------------------------------------------------------------- #
# venue_type HONESTY tag: ESPN republished books = sportsbook; Kalshi /
# Polymarket = prediction_market; unknown labels default to sportsbook.
# --------------------------------------------------------------------------- #
def test_venue_type_tags_each_provider_correctly():
    assert base.venue_type("espn:DraftKings") == base.VENUE_SPORTSBOOK
    assert base.venue_type("kalshi") == base.VENUE_PREDICTION_MARKET
    assert base.venue_type("polymarket") == base.VENUE_PREDICTION_MARKET
    # bare/legacy sportsbook labels default to sportsbook (back-compat)
    assert base.venue_type("DK") == base.VENUE_SPORTSBOOK
    assert base.venue_type("") == base.VENUE_SPORTSBOOK
    assert base.is_prediction_market("kalshi") is True
    assert base.is_prediction_market("espn:FanDuel") is False


def test_real_provider_venue_names_classify_as_expected():
    # The venue keys ACTUALLY produced by the providers tag correctly.
    espn = parse_pickcenter(ESPN_SUMMARY, "Atlanta Braves", "San Francisco Giants")
    for v in espn:  # e.g. "espn:DraftKings"
        assert base.venue_type(v) == base.VENUE_SPORTSBOOK
    kalshi = parse_events(KALSHI_MARKETS["markets"], "nba")[0]
    for v in kalshi.prices:  # "kalshi"
        assert base.venue_type(v) == base.VENUE_PREDICTION_MARKET
    poly = parse_market(POLY_MARKET, "nba")
    for v in poly.prices:  # "polymarket"
        assert base.venue_type(v) == base.VENUE_PREDICTION_MARKET


def test_venue_types_helper_maps_keys():
    tags = base.venue_types(["espn:DraftKings", "kalshi", "polymarket"])
    assert tags == {
        "espn:DraftKings": base.VENUE_SPORTSBOOK,
        "kalshi": base.VENUE_PREDICTION_MARKET,
        "polymarket": base.VENUE_PREDICTION_MARKET,
    }


def test_merged_pm_venue_not_bettable_but_visible_separately():
    # Merge a sportsbook (espn) + two PMs into one event, then run it through the
    # odds_shop honesty path: the bettable best is the sportsbook, while the PM
    # prices stay visible separately as a divergence signal.
    espn_ev = base.OddsEvent(
        "e", "nba", "Boston Celtics", "Los Angeles Lakers", None,
        {"espn:DraftKings": {"home": 1.95, "away": 1.90}})
    kalshi = parse_events(KALSHI_MARKETS["markets"], "nba")
    poly = [parse_market(POLY_MARKET, "nba")]
    merged = aggregate.merge_events([[espn_ev], kalshi, poly])
    assert len(merged) == 1
    ev = merged[0]
    assert set(ev.prices.keys()) == {"espn:DraftKings", "kalshi", "polymarket"}
    book_prices = {
        v: {ev.home: sides.get("home"), ev.away: sides.get("away")}
        for v, sides in ev.prices.items()
    }
    out = odds_shop.summarise_twoway(
        book_prices, ev.home, ev.away,
        bettable_restrict=odds_shop.VENUE_SPORTSBOOK)
    assert out["best_a_book"] == "espn:DraftKings"      # PM never wins bettable
    assert out["pm_a_book"] in ("kalshi", "polymarket")  # PM visible separately
    assert out["pm_a_price"] is not None
