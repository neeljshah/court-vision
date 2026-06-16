"""cross_market_arb -- lock the spread on the SAME contract across two venues.

If YES is buyable on venue A cheaper than it is sellable on venue B
(best_ask_A < best_bid_B), buy YES on A and sell YES on B: the two legs are
the same outcome, so at settlement they net to zero exposure and you keep
(bid_B - ask_A) per contract regardless of who wins -- market-neutral.

Both legs are sized to min(book depth) and then risk-checked on EACH venue's
own RiskManager (the gate doesn't see the cross-venue hedge, so caps are
applied conservatively per venue). Returns the smaller approved leg size so
the hedge stays balanced. Honest: real arb is rare, tiny, and seconds-long
(see projection.py) -- this just emits the order pair when it genuinely exists.
"""
from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass
from typing import List, Optional

_PKG = pathlib.Path(__file__).resolve().parents[1]   # pm_trading
_DIR = pathlib.Path(__file__).resolve().parent       # strategies
for _p in (str(_PKG), str(_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from base import Strategy, TradeIntent  # noqa: E402
from risk import RiskManager  # noqa: E402
from venues.base import MarketVenue, Order, OrderType, Side  # noqa: E402


@dataclass
class ArbOpportunity:
    locked_edge: float          # $ per contract captured (bid - ask)
    qty: int
    buy: TradeIntent            # buy YES on the cheaper venue
    sell: TradeIntent           # sell YES on the dearer venue


class CrossMarketArb(Strategy):
    def __init__(self, min_edge: float = 0.0) -> None:
        self.min_edge = float(min_edge)  # $ per contract, net of fees you assume

    @property
    def name(self) -> str:
        return "cross_market_arb"

    def _leg(self, buy_v, sell_v, buy_rm, sell_rm, market_id, ask, bid, event_id):
        if ask is None or bid is None:
            return None
        edge = bid.price - ask.price
        if edge <= self.min_edge:
            return None
        depth = min(ask.qty, bid.qty)
        qb = buy_rm.cap_quantity(market_id, Side.BUY, ask.price, depth, event_id)
        qs = sell_rm.cap_quantity(market_id, Side.SELL, bid.price, depth, event_id)
        q = min(qb, qs)
        if q <= 0:
            return None
        return ArbOpportunity(
            locked_edge=round(edge, 6), qty=q,
            buy=TradeIntent(buy_v, Order(market_id, Side.BUY, q, OrderType.LIMIT,
                                         ask.price), "arb buy @%.4f" % ask.price),
            sell=TradeIntent(sell_v, Order(market_id, Side.SELL, q, OrderType.LIMIT,
                                           bid.price), "arb sell @%.4f" % bid.price),
        )

    def evaluate(self, venue_a: MarketVenue, venue_b: MarketVenue, market_id: str,
                 risk_a: RiskManager, risk_b: RiskManager,
                 event_id: str = "") -> List[TradeIntent]:
        ba = venue_a.get_orderbook(market_id)
        bb = venue_b.get_orderbook(market_id)
        opps = []
        # direction 1: buy on A, sell on B
        o1 = self._leg(venue_a, venue_b, risk_a, risk_b, market_id,
                       ba.best_ask(), bb.best_bid(), event_id)
        # direction 2: buy on B, sell on A
        o2 = self._leg(venue_b, venue_a, risk_b, risk_a, market_id,
                       bb.best_ask(), ba.best_bid(), event_id)
        best = max([o for o in (o1, o2) if o], key=lambda o: o.locked_edge,
                   default=None)
        if best is None:
            return []
        opps.append(best)
        self.last_opportunities: List[ArbOpportunity] = opps
        return [best.buy, best.sell]
