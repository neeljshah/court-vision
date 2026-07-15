"""Per-file test for odds_provider.kalshi_tick_depth (pure, no I/O).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_tick_depth.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider.kalshi_tick_depth import best_bid_ask, spread_bp


def test_best_bid_ask_reads_live_dollars_fields():
    market = {"yes_bid_dollars": 0.53, "yes_ask_dollars": 0.54}
    assert best_bid_ask(market) == (0.53, 0.54)


def test_best_bid_ask_none_when_unquoted_never_fabricated():
    assert best_bid_ask({}) == (None, None)
    assert best_bid_ask({"yes_bid_dollars": 0.53}) == (0.53, None)


def test_best_bid_ask_ignores_deprecated_bare_int_fields():
    # yes_bid/yes_ask (no _dollars suffix) read None on the live API -- must never
    # be read as a fallback (would silently reintroduce the deprecated-field bug).
    market = {"yes_bid": 53, "yes_ask": 54, "yes_bid_dollars": None, "yes_ask_dollars": None}
    assert best_bid_ask(market) == (None, None)


def test_spread_bp_matches_canonical_bp_formula():
    assert abs(spread_bp(0.53, 0.54) - 100.0) < 1e-9   # 1c spread = 100bp of a $1 contract


def test_spread_bp_none_when_either_side_unquoted():
    assert spread_bp(None, 0.54) is None
    assert spread_bp(0.53, None) is None
    assert spread_bp(None, None) is None


def test_spread_bp_none_when_book_crossed():
    assert spread_bp(0.60, 0.50) is None  # bid > ask -- never fabricate a negative spread
