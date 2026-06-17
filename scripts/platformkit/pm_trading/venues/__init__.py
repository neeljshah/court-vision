"""Venue adapters: one normalized surface over many exchanges.

base.py    -- MarketVenue ABC + normalized prediction-market data model.
paper.py   -- PaperVenue, the deterministic default (no keys, no network).

Real Kalshi/Polymarket adapters are added later as env-gated stubs that check
key PRESENCE only and NEVER place a real order without HUMAN-CONFIRM.
"""

from .base import (
    Side,
    OrderType,
    OrderStatus,
    Level,
    OrderBook,
    Order,
    Fill,
    Position,
    Balance,
    MarketVenue,
)
from .paper import PaperVenue
from .live_stubs import KalshiVenue, PolymarketVenue

__all__ = [
    "Side",
    "OrderType",
    "OrderStatus",
    "Level",
    "OrderBook",
    "Order",
    "Fill",
    "Position",
    "Balance",
    "MarketVenue",
    "PaperVenue",
    "KalshiVenue",
    "PolymarketVenue",
]
