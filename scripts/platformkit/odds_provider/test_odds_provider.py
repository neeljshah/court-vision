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
    PolymarketProvider, parse_market, parse_market_binary,
    parse_markets_with_binaries)


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

# Single-sided YES/NO gamma binary: "Will the Celtics win the NBA title?"
POLY_BINARY_MARKET = {
    "id": "1001",
    "slug": "nba-celtics-win-title",
    "question": "Will the Boston Celtics win the NBA championship?",
    "outcomes": "[\"Yes\", \"No\"]",
    "outcomePrices": "[\"0.62\", \"0.38\"]",
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
    from datetime import datetime, timezone
    http = _stub({"scoreboard": ESPN_SCOREBOARD, "summary": ESPN_SUMMARY})
    # now= pinned near the canned event's date -- the stale-echo guard (espn.py
    # _MAX_EVENT_AGE_HOURS) would otherwise drop this old fixture date.
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    events = EspnProvider(http_get=http, use_cache=False).fetch("mlb", now=now)
    assert isinstance(events, list) and len(events) == 1
    ev = events[0]
    assert ev.event_id == "401815778"
    assert ev.home == "Atlanta Braves" and ev.away == "San Francisco Giants"
    assert "espn:DraftKings" in ev.prices
    assert ev.source == "espn" and ev.as_of


def test_espn_fetch_drops_stale_scoreboard_echo():
    """Root-cause regression (2026-07-11): a quiet scoreboard re-serving a game
    that tipped off weeks ago (e.g. the offseason "last known event" fallback)
    must be dropped, not captured as if it were today's live slate."""
    from datetime import datetime, timezone
    http = _stub({"scoreboard": ESPN_SCOREBOARD, "summary": ESPN_SUMMARY})
    # ESPN_SCOREBOARD's event dates to 2026-06-16; poll 25 days later.
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    events = EspnProvider(http_get=http, use_cache=False).fetch("mlb", now=now)
    assert events == []


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


def test_kalshi_fetch_npb_filters_by_series():
    """npb added to _SERIES_HINT (paper enablement sweep, LANE 5): KXNPBGAME
    tickers filter in, everything else (incl. KXNBAGAME) filters out."""
    npb_markets = {
        "markets": [
            {"event_ticker": "KXNPBGAME-26JUL050500YOKYAK", "yes_sub_title": "Yokohama",
             "yes_ask_dollars": "0.55", "close_time": "2026-07-05T05:00Z"},
            {"event_ticker": "KXNPBGAME-26JUL050500YOKYAK", "yes_sub_title": "Yakult",
             "yes_ask_dollars": "0.48", "close_time": "2026-07-05T05:00Z"},
            {"event_ticker": "KXNBAGAME-26JUN17BOSLAL", "yes_sub_title": "noise",
             "yes_ask_dollars": "0.5"},
        ],
    }
    http = _stub({"markets": npb_markets})
    events = KalshiProvider(http_get=http, use_cache=False).fetch("npb")
    assert isinstance(events, list) and len(events) == 1
    assert events[0].home in ("Yokohama", "Yakult") or events[0].away in ("Yokohama", "Yakult")


def test_kalshi_fetch_unsupported_sport_still_unavailable():
    """A sport absent from _SERIES_HINT stays a clean UNAVAILABLE degrade, never a
    guess. (Fixture sport was 'kbo' until kbo became SUPPORTED in waves 3-4; use a
    sport with no series hint.)"""
    http = _stub({"markets": KALSHI_MARKETS})
    res = KalshiProvider(http_get=http, use_cache=False).fetch("cricket")
    assert base.is_unavailable(res)


def test_kalshi_fetch_governor_caller_opt_in_gates_request(monkeypatch):
    """governor_caller="close_capture" (m18's fix) resolves a REAL governor and
    acquires a token before the HTTP call; the default (governor_caller=None,
    every pre-existing caller) resolves to governor=None, so before_request's
    own None-check no-ops it -- byte-identical behavior, same opt-in idiom as
    inplay_kalshi.fetch_inplay's governor_caller."""
    calls = []
    import scripts.platformkit.odds_provider.kalshi as kalshi_mod
    monkeypatch.setattr(kalshi_mod, "_governor_before",
                        lambda governor, sport, **kw: calls.append((governor, sport)))
    http = _stub({"markets": KALSHI_MARKETS})

    KalshiProvider(http_get=http, use_cache=False).fetch("nba")
    assert calls == [(None, "nba")]  # default caller=None -> governor is None (no-op downstream)

    calls.clear()
    KalshiProvider(http_get=http, use_cache=False,
                  governor_caller="close_capture").fetch("nba")
    assert len(calls) == 1 and calls[0][1] == "nba" and calls[0][0] is not None


def test_kalshi_fetch_governor_reports_429(monkeypatch):
    """A 429 on the governed path must report_429 so the shared backoff engages."""
    reported = []
    import scripts.platformkit.odds_provider.kalshi as kalshi_mod
    import urllib.error
    monkeypatch.setattr(kalshi_mod, "_governor_report_429",
                        lambda governor: reported.append(governor))

    def _raise_429(_url):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    res = KalshiProvider(http_get=_raise_429, use_cache=False,
                         governor_caller="close_capture").fetch("nba")
    assert base.is_unavailable(res)
    assert len(reported) == 1


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
# Polymarket single-sided YES/NO binary contract parsing.
# --------------------------------------------------------------------------- #
def test_poly_yesno_market_rejected_by_parse_market():
    # A YES/NO contract must NOT be mapped to home="Yes"/away="No".
    result = parse_market(POLY_BINARY_MARKET, "nba")
    assert result is None, "YES/NO binary must not produce a two-leg OddsEvent"


def test_poly_parse_market_binary_single_binary_shape():
    row = parse_market_binary(POLY_BINARY_MARKET, "nba")
    assert row is not None, "parse_market_binary must parse a YES/NO market"
    # Shape must match single-binary: home/away/pm_prob all None.
    assert row["home"] is None
    assert row["away"] is None
    assert row["pm_prob"] is None
    assert row["binary_title"] == "Will the Boston Celtics win the NBA championship?"
    assert math.isclose(row["binary_yes_prob"], 0.62)
    assert row["market_id"] == "1001"
    assert row["sport"] == "nba"


def test_poly_parse_market_binary_rejects_non_yesno():
    # A regular two-team market must be rejected by parse_market_binary.
    assert parse_market_binary(POLY_MARKET, "nba") is None


def test_poly_parse_markets_with_binaries_splits_correctly():
    markets = [POLY_MARKET, POLY_BINARY_MARKET]
    events, binaries = parse_markets_with_binaries(markets, "nba")
    # Two-leg event parsed correctly.
    assert len(events) == 1
    assert events[0].home == "Boston Celtics"
    # Binary parsed into separate list.
    assert len(binaries) == 1
    b = binaries[0]
    assert b["home"] is None and b["away"] is None and b["pm_prob"] is None
    assert "Boston Celtics" in b["binary_title"]
    assert math.isclose(b["binary_yes_prob"], 0.62)


def test_poly_fetch_with_binaries_returns_both_shapes():
    http = _stub({"markets": [POLY_MARKET, POLY_BINARY_MARKET]})
    result = PolymarketProvider(http_get=http, use_cache=False).fetch_with_binaries("nba")
    assert isinstance(result, tuple), "fetch_with_binaries must return a tuple"
    events, binaries = result
    assert len(events) == 1 and events[0].home == "Boston Celtics"
    assert len(binaries) == 1 and binaries[0]["binary_title"] is not None


def test_poly_fetch_still_returns_only_events():
    # fetch() (two-leg only) still works; binaries are silently excluded.
    http = _stub({"markets": [POLY_MARKET, POLY_BINARY_MARKET]})
    events = PolymarketProvider(http_get=http, use_cache=False).fetch("nba")
    assert isinstance(events, list) and len(events) == 1
    assert events[0].home == "Boston Celtics"


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


def test_lookup_carries_draw_for_soccer():
    # DRAW-KEY-CARRY-THROUGH: a raw 3-way soccer event's literal 'draw' price must
    # reach the lookup output under the board's expected "Draw" selection key.
    ev = base.OddsEvent("1", "soccer_intl", "England", "Croatia", None,
                        {"kalshi": {"home": 1.90, "away": 4.50, "draw": 3.40}})

    class _StubProvider:
        name = "kalshi"
        def fetch(self, sport):
            return [ev]

    lookup = aggregate.to_odds_lookup("soccer_intl", providers=[_StubProvider()])
    book_prices = lookup("soccer_intl", "England", "Croatia")
    assert book_prices is not None
    venue = book_prices["kalshi"]
    assert venue["England"] == 1.90
    assert venue["Croatia"] == 4.50
    assert venue["Draw"] == 3.40


def test_lookup_2way_sport_has_no_draw_key():
    # REGRESSION: a 2-way sport (no 'draw' in the source prices) must NOT gain a
    # "Draw" key -- byte-identical output to before the carry-through fix.
    http = _stub({"scoreboard": {"events": []}, "markets": KALSHI_MARKETS})
    providers = aggregate.default_providers(http_get=http, use_cache=False)
    lookup = aggregate.to_odds_lookup("nba", providers)
    book_prices = lookup("nba", "Boston Celtics", "Los Angeles Lakers")
    assert book_prices is not None
    for venue in book_prices.values():
        assert "Draw" not in venue


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
