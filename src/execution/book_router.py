"""
src/execution/book_router.py — Price-shopping order router.

Queries all registered adapters for a given market, picks the adapter
with the lowest yes_ask (best buy price), and routes the order there.

When LIVE_BETTING=0 (env var), returns a paper OrderResult without
calling any adapter's place_limit_order. This is the global kill switch.
"""
import logging
import os
from typing import Optional

from .base_adapter import (
    ExchangeAdapter,
    MarketQuote,
    OrderResult,
    assert_live_betting_enabled,
    live_betting_enabled,
)

_log = logging.getLogger(__name__)


class BookRouter:
    """Routes bets to the exchange offering the best price."""

    def __init__(self, adapters: list) -> None:
        self._adapters = adapters
        # Read the LIVE_BETTING kill switch at startup and log the mode so
        # the operating mode is unambiguous in the logs (task 19-01).
        self._startup_live = live_betting_enabled()
        _log.info(
            "BookRouter initialised with %d adapter(s) — mode=%s",
            len(adapters), "LIVE" if self._startup_live else "PAPER (LIVE_BETTING=0)",
        )

    def route(
        self,
        market_query: str,
        side: str,          # "yes" or "no"
        count: int,
        max_price: float,   # won't pay more than this (0.0–1.0)
    ) -> Optional[OrderResult]:
        """Find best price across adapters; place order or return paper result."""
        # Read LIVE_BETTING fresh each call so monkeypatching works in tests
        live = os.getenv("LIVE_BETTING", "0") == "1"

        quotes: list = []
        for adapter in self._adapters:
            try:
                markets = adapter.find_market(market_query)
                if not markets:
                    continue
                q = adapter.get_quote(markets[0]["id"])
                if q and q.yes_ask <= max_price:
                    quotes.append((adapter, q))
            except Exception as exc:  # noqa: BLE001
                _log.warning("%s quote failed: %s", adapter.__class__.__name__, exc)

        if not quotes:
            _log.info("No quotes within max_price=%.3f for: %s", max_price, market_query)
            return None

        # Best price = lowest ask
        quotes.sort(key=lambda x: x[1].yes_ask)
        best_adapter, best_quote = quotes[0]

        _log.info(
            "Routing %dx %s @ %.3f via %s (market=%s)",
            count, side, best_quote.yes_ask, best_quote.exchange, best_quote.ticker,
        )

        if not live:
            return OrderResult(
                exchange=best_quote.exchange,
                order_id="dry-run",
                ticker=best_quote.ticker,
                side=side,
                count=count,
                fill_price=best_quote.yes_ask,
                status="paper",
            )

        # Hard kill-switch guard: raises RuntimeError if LIVE_BETTING flipped
        # off between the top-of-call read and here — a real order is never
        # placed in paper mode (task 19-01).
        assert_live_betting_enabled(best_quote.exchange)
        return best_adapter.place_limit_order(
            best_quote.ticker, side, count, best_quote.yes_ask
        )
