"""market_maker -- two-sided quotes on thin books, inventory-skewed.

Quote a BUY limit at fair - half_spread and a SELL limit at fair + half_spread
to capture the spread. Inventory risk is managed by SKEWING size: when already
long, shrink the bid and grow the ask (and vice versa) so quoting pulls the
position back toward flat. Each leg is risk-checked via cap_quantity.

Honest: spread capture is real but small and exposed to adverse selection
(informed flow picks you off). This emits quotes; pnl.py records what actually
fills. No edge is claimed.
"""
from __future__ import annotations

from typing import List

try:
    from ..risk import RiskManager
    from ..venues.base import Order, OrderType, Side
    from .base import Strategy, TradeIntent
except ImportError:  # pragma: no cover
    from risk import RiskManager  # type: ignore
    from venues.base import Order, OrderType, Side  # type: ignore
    from base import Strategy, TradeIntent  # type: ignore


class MarketMaker(Strategy):
    def __init__(self, risk: RiskManager, base_qty: int = 100,
                 inventory_band: int = 500) -> None:
        self.risk = risk
        self.base_qty = int(base_qty)
        # net position (in contracts) at which a side is fully skewed off
        self.inventory_band = max(int(inventory_band), 1)

    @property
    def name(self) -> str:
        return "market_maker"

    def evaluate(self, market_id: str, fair_prob: float, half_spread: float,
                 event_id: str = "") -> List[TradeIntent]:
        bid_px = round(max(fair_prob - half_spread, 0.01), 4)
        ask_px = round(min(fair_prob + half_spread, 0.99), 4)
        if bid_px >= ask_px:
            return []
        pos = self.risk.venue.get_positions().get(market_id)
        net = pos.net_qty if pos else 0
        skew = max(min(net / float(self.inventory_band), 1.0), -1.0)
        bid_qty = int(self.base_qty * (1.0 - skew))   # long -> smaller bid
        ask_qty = int(self.base_qty * (1.0 + skew))   # long -> bigger ask
        out: List[TradeIntent] = []
        bq = self.risk.cap_quantity(market_id, Side.BUY, bid_px, max(bid_qty, 0),
                                    event_id)
        if bq > 0:
            out.append(TradeIntent(self.risk.venue,
                                   Order(market_id, Side.BUY, bq, OrderType.LIMIT,
                                         bid_px), "mm bid"))
        aq = self.risk.cap_quantity(market_id, Side.SELL, ask_px, max(ask_qty, 0),
                                    event_id)
        if aq > 0:
            out.append(TradeIntent(self.risk.venue,
                                   Order(market_id, Side.SELL, aq, OrderType.LIMIT,
                                         ask_px), "mm ask"))
        return out
