"""PaperVenue -- the deterministic default venue (no keys, no network).

A fully in-memory exchange. You seed it with order books; it matches incoming
orders against that resting liquidity with a deterministic price-time engine,
mutating the seeded depth so later orders see what earlier orders consumed.
Identical inputs -> identical fills, every run (no wall-clock, no randomness),
which is what the forward-paper validation harness requires.

Matching:
  BUY  consumes asks priced <= limit (any price for MARKET), cheapest first.
  SELL consumes bids priced >= limit (any price for MARKET), highest first.
  Taker fills at the resting level price. Unfilled LIMIT remainder rests OPEN
  (cancellable) but is not auto-filled -- no synthetic counterparties arrive.

Fees: fee = fee_bps/1e4 * (qty * price) per fill; default 0.0.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

try:  # works as a package import or as a flat sibling import (hermetic tests)
    from .base import (
        Balance, Fill, Level, MarketVenue, Order, OrderBook,
        OrderStatus, OrderType, Position, Side,
    )
except ImportError:  # pragma: no cover
    from base import (  # type: ignore
        Balance, Fill, Level, MarketVenue, Order, OrderBook,
        OrderStatus, OrderType, Position, Side,
    )


class PaperVenue(MarketVenue):
    def __init__(
        self,
        initial_cash: float = 10_000.0,
        books: Optional[Dict[str, OrderBook]] = None,
        fee_bps: float = 0.0,
        clock: Optional[Callable[[int], str]] = None,
    ) -> None:
        self._cash = float(initial_cash)
        self._books: Dict[str, OrderBook] = dict(books or {})
        self._fee_bps = float(fee_bps)
        self._clock = clock or (lambda n: "t%d" % n)
        self._positions: Dict[str, Position] = {}
        self._fills: List[Fill] = []
        self._open: Dict[str, Order] = {}
        self._seq = 0

    @property
    def name(self) -> str:
        return "paper"

    # -- market data -----------------------------------------------------
    def set_book(self, book: OrderBook) -> None:
        """Seed or refresh the resting liquidity for one market."""
        self._books[book.market_id] = book

    def get_orderbook(self, market_id: str) -> OrderBook:
        return self._books.get(market_id, OrderBook(market_id=market_id))

    def get_price(self, market_id: str) -> Optional[float]:
        return self.get_orderbook(market_id).mid()

    # -- account ---------------------------------------------------------
    def get_balance(self) -> Balance:
        reserved = sum(
            o.limit_price * (o.qty - o.filled_qty)
            for o in self._open.values()
            if o.side == Side.BUY and o.limit_price is not None
        )
        return Balance(cash=round(self._cash, 6), reserved=round(reserved, 6))

    def get_positions(self) -> Dict[str, Position]:
        return {m: p for m, p in self._positions.items() if p.net_qty != 0 or p.realized_pnl}

    def get_fills(self) -> List[Fill]:
        return list(self._fills)

    def cancel_order(self, order_id: str) -> bool:
        o = self._open.pop(order_id, None)
        if o is None:
            return False
        o.status = OrderStatus.CANCELLED
        return True

    # -- order entry -----------------------------------------------------
    def place_order(self, order: Order) -> Order:
        self._seq += 1
        order.order_id = "PAPER-O-%d" % self._seq
        order.ts = order.ts or self._clock(self._seq)
        if not self._validate(order):
            order.status = OrderStatus.REJECTED
            return order

        book = self.get_orderbook(order.market_id)
        levels = list(book.asks if order.side == Side.BUY else book.bids)
        remaining = order.qty
        notional = 0.0
        consumed: List[Level] = []

        for lvl in levels:
            if remaining <= 0:
                break
            if not self._crosses(order, lvl.price):
                break
            take = min(remaining, lvl.qty)
            self._record_fill(order, take, lvl.price)
            notional += take * lvl.price
            remaining -= take
            leftover = lvl.qty - take
            consumed.append(Level(lvl.price, leftover) if leftover > 0 else Level(lvl.price, 0))

        self._rewrite_book(order, book, levels, consumed)

        order.filled_qty = order.qty - remaining
        order.avg_fill_price = round(notional / order.filled_qty, 6) if order.filled_qty else 0.0
        if remaining == 0:
            order.status = OrderStatus.FILLED
        elif order.filled_qty > 0:
            order.status = OrderStatus.PARTIAL
        else:
            order.status = OrderStatus.NEW

        if remaining > 0 and order.order_type == OrderType.LIMIT:
            rest = Order(
                market_id=order.market_id, side=order.side, qty=order.qty,
                order_type=OrderType.LIMIT, limit_price=order.limit_price,
                order_id=order.order_id, status=order.status,
                filled_qty=order.filled_qty, avg_fill_price=order.avg_fill_price,
                ts=order.ts,
            )
            self._open[order.order_id] = rest
        return order

    # -- internals -------------------------------------------------------
    def _validate(self, order: Order) -> bool:
        if order.qty <= 0:
            return False
        if order.order_type == OrderType.LIMIT:
            if order.limit_price is None or not (0.0 <= order.limit_price <= 1.0):
                return False
        return True

    def _crosses(self, order: Order, price: float) -> bool:
        if order.order_type == OrderType.MARKET:
            return True
        if order.side == Side.BUY:
            return price <= order.limit_price + 1e-9
        return price >= order.limit_price - 1e-9

    def _record_fill(self, order: Order, qty: int, price: float) -> None:
        fee = round(self._fee_bps / 1e4 * qty * price, 6)
        self._seq += 1
        self._fills.append(Fill(
            fill_id="PAPER-F-%d" % self._seq, order_id=order.order_id,
            market_id=order.market_id, side=order.side, qty=qty,
            price=price, fee=fee, ts=self._clock(self._seq),
        ))
        signed = qty if order.side == Side.BUY else -qty
        self._cash += -(signed * price) - fee
        self._cash = round(self._cash, 6)
        self._apply_to_position(order.market_id, order.side, qty, price)

    def _apply_to_position(self, market_id: str, side: Side, qty: int, price: float) -> None:
        pos = self._positions.setdefault(market_id, Position(market_id=market_id))
        signed = qty if side == Side.BUY else -qty
        old = pos.net_qty
        new = old + signed
        if old == 0 or (old > 0) == (signed > 0):  # opening / increasing
            total = abs(old) * pos.avg_price + qty * price
            pos.avg_price = round(total / abs(new), 6) if new else 0.0
        else:  # reducing / closing / flipping
            closed = min(abs(old), qty)
            if old > 0:
                pos.realized_pnl += closed * (price - pos.avg_price)
            else:
                pos.realized_pnl += closed * (pos.avg_price - price)
            pos.realized_pnl = round(pos.realized_pnl, 6)
            if abs(signed) > abs(old):
                pos.avg_price = price        # flipped to the other side
            elif new == 0:
                pos.avg_price = 0.0
        pos.net_qty = new

    def _rewrite_book(self, order: Order, book: OrderBook,
                      levels: List[Level], consumed: List[Level]) -> None:
        tail = levels[len(consumed):]
        remade = tuple(l for l in consumed if l.qty > 0) + tuple(tail)
        if order.side == Side.BUY:
            self._books[order.market_id] = OrderBook(
                market_id=book.market_id, bids=book.bids, asks=remade, ts=book.ts)
        else:
            self._books[order.market_id] = OrderBook(
                market_id=book.market_id, bids=remade, asks=book.asks, ts=book.ts)
