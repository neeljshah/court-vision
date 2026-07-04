"""Per-file test for ingame_book_depth (snapshot builders + stale_quote_flag).

OFFLINE + deterministic: http is injected, no network.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.ingame import ingame_book_depth as bd

_ORDERBOOK_BODY = {
    "orderbook_fp": {
        "yes_dollars": [["0.50", "10"]],
        "no_dollars": [["0.48", "10"]],  # yes_ask = 1 - 0.48 = 0.52 -> 2c spread = 200bp
    }
}
_TRADES_BODY = {"trades": []}

_POLY_BOOK_WIDE = {
    "bids": [{"price": "0.10", "size": "5"}],
    "asks": [{"price": "0.90", "size": "5"}],  # 80c spread -> way over the 50bp threshold
}


def _http_kalshi(url: str):
    if "orderbook" in url:
        return _ORDERBOOK_BODY
    if "trades" in url:
        return _TRADES_BODY
    raise AssertionError(url)


def _http_poly(url: str):
    return _POLY_BOOK_WIDE


def test_stale_quote_flag_first_snapshot_never_stale():
    cur = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": 200.0}
    assert bd.stale_quote_flag(None, cur) is False


def test_stale_quote_flag_unchanged_and_wide_is_stale():
    prev = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": 200.0}
    cur = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": 200.0}
    assert bd.stale_quote_flag(prev, cur) is True


def test_stale_quote_flag_unchanged_but_tight_is_not_stale():
    """A tight, unchanged quote is a healthy resting book, not staleness."""
    prev = {"best_bid": 0.50, "best_ask": 0.505, "spread_bp": 5.0}
    cur = {"best_bid": 0.50, "best_ask": 0.505, "spread_bp": 5.0}
    assert bd.stale_quote_flag(prev, cur) is False


def test_stale_quote_flag_top_of_book_moved_is_not_stale():
    prev = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": 200.0}
    cur = {"best_bid": 0.51, "best_ask": 0.52, "spread_bp": 100.0}
    assert bd.stale_quote_flag(prev, cur) is False


def test_stale_quote_flag_none_spread_is_never_stale():
    prev = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": None}
    cur = {"best_bid": 0.50, "best_ask": 0.52, "spread_bp": None}
    assert bd.stale_quote_flag(prev, cur) is False


def test_snapshot_kalshi_market_wires_stale_flag():
    now_dt = datetime(2026, 7, 6, 0, 0, 0, tzinfo=timezone.utc)
    row1 = bd.snapshot_kalshi_market("TICK1", http=_http_kalshi, now_dt=now_dt, prev=None)
    assert row1["stale_quote_flag"] is False  # no prior snapshot yet
    row2 = bd.snapshot_kalshi_market("TICK1", http=_http_kalshi, now_dt=now_dt, prev=row1)
    assert row2["stale_quote_flag"] is True  # identical top-of-book + wide (200bp) spread


def test_snapshot_kalshi_market_fetch_failure_returns_none():
    def _boom(url):
        raise ConnectionError("dead")
    assert bd.snapshot_kalshi_market("X", http=_boom) is None


def test_snapshot_polymarket_token_wires_stale_flag():
    row1 = bd.snapshot_polymarket_token("TOK1", http=_http_poly, prev=None)
    assert row1["stale_quote_flag"] is False
    row2 = bd.snapshot_polymarket_token("TOK1", http=_http_poly, prev=row1)
    assert row2["stale_quote_flag"] is True  # unchanged + 80c spread >> 50bp


def test_snapshot_polymarket_token_fetch_failure_returns_none():
    def _boom(url):
        raise TimeoutError("dead")
    assert bd.snapshot_polymarket_token("X", http=_boom) is None


def test_resolve_polymarket_token_delegates():
    body = [{"markets": [{"clobTokenIds": '["999"]'}]}]
    assert bd.resolve_polymarket_token("slug", http=lambda u: body) == "999"
