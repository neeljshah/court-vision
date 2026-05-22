"""
test_book_router.py -- Tests for the execution-layer foundation (17-06).

Covers ExchangeAdapter ABC, MarketQuote/OrderResult dataclasses, DryRunAdapter,
and the BookRouter price-shopping router with its LIVE_BETTING=0 passthrough.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.execution.base_adapter import (  # noqa: E402
    DryRunAdapter,
    ExchangeAdapter,
    MarketQuote,
    OrderResult,
)
from src.execution.book_router import BookRouter  # noqa: E402


def _mock_adapter(exchange: str, ticker: str, yes_ask: float) -> MagicMock:
    a = MagicMock()
    a.find_market.return_value = [{"id": ticker}]
    a.get_quote.return_value = MarketQuote(
        exchange=exchange, ticker=ticker, yes_ask=yes_ask,
        yes_bid=yes_ask - 0.02, available_contracts=100,
    )
    return a


# ── base_adapter ──────────────────────────────────────────────────────────────

def test_exchange_adapter_is_abstract():
    """ExchangeAdapter cannot be instantiated directly — it is an ABC."""
    with pytest.raises(TypeError):
        ExchangeAdapter()  # type: ignore[abstract]


def test_dry_run_adapter_implements_contract():
    """DryRunAdapter satisfies the ExchangeAdapter contract."""
    adapter = DryRunAdapter()
    assert isinstance(adapter, ExchangeAdapter)
    quote = adapter.get_quote("market-x")
    assert isinstance(quote, MarketQuote)
    assert quote.exchange == "dry_run"
    result = adapter.place_limit_order("market-x", "yes", 5, 0.5)
    assert isinstance(result, OrderResult)
    assert result.status == "paper"
    assert adapter.find_market("LeBron points")[0]["id"] == "LeBron points"


# ── BookRouter ────────────────────────────────────────────────────────────────

def test_router_picks_lowest_ask():
    """The router routes to the adapter offering the lowest yes_ask."""
    kalshi = _mock_adapter("kalshi", "m-k", 0.62)
    poly = _mock_adapter("polymarket", "m-p", 0.58)
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        result = BookRouter([kalshi, poly]).route("LeBron pts o25.5", "yes", 10, 0.65)
    assert result is not None
    assert result.exchange == "polymarket"


def test_router_dry_run_returns_paper_without_placing():
    """With LIVE_BETTING=0 the router returns paper and never places an order."""
    adapter = _mock_adapter("kalshi", "m-1", 0.60)
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        result = BookRouter([adapter]).route("query", "yes", 5, 0.65)
    assert result.status == "paper"
    adapter.place_limit_order.assert_not_called()


def test_router_returns_none_when_no_market_within_max_price():
    """No adapter quoting within max_price -> route returns None."""
    expensive = _mock_adapter("kalshi", "m-1", 0.80)
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        result = BookRouter([expensive]).route("query", "yes", 5, max_price=0.65)
    assert result is None


def test_router_result_has_all_required_fields():
    """The OrderResult carries exchange, ticker, side, count, fill_price, status."""
    adapter = _mock_adapter("kalshi", "KXNBA-TEST", 0.60)
    with patch.dict(os.environ, {"LIVE_BETTING": "0"}):
        result = BookRouter([adapter]).route("q", "yes", 3, 0.65)
    for field in ("exchange", "ticker", "side", "count", "fill_price", "status"):
        assert hasattr(result, field)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
