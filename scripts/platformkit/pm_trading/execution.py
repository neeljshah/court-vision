"""execution.py -- BEST EXECUTION for a risk-checked order.

Takes an already-sized, risk-approved Order and works it on a MarketVenue to
get the best fill it can WITHOUT paying more than a slippage cap:

  - tick + min-size rounding (reject sub-minimum orders),
  - start passive at the touch and step toward the market one tick at a time
    only on a partial fill (re-quote), never beyond ref +/- max_slippage,
  - order splitting into child orders so a price that runs away is abandoned
    mid-way instead of sweeping the book,
  - returns an ExecReport with realized avg price, slippage, and every fill.

Deterministic against PaperVenue (book depletes as children fill), so the
forward paper-validation harness reproduces exactly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

try:
    from .venues.base import Fill, MarketVenue, Order, OrderType, Side
except ImportError:  # pragma: no cover  (flat import for hermetic tests)
    from venues.base import Fill, MarketVenue, Order, OrderType, Side  # type: ignore


@dataclass
class ExecConfig:
    tick: float = 0.01           # minimum price increment
    min_size: int = 1            # minimum order size in contracts
    max_slippage: float = 0.02   # max adverse move from the reference price
    child_size: int = 0          # 0 => single child (no split)
    max_requotes: int = 3        # max times to step the limit toward market


@dataclass
class ExecReport:
    market_id: str
    side: Side
    requested_qty: int
    filled_qty: int = 0
    avg_price: float = 0.0
    ref_price: float = 0.0
    slippage: float = 0.0        # >=0 means worse than ref (a cost)
    n_orders: int = 0
    status: str = "NOFILL"       # FILLED | PARTIAL | NOFILL | REJECTED
    fills: List[Fill] = field(default_factory=list)


class BestExecution:
    def __init__(self, config: Optional[ExecConfig] = None) -> None:
        self.cfg = config or ExecConfig()

    def _round_tick(self, price: float) -> float:
        t = self.cfg.tick
        return round(round(price / t) * t, 10)

    def _ref_price(self, venue: MarketVenue, order: Order) -> Optional[float]:
        ob = venue.get_orderbook(order.market_id)
        touch = ob.best_ask() if order.side == Side.BUY else ob.best_bid()
        if touch is not None:
            return touch.price
        return order.limit_price

    def _cap_limit(self, side: Side, ref: float, order_limit: Optional[float]) -> float:
        if side == Side.BUY:
            cap = self._round_tick(ref + self.cfg.max_slippage)
            if order_limit is not None:
                cap = min(cap, order_limit)
            return min(cap, 1.0)
        cap = self._round_tick(ref - self.cfg.max_slippage)
        if order_limit is not None:
            cap = max(cap, order_limit)
        return max(cap, 0.0)

    def _within_cap(self, working: float, cap: float, side: Side) -> bool:
        if side == Side.BUY:
            return working <= cap + 1e-9
        return working >= cap - 1e-9

    def _step(self, working: float, side: Side) -> float:
        d = self.cfg.tick if side == Side.BUY else -self.cfg.tick
        return self._round_tick(working + d)

    def execute(self, venue: MarketVenue, order: Order,
                ref_price: Optional[float] = None) -> ExecReport:
        rep = ExecReport(order.market_id, order.side, order.qty)
        qty = (order.qty // self.cfg.min_size) * self.cfg.min_size
        if qty < self.cfg.min_size or qty <= 0:
            rep.status = "REJECTED"
            return rep

        ref = ref_price if ref_price is not None else self._ref_price(venue, order)
        if ref is None:
            rep.status = "REJECTED"
            return rep
        rep.ref_price = round(ref, 6)
        cap = self._cap_limit(order.side, ref, order.limit_price)
        working = self._round_tick(ref)
        if not self._within_cap(working, cap, order.side):
            working = cap

        child = self.cfg.child_size or qty
        remaining = qty
        notional = 0.0
        requotes = 0
        while remaining > 0:
            q = min(child, remaining)
            o = venue.place_order(Order(order.market_id, order.side, q,
                                        OrderType.LIMIT, working))
            got = o.filled_qty
            if got > 0:
                cf = [f for f in venue.get_fills() if f.order_id == o.order_id]
                rep.fills.extend(cf)
                notional += sum(f.qty * f.price for f in cf)
                remaining -= got
                rep.n_orders += 1
            else:
                rep.n_orders += 1
            if got < q:  # partial / no fill at this price -> try one tick worse
                if requotes >= self.cfg.max_requotes:
                    break
                stepped = self._step(working, order.side)
                if not self._within_cap(stepped, cap, order.side):
                    break
                working = stepped
                requotes += 1

        rep.filled_qty = qty - remaining
        if rep.filled_qty > 0:
            rep.avg_price = round(notional / rep.filled_qty, 6)
            rep.slippage = round((rep.avg_price - ref) if order.side == Side.BUY
                                 else (ref - rep.avg_price), 6)
        if rep.filled_qty == qty:
            rep.status = "FILLED"
        elif rep.filled_qty > 0:
            rep.status = "PARTIAL"
        else:
            rep.status = "NOFILL"
        return rep
