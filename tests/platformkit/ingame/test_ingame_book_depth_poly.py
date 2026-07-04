"""Per-file test for ingame_book_depth_poly (Polymarket depth reader).

OFFLINE + deterministic: http is injected, no network.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_ingame_book_depth_poly.py -q
"""
from __future__ import annotations

from scripts.platformkit.ingame import ingame_book_depth_poly as pd

_BOOK_BODY = {
    "bids": [{"price": "0.10", "size": "100"}, {"price": "0.12", "size": "50"},
             {"price": "0.13", "size": "200"}],
    "asks": [{"price": "0.20", "size": "30"}, {"price": "0.15", "size": "80"},
             {"price": "0.14", "size": "10"}],
}

_EVENTS_BODY = [
    {
        "slug": "nba-lal-bos",
        "markets": [
            {"clobTokenIds": '["1111111111111111111", "2222222222222222222"]'},
        ],
    }
]


def _http_book(url: str):
    assert "book?token_id=" in url
    return _BOOK_BODY


def _http_events(url: str):
    assert "events?slug=" in url
    return _EVENTS_BODY


def test_parse_book_best_bid_ask_thinness():
    best_bid, best_ask, bid_thin, ask_thin, n_levels = pd.parse_book(_BOOK_BODY)
    assert best_bid == 0.13  # last entry of ASC bids
    assert best_ask == 0.14  # last entry of DESC asks (lowest ask)
    assert bid_thin == 50 + 200 + 100  # only 3 levels -> all summed
    assert ask_thin == 80 + 10 + 30
    assert n_levels == 6


def test_parse_book_malformed_never_raises():
    assert pd.parse_book({}) == (None, None, 0.0, 0.0, 0)
    assert pd.parse_book({"bids": "bad", "asks": None}) == (None, None, 0.0, 0.0, 0)


def test_spread_bp():
    assert pd.spread_bp(0.13, 0.14) is not None
    assert round(pd.spread_bp(0.13, 0.14), 2) == 100.0
    assert pd.spread_bp(None, 0.14) is None
    assert pd.spread_bp(0.20, 0.10) is None  # crossed


def test_resolve_token_from_gamma_slug():
    token = pd.resolve_token("nba-lal-bos", http=_http_events)
    assert token == "1111111111111111111"


def test_resolve_token_outcome_index_out_of_range_falls_back_to_zero():
    token = pd.resolve_token("nba-lal-bos", http=_http_events, outcome_index=5)
    assert token == "1111111111111111111"


def test_resolve_token_no_markets_or_bad_shape_returns_none():
    assert pd.resolve_token("x", http=lambda u: []) is None
    assert pd.resolve_token("x", http=lambda u: [{"markets": []}]) is None
    assert pd.resolve_token("x", http=lambda u: (_ for _ in ()).throw(ConnectionError())) is None


def test_fetch_book_row_full():
    row = pd.fetch_book_row("1111111111111111111", http=_http_book, ts="2026-07-06T00:00:00Z")
    assert row["venue"] == "polymarket"
    assert row["best_bid"] == 0.13
    assert row["best_ask"] == 0.14
    assert row["last_trade_ts"] is None  # documented gap: no keyless trades tape by token
    assert row["trades_last_5m"] == 0


def test_fetch_book_row_http_failure_returns_none():
    def _boom(url):
        raise ConnectionError("dead")
    assert pd.fetch_book_row("X", http=_boom, ts="t") is None


def test_fetch_book_row_non_dict_body_returns_none():
    assert pd.fetch_book_row("X", http=lambda u: [1, 2, 3], ts="t") is None
