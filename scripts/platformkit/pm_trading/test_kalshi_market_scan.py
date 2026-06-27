"""Per-file test for kalshi_market_scan -- the liquid-surface discovery.

Fully offline (injected http_get). Pins: the liquidity gate EXCLUDES listed-not-traded
markets (no two-way / wide / zero-volume), market_type classification, and the grouped
report shape. No network, no real Kalshi call.

Run: cd /c/Users/neelj/nba-ai-system && \
     python -m pytest scripts/platformkit/pm_trading/test_kalshi_market_scan.py -q
"""
from __future__ import annotations

import scripts.platformkit.pm_trading.kalshi_market_scan as K


def _market(ticker, yes_bid, yes_ask, volume):
    # Kalshi list schema: prices in DOLLARS (yes_bid_dollars), size in *_fp. A
    # None bid/ask models a listed-not-quoted contract. yes_bid/yes_ask args are
    # in cents here for readability -> convert to the real dollar fields.
    yb = None if yes_bid is None else yes_bid / 100.0
    ya = None if yes_ask is None else yes_ask / 100.0
    return {"ticker": ticker, "title": ticker, "yes_bid_dollars": yb,
            "yes_ask_dollars": ya, "volume_24h_fp": volume,
            "open_interest_fp": volume}


def _fake_http(series_body, market_bodies):
    def _get(url):
        if "/series" in url:
            return series_body
        for ser, body in market_bodies.items():
            if "series_ticker=%s" % ser in url:
                return body
        return {}
    return _get


def test_classify_market_type():
    assert K.classify_market_type("KXMLBGAME", "MLB Game") == "game_winner"
    assert K.classify_market_type("KXWNBATOTAL", "Total") == "team_total"
    assert K.classify_market_type("KXNBAPLAYOFFPTS", "Player Points") == "player_prop"
    assert K.classify_market_type("KXEPL1H", "First Half") == "first_half"
    assert K.classify_market_type("KXNHLVEZINA", "Vezina") == "event_future"


def test_liquidity_gate_excludes_untraded():
    assert K._is_liquid(_market("a", 48, 50, 1200)) is True        # tight two-way + vol
    assert K._is_liquid(_market("b", None, None, 0)) is False       # no two-way (untraded)
    assert K._is_liquid(_market("c", 30, 70, 5)) is False           # 40c spread = wide
    # a tight two-way is HITTABLE even before volume accrues (market-maker quoted) ->
    # takeable; volume is a bonus signal, not a gate (matches the real Kalshi props).
    assert K._is_liquid(_market("d", 48, 50, 0)) is True


def test_scan_groups_and_counts_only_liquid():
    series = [{"ticker": "KXMLBGAME", "title": "MLB Game"},
              {"ticker": "KXMLBHR", "title": "Home Runs"}]
    bodies = {
        # game_winner: 1 liquid + 1 untraded
        "KXMLBGAME": {"markets": [_market("g1", 55, 57, 9000),
                                  _market("g2", None, None, 0)]},
        # player_prop: all listed-not-traded (the honest reality)
        "KXMLBHR": {"markets": [_market("hr1", None, None, 0),
                                _market("hr2", 10, 80, 0)]},
    }
    rep = K.scan(series, http_get=_fake_http({}, bodies))
    assert rep["n_liquid_total"] == 1                 # only the one real two-way
    assert rep["n_open_total"] == 4
    assert rep["by_type"]["game_winner"]["n_liquid"] == 1
    assert rep["by_type"]["player_prop"]["n_liquid"] == 0   # listed but NOT takeable
    assert rep["executed"] is False and rep["edge_claimed"] is False


def test_discover_filters_by_league_token():
    series_body = {"series": [{"ticker": "KXMLBGAME", "title": "MLB"},
                              {"ticker": "KXNFLSAFETY", "title": "NFL"},
                              {"ticker": "KXWCGAME", "title": "WC"}], "cursor": ""}
    got = K.discover_sports_series(["MLB", "WC"], http_get=_fake_http(series_body, {}))
    tickers = {s["ticker"] for s in got}
    assert tickers == {"KXMLBGAME", "KXWCGAME"}     # NFL token excluded
