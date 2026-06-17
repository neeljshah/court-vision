"""live_stubs.py -- env-gated REAL venue stubs (Kalshi, Polymarket).

These exist so the system can SEE that real venues would slot into the same
MarketVenue interface -- WITHOUT doing anything dangerous:

  - They check API-key PRESENCE only (os.environ), never read/store/log the
    key VALUE. has_credentials() returns a bool, never the secret.
  - is_live() returns True, so risk.py blocks every order while
    pm_trading.ENABLED is OFF (the default). Strategies never reach place_order.
  - place_order() and cancel_order() HARD-REFUSE (raise) -- no real order is
    ever sent from this code. Wiring the real REST/WebSocket endpoints is a
    later, HUMAN-CONFIRM step (see docs/research/pm-trading/GO-LIVE-CHECKLIST.md).
  - Read methods return safe empties so a daemon poll never crashes; wired()
    is False to advertise that live market data is not implemented here.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

try:
    from .base import Balance, MarketVenue, Order, OrderBook, Position
except ImportError:  # pragma: no cover  (flat import for hermetic tests)
    from base import Balance, MarketVenue, Order, OrderBook, Position  # type: ignore


class _LiveVenueStub(MarketVenue):
    ENV_KEYS: tuple = ()
    VENUE_NAME: str = "live"

    def __init__(self) -> None:
        # PRESENCE only -- we never copy the secret out of the environment.
        self._has_creds = all(bool(os.environ.get(k)) for k in self.ENV_KEYS)

    @property
    def name(self) -> str:
        return self.VENUE_NAME

    def is_live(self) -> bool:
        return True

    def wired(self) -> bool:
        """Real market-data/order endpoints implemented? Always False here."""
        return False

    def has_credentials(self) -> bool:
        return self._has_creds

    def missing_credentials(self) -> List[str]:
        return [k for k in self.ENV_KEYS if not os.environ.get(k)]

    # -- read: safe empties (no network in a stub) ----------------------
    def get_orderbook(self, market_id: str) -> OrderBook:
        return OrderBook(market_id=market_id)

    def get_price(self, market_id: str) -> Optional[float]:
        return None

    def get_positions(self) -> Dict[str, Position]:
        return {}

    def get_balance(self) -> Balance:
        return Balance(cash=0.0)

    def get_fills(self) -> list:
        return []

    # -- write: HARD REFUSE ---------------------------------------------
    def place_order(self, order: Order) -> Order:
        raise RuntimeError(
            "%s: REFUSED to place a real order. PAPER-FIRST env-gated stub -- "
            "live trading requires wiring the real API AND a HUMAN-CONFIRM "
            "go-live with pm_trading.ENABLED on. No real order was sent."
            % self.VENUE_NAME)

    def cancel_order(self, order_id: str) -> bool:
        raise RuntimeError(
            "%s: live cancel not wired (env-gated stub)." % self.VENUE_NAME)


class KalshiVenue(_LiveVenueStub):
    """Kalshi (CFTC-regulated). Needs KALSHI_API_KEY + KALSHI_API_SECRET."""
    ENV_KEYS = ("KALSHI_API_KEY", "KALSHI_API_SECRET")
    VENUE_NAME = "kalshi"


class PolymarketVenue(_LiveVenueStub):
    """Polymarket CLOB. Needs POLYMARKET_API_KEY (or a wallet key, presence-only)."""
    ENV_KEYS = ("POLYMARKET_API_KEY",)
    VENUE_NAME = "polymarket"
