"""MarketVenue interface + normalized prediction-market data model.

NORMALIZATION
-------------
A "market" is one binary YES contract that settles to $1.00 if the event
resolves YES and $0.00 otherwise. This single surface maps onto:
  - Kalshi    (price quoted in cents 1..99  -> divide by 100)
  - Polymarket(price quoted in USDC 0..1     -> already normalized)

CONVENTIONS
-----------
  price : float in [0, 1]   dollars per contract == implied probability.
  qty   : int               contract count (>= 1).
  Side.BUY  = open/long YES  (you profit if event resolves YES).
  Side.SELL = short YES      (== long NO; you profit if it resolves NO).

CASH MODEL (paper-simplified, honest)
-------------------------------------
Cash moves by pure trade cash-flow: a BUY pays qty*price (+fee), a SELL
receives qty*price (-fee). Collateral/margin for short YES is NOT modeled
here -- exposure is bounded by risk.py (step 5), not by venue cash. Final
settlement (net_qty * resolution) is booked by pnl.py (step 4).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"


class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class Level:
    """One price level of resting size in an order book."""
    price: float
    qty: int


@dataclass(frozen=True)
class OrderBook:
    """Top-of-book / depth snapshot. bids descending, asks ascending."""
    market_id: str
    bids: Tuple[Level, ...] = ()
    asks: Tuple[Level, ...] = ()
    ts: str = ""

    def best_bid(self) -> Optional[Level]:
        return self.bids[0] if self.bids else None

    def best_ask(self) -> Optional[Level]:
        return self.asks[0] if self.asks else None

    def mid(self) -> Optional[float]:
        b, a = self.best_bid(), self.best_ask()
        if b is not None and a is not None:
            return round((b.price + a.price) / 2.0, 6)
        return None

    def spread(self) -> Optional[float]:
        b, a = self.best_bid(), self.best_ask()
        if b is not None and a is not None:
            return round(a.price - b.price, 6)
        return None


@dataclass
class Order:
    """An order request / its post-submission state."""
    market_id: str
    side: Side
    qty: int
    order_type: OrderType = OrderType.LIMIT
    limit_price: Optional[float] = None
    order_id: str = ""
    status: OrderStatus = OrderStatus.NEW
    filled_qty: int = 0
    avg_fill_price: float = 0.0
    ts: str = ""


@dataclass(frozen=True)
class Fill:
    """A single execution against resting liquidity."""
    fill_id: str
    order_id: str
    market_id: str
    side: Side
    qty: int
    price: float
    fee: float
    ts: str


@dataclass
class Position:
    """Net open position in one market (signed contract count)."""
    market_id: str
    net_qty: int = 0          # + long YES, - short YES
    avg_price: float = 0.0    # avg cost of the currently-open side
    realized_pnl: float = 0.0


@dataclass
class Balance:
    cash: float
    reserved: float = 0.0

    @property
    def available(self) -> float:
        return round(self.cash - self.reserved, 6)


class MarketVenue(ABC):
    """Uniform interface every venue (paper or real) must implement.

    Strategies, execution, risk, and pnl talk ONLY to this interface, so the
    same code runs against PaperVenue, KalshiVenue, or PolymarketVenue.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def is_live(self) -> bool:
        """True only for adapters that touch real capital. Paper => False."""
        return False

    @abstractmethod
    def get_orderbook(self, market_id: str) -> OrderBook:
        ...

    @abstractmethod
    def get_price(self, market_id: str) -> Optional[float]:
        """Reference price (mid if two-sided, else last/best). May be None."""
        ...

    @abstractmethod
    def place_order(self, order: Order) -> Order:
        """Submit an order; returns it with id/status/fills populated."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        ...

    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        ...

    @abstractmethod
    def get_balance(self) -> Balance:
        ...

    @abstractmethod
    def get_fills(self) -> List[Fill]:
        ...
