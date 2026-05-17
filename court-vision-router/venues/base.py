"""Abstract venue interface — new venues plug in by subclassing Venue."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Level:
    """One order-book level: price in implied-prob units [0, 1], size in USD."""
    price: float
    size: float


@dataclass
class Book:
    venue: str
    market_id: str
    asks: list[Level] = field(default_factory=list)  # sorted ascending
    error: str | None = None

    @property
    def best_ask(self) -> Level | None:
        return self.asks[0] if self.asks else None

    @property
    def depth_usd(self) -> float:
        return sum(l.size for l in self.asks)


class Venue(Protocol):
    """Every venue exposes the same three ops. That's the contract."""
    name: str
    chain: str  # "polygon" | "sx" | ...

    def find_market(self, team_a: str, team_b: str) -> str | None: ...
    def fetch_book(self, market_id: str, side: str = "YES") -> Book: ...
    def submit_order(self, market_id: str, size_usd: float, limit_price: float) -> dict: ...
