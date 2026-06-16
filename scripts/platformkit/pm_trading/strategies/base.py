"""Strategy base types.

A strategy turns market state into TradeIntents -- a (venue, order) pair the
runner will place. Every order in a TradeIntent has ALREADY passed the risk
gate (sized by RiskManager.approve / cap_quantity), so the runner just routes.
"""
from __future__ import annotations

import pathlib
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

# Make imports context-independent (flat test / strategies-package / subpackage).
_PKG = pathlib.Path(__file__).resolve().parents[1]   # pm_trading
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from venues.base import MarketVenue, Order  # noqa: E402


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
