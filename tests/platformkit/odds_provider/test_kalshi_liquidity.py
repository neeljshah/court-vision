"""Per-file test for odds_provider.kalshi_liquidity (pure, offline).

  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/odds_provider/test_kalshi_liquidity.py -q
"""
from __future__ import annotations

from scripts.platformkit.odds_provider import kalshi_liquidity as liq

_LIQUID = {
    "yes_bid_dollars": 0.53, "yes_ask_dollars": 0.54,
    "yes_bid_size_fp": 71910.0, "yes_ask_size_fp": 1000227.0,
    "volume_fp": 606488.0,
}

_ILLIQUID = {
    "yes_bid_dollars": 0.10, "yes_ask_dollars": 0.80,
    "yes_bid_size_fp": None, "yes_ask_size_fp": None, "volume_fp": 0.0,
}

_DEPRECATED_ONLY = {
    "yes_bid": 47, "yes_ask": 49, "volume": 1234,
    "yes_bid_dollars": None, "yes_ask_dollars": None,
    "yes_bid_size_fp": None, "yes_ask_size_fp": None, "volume_fp": None,
}


def test_is_liquid_gate():
    assert liq.is_liquid(_LIQUID) is True
    assert liq.is_liquid(_ILLIQUID) is False
    assert liq.is_liquid(_DEPRECATED_ONLY) is False


def test_is_liquid_malformed_market_never_raises():
    assert liq.is_liquid({}) is False
    assert liq.is_liquid(None) is False  # type: ignore[arg-type]


def test_custom_thresholds():
    tight = dict(_LIQUID, yes_ask_dollars=0.60)  # 7c spread
    assert liq.is_liquid(tight) is False
    assert liq.is_liquid(tight, max_spread=0.10) is True
