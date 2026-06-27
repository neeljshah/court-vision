"""Per-file test for odds_provider.inplay_history (offline, injected http).

Exercises BOTH fetch functions on canned payloads (real Kalshi candlestick shape
+ real Polymarket prices-history shape) and asserts the canonical tick schema:
  prob in [0,1], ts ISO-8601 'Z', venue/ticker set, and the cents->prob rule.

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_inplay_history.py -q
"""
from __future__ import annotations

import re
from pathlib import Path

from scripts.platformkit.odds_provider.inplay_history import (
    fetch_price_history,
    fetch_price_history_polymarket,
    series_from_ticker,
)

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REPO = Path(__file__).resolve().parents[2]

# ---- canned Kalshi candlesticks body (real shape) ------------------------- #
_KALSHI_BODY = {
    "candlesticks": [
        {  # priced via price.close_dollars (already a dollar in [0,1])
            "end_period_ts": 1781564400,
            "price": {"close_dollars": "0.4900", "mean_dollars": "0.4898"},
            "yes_bid": {"close_dollars": "0.4800"},
            "yes_ask": {"close_dollars": "0.4900"},
        },
        {  # no price.close -> mid of yes_bid/yes_ask
            "end_period_ts": 1781568000,
            "price": {},
            "yes_bid": {"close_dollars": "0.4400"},
            "yes_ask": {"close_dollars": "0.6000"},
        },
        {  # integer-cents fallback shape -> /100
            "end_period_ts": 1781571600,
            "price": 62,
        },
        {"end_period_ts": 1781575200, "price": {}, "yes_bid": {}, "yes_ask": {}},  # skip
    ]
}

# ---- canned Polymarket prices-history body (real shape) -------------------- #
_POLY_BODY = {
    "history": [
        {"t": 1779145208, "p": 0.655},
        {"t": 1781822884, "p": 0.9935},
        {"t": 1781822999, "p": 1.5},   # out of range -> skipped
    ]
}


def _fake_http(body):
    def _get(url):
        return body
    return _get


def test_series_from_ticker():
    assert series_from_ticker("KXWCGAME-26JUN18MEXKOR-MEX") == "KXWCGAME"
    assert series_from_ticker("") == ""


def test_kalshi_ticks_match_schema_and_conversion():
    ticks = fetch_price_history(
        "", "KXWCGAME-26JUN18MEXKOR-MEX", 0, 1, 60,
        sport="soccer_intl", side="MEX", http=_fake_http(_KALSHI_BODY))
    assert len(ticks) == 3  # 4th candle has no usable price -> skipped
    for t in ticks:
        assert t["venue"] == "kalshi"
        assert t["sport"] == "soccer_intl"
        assert t["side"] == "MEX"
        assert t["ticker"] == "KXWCGAME-26JUN18MEXKOR-MEX"
        assert isinstance(t["prob"], float) and 0.0 <= t["prob"] <= 1.0
        assert _ISO.match(t["ts"]), t["ts"]
    # close_dollars used directly
    assert abs(ticks[0]["prob"] - 0.49) < 1e-9
    # mid of 0.44 / 0.60
    assert abs(ticks[1]["prob"] - 0.52) < 1e-9
    # integer cents 62 -> 0.62
    assert abs(ticks[2]["prob"] - 0.62) < 1e-9


def test_polymarket_ticks_match_schema():
    ticks = fetch_price_history_polymarket(
        "0xtoken", "max", 60, sport="soccer_intl", side="CAN",
        ticker="CAN-win", http=_fake_http(_POLY_BODY))
    assert len(ticks) == 2  # 1.5 out of range -> skipped
    for t in ticks:
        assert t["venue"] == "polymarket"
        assert t["ticker"] == "CAN-win"
        assert isinstance(t["prob"], float) and 0.0 <= t["prob"] <= 1.0
        assert _ISO.match(t["ts"]), t["ts"]
    assert ticks[0]["prob"] == 0.655
    assert ticks[1]["prob"] == 0.9935
    assert ticks[0]["ts"] == "2026-05-18T23:00:08Z"


def test_empty_or_bad_body_yields_empty_list():
    assert fetch_price_history("S", "T", 0, 1, http=_fake_http({})) == []
    assert fetch_price_history_polymarket("x", http=_fake_http({"history": "bad"})) == []

    def _boom(url):
        raise RuntimeError("network down")

    assert fetch_price_history("S", "T", 0, 1, http=_boom) == []
    assert fetch_price_history_polymarket("x", http=_boom) == []


def test_committed_real_fixtures_are_valid_schema():
    """The captured REAL fixtures parse and obey the canonical schema."""
    for rel, venue in (
        ("tests/fixtures/inplay/kalshi_soccer_intl_sample.jsonl", "kalshi"),
        ("tests/fixtures/inplay/polymarket_soccer_intl_sample.jsonl", "polymarket"),
    ):
        import json
        path = _REPO / rel
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        assert len(rows) >= 10, rel
        for r in rows:
            assert r["venue"] == venue
            assert 0.0 <= r["prob"] <= 1.0
            assert _ISO.match(r["ts"]), r["ts"]
            assert set(r) >= {"sport", "game_id", "venue", "market_type",
                              "side", "ticker", "prob", "ts"}
