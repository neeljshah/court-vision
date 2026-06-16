"""Strategy base types.

A strategy turns market state into TradeIntents -- a (venue, order) pair the
runner will place. Every order in a TradeIntent has ALREADY passed the risk
gate (sized by RiskManager.approve / cap_quantity), so the runner just routes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

try:
    from ..venues.base import MarketVenue, Order
except ImportError:  # pragma: no cover  (flat import for hermetic tests)
    from venues.base import MarketVenue, Order  # type: ignore


@dataclass
class TradeIntent:
    venue: MarketVenue
    order: Order
    note: str = ""


class Strategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def evaluate(self, *args, **kwargs) -> List[TradeIntent]:
        """Return zero or more risk-checked TradeIntents for current state."""
        ...
