"""Per-file test for ingame_book_depth_kalshi (Kalshi depth reader).

OFFLINE + deterministic: http is injected, no network.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_kalshi.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone

from scripts.platformkit.ingame import ingame_book_depth_kalshi as kd

_ORDERBOOK_BODY = {
    "orderbook_fp": {
        "yes_dollars": [["0.01", "100"], ["0.05", "50"], ["0.10", "30"], ["0.13", "5"]],
        "no_dollars": [["0.01", "56136"], ["0.02", "6550"], ["0.18", "80"]],
    }
}

_TRADES_BODY = {
    "trades": [
        {"created_time": "2026-07-06T02:40:13.373445Z", "yes_price_dollars": "0.95"},
        {"created_time": "2026-07-06T02:30:00.000000Z", "yes_price_dollars": "0.90"},
    ]
}


def _http_ok(url: str):
    if "orderbook" in url:
        return _ORDERBOOK_BODY
    if "trades" in url:
        return _TRADES_BODY
    raise AssertionError("unexpected url %s" % url)


def test_parse_orderbook_best_bid_ask_and_thinness():
    best_bid, best_ask, bid_thin, ask_thin, n_levels = kd.parse_orderbook(_ORDERBOOK_BODY)
    assert best_bid == 0.13  # last (highest) entry of ASC yes_dollars
    assert best_ask == 1.0 - 0.18  # 1 - highest no_price level
    assert bid_thin == 50 + 30 + 5  # top-3 closest to best (last 3 entries)
    assert ask_thin == 56136 + 6550 + 80  # only 3 levels present -> all summed
    assert n_levels == 4 + 3


def test_parse_orderbook_missing_or_malformed_never_raises():
    assert kd.parse_orderbook({}) == (None, None, 0.0, 0.0, 0)
    assert kd.parse_orderbook({"orderbook_fp": None}) == (None, None, 0.0, 0.0, 0)
    assert kd.parse_orderbook({"orderbook_fp": {"yes_dollars": "bad"}}) == (None, None, 0.0, 0.0, 0)


def test_spread_bp():
    assert round(kd.spread_bp(0.50, 0.52), 6) == 200.0  # 2c spread = 200bp
    assert kd.spread_bp(None, 0.52) is None
    assert kd.spread_bp(0.60, 0.50) is None  # negative/crossed -> None


def test_fetch_orderbook_row_none_int_fields_read_none():
    """The scout-verified trap: plain int yes_bid/yes_ask read None on live
    markets -- this reader NEVER touches those fields, only orderbook_fp."""
    row = kd.fetch_orderbook_row("KXMLBGAME-TEST-AAA", http=_http_ok, ts="2026-07-06T00:00:00Z")
    assert row is not None
    assert row["venue"] == "kalshi"
    assert row["best_bid"] == 0.13
    assert round(row["best_ask"], 6) == 0.82
    assert row["spread_bp"] is not None and row["spread_bp"] > 0


def test_fetch_orderbook_row_http_failure_returns_none():
    def _boom(url):
        raise ConnectionError("dead feed")
    assert kd.fetch_orderbook_row("X", http=_boom, ts="t") is None


def test_fetch_trades_and_recency():
    trades = kd.fetch_trades("KXMLBGAME-TEST-AAA", http=_http_ok)
    assert len(trades) == 2
    now_dt = datetime(2026, 7, 6, 2, 41, 0, tzinfo=timezone.utc)
    last_ts, n_recent = kd.trade_recency(trades, now_dt)
    assert last_ts == "2026-07-06T02:40:13.373445Z"
    assert n_recent == 1  # only the 02:40 trade is within the last 5 minutes of 02:41


def test_trade_recency_empty_or_unparseable():
    assert kd.trade_recency([], datetime.now(timezone.utc)) == (None, 0)
    bad = [{"created_time": "not-a-date"}]
    assert kd.trade_recency(bad, datetime.now(timezone.utc)) == (None, 0)


def test_snapshot_market_full_row():
    now_dt = datetime(2026, 7, 6, 2, 41, 0, tzinfo=timezone.utc)
    row = kd.snapshot_market("KXMLBGAME-TEST-AAA", http=_http_ok, now_dt=now_dt,
                             now_iso_fn=lambda: "2026-07-06T02:41:00.000000Z")
    assert row["ticker"] == "KXMLBGAME-TEST-AAA"
    assert row["trades_last_5m"] == 1
    assert row["last_trade_ts"] == "2026-07-06T02:40:13.373445Z"


def test_snapshot_market_orderbook_failure_returns_none():
    def _boom(url):
        raise TimeoutError("no response")
    assert kd.snapshot_market("X", http=_boom, now_dt=datetime.now(timezone.utc),
                              now_iso_fn=lambda: "t") is None


def test_normalize_trade_extracts_price_and_ts():
    n = kd.normalize_trade({"created_time": "2026-07-06T02:40:13.373445Z",
                            "yes_price_dollars": "0.95", "count": "3",
                            "taker_side": "yes", "trade_id": "T1"})
    assert n == {"trade_ts": "2026-07-06T02:40:13.373445Z", "trade_id": "T1",
                "price": 0.95, "count": 3.0, "taker_side": "yes"}


def test_normalize_trade_reads_count_fp_live_field_name():
    """2026-07-11 fix: live endpoint returns trade size on count_fp (a decimal
    string), not count -- count_fp must win when both are absent/present."""
    n = kd.normalize_trade({"created_time": "2026-07-06T02:40:13.373445Z",
                            "yes_price_dollars": "0.62", "count_fp": "75.00",
                            "taker_side": "no", "trade_id": "T2"})
    assert n["count"] == 75.0


def test_normalize_trade_unparseable_ts_is_none():
    assert kd.normalize_trade({"created_time": "not-a-date"}) is None
    assert kd.normalize_trade("not-a-dict") is None


def test_new_trades_since_cold_start_returns_whole_tape():
    new, watermark = kd.new_trades_since(_TRADES_BODY["trades"])
    assert len(new) == 2  # no prior watermark -> whole fetched tape is "new"
    assert watermark == "2026-07-06T02:40:13.373445Z"  # newest trade_ts


def test_new_trades_since_dedups_against_watermark():
    """Second call with the watermark from the first call sees only strictly
    newer trades -- the repeat is not re-persisted."""
    new, watermark = kd.new_trades_since(_TRADES_BODY["trades"])
    new2, watermark2 = kd.new_trades_since(_TRADES_BODY["trades"], watermark=watermark)
    assert new2 == []  # same tape, nothing newer than the watermark
    assert watermark2 == watermark


def test_new_trades_since_caps_at_limit():
    trades = [{"created_time": "2026-07-06T02:00:%02d.000000Z" % i,
              "yes_price_dollars": "0.50"} for i in range(10)]
    new, _ = kd.new_trades_since(trades, limit=3)
    assert len(new) == 3
    assert new[-1]["trade_ts"] == "2026-07-06T02:00:09.000000Z"  # newest kept


def test_snapshot_market_carries_transient_trade_keys():
    now_dt = datetime(2026, 7, 6, 2, 41, 0, tzinfo=timezone.utc)
    row = kd.snapshot_market("KXMLBGAME-TEST-AAA", http=_http_ok, now_dt=now_dt,
                             now_iso_fn=lambda: "2026-07-06T02:41:00.000000Z")
    assert len(row["_new_trades"]) == 2
    assert row["_new_trades"][0]["price"] == 0.90  # sorted ascending by trade_ts
    assert row["_trade_watermark"] == "2026-07-06T02:40:13.373445Z"
