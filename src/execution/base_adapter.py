"""
src/execution/base_adapter.py — Abstract exchange adapter interface.

All exchange adapters (Kalshi, Polymarket, Sporttrade) implement ExchangeAdapter.
DryRunAdapter is the default when LIVE_BETTING=0.

LIVE_BETTING env var (global kill switch):
  0 (default) = paper/dry-run mode — orders logged, never placed
  1           = live mode — real orders sent to exchanges
"""
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

_log = logging.getLogger(__name__)

LIVE_BETTING: bool = os.getenv("LIVE_BETTING", "0") == "1"


def live_betting_enabled() -> bool:
    """Return True only when LIVE_BETTING=1. Read fresh so tests can patch it."""
    return os.getenv("LIVE_BETTING", "0") == "1"


def assert_live_betting_enabled(exchange: str = "exchange") -> None:
    """Hard kill-switch guard for real order placement (task 19-01).

    Any adapter that places a REAL order MUST call this at the top of
    place_limit_order().  Raises RuntimeError when LIVE_BETTING != "1" so a
    real order can never be sent while the system is in paper mode — a
    code-level enforcement that a stray config flag cannot override.
    """
    if not live_betting_enabled():
        raise RuntimeError(
            f"LIVE_BETTING is not enabled — refusing real order placement on "
            f"'{exchange}'. Set LIVE_BETTING=1 to permit live betting."
        )


@dataclass
class MarketQuote:
    exchange: str
    ticker: str
    yes_ask: float          # cost to buy YES (0.0–1.0)
    yes_bid: float
    available_contracts: int


@dataclass
class OrderResult:
    exchange: str
    order_id: str
    ticker: str
    side: str               # "yes" or "no"
    count: int
    fill_price: float       # 0.0–1.0
    status: str             # "resting" | "filled" | "paper"


class ExchangeAdapter(ABC):
    """Abstract base for all exchange adapters."""

    @abstractmethod
    def get_quote(self, market_id: str) -> Optional[MarketQuote]:
        """Fetch current best ask/bid for a binary contract."""
        ...

    @abstractmethod
    def place_limit_order(
        self,
        ticker: str,
        side: str,      # "yes" or "no"
        count: int,
        price: float,   # 0.0–1.0
    ) -> OrderResult:
        """Submit a limit order. Raises on exchange error."""
        ...

    @abstractmethod
    def find_market(self, query: str) -> list:
        """Search for markets matching a player/stat string.

        Returns list of dicts with at minimum an 'id' key.
        """
        ...

    def guard_live_order(self) -> None:
        """Enforce the LIVE_BETTING kill switch before a real order.

        Subclasses that place REAL orders must call this at the start of
        place_limit_order().  Raises RuntimeError when LIVE_BETTING != 1.
        DryRunAdapter intentionally does not call it — it never places real
        orders.
        """
        assert_live_betting_enabled(self.__class__.__name__)


class DryRunAdapter(ExchangeAdapter):
    """Logs all order intent without hitting any exchange.

    Used when LIVE_BETTING=0. Returns synthetic quotes at 0.50 even-money.
    """

    def get_quote(self, market_id: str) -> MarketQuote:
        return MarketQuote(
            exchange="dry_run",
            ticker=market_id,
            yes_ask=0.50,
            yes_bid=0.49,
            available_contracts=999,
        )

    def place_limit_order(self, ticker: str, side: str, count: int, price: float) -> OrderResult:
        _log.info("[DRY RUN] Would place: %dx %s @ %.3f on %s", count, side, price, ticker)
        return OrderResult(
            exchange="dry_run",
            order_id="paper",
            ticker=ticker,
            side=side,
            count=count,
            fill_price=price,
            status="paper",
        )

    def find_market(self, query: str) -> list:
        return [{"id": query, "title": f"dry-run:{query}"}]
