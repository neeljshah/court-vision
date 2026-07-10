"""scripts.platformkit.execution.executor.mock_exchange -- deterministic mock
Kalshi exchange for lifecycle tests + dry-run parity. NO network, NO real
orders -- fills come only from recorded book_depth snapshots (fill only if the
captured depth supports it at that price; same realism discipline as
scripts/platformkit/execution/fill_model/fill_realism.py). Supports partial
fills, injected 429s, and the cancel-after-fill race.

Prices are Kalshi cents (int 1..99), matching scripts/execute_loop/
L09_kalshi_client.py's convention; book_depth snapshot rows carry 0-1 floats
(best_bid/best_ask) and are converted on load. book_thinness is the archive's
only size field (no per-side ladder in the dense archive) -- it caps fillable
size per side.  # ponytail: per-side size = book_thinness; split per-level when depth_history ladders are wired in.

INVARIANTS: <=300 LOC; ASCII; stdlib only; never writes data/registry/;
never flips a flag; no $/ROI/edge language.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_mock_exchange.py -q
"""
from __future__ import annotations

import itertools
from typing import Any, Dict, Iterable, List, Optional

VALID_SIDES = ("yes", "no")


def _cents(p: Any) -> Optional[int]:
    """0-1 float probability -> whole cents 1..99, else None."""
    try:
        c = int(round(float(p) * 100.0))
    except (TypeError, ValueError):
        return None
    return c if 1 <= c <= 99 else None


def validate_order(side: str, qty: int, price_cents: int) -> Optional[str]:
    """Reject reason or None. (Same rules as L09_kalshi_client._validate_order,
    restated locally to avoid importing the legacy execute_loop tree.)"""
    if side not in VALID_SIDES:
        return "side must be 'yes' or 'no'"
    if not isinstance(qty, int) or qty <= 0:
        return "qty must be a positive int"
    if not isinstance(price_cents, int) or not 1 <= price_cents <= 99:
        return "price must be 1-99 cents"
    return None


class MockKalshiExchange:
    """Deterministic in-memory exchange seeded from book_depth snapshot rows.

    Fill rule (taker realism): a YES buy at limit L fills only if the book
    shows a best_ask and L >= ask, at the ASK price (price improvement kept),
    capped by the ask-side size. A NO buy at limit L fills only if a YES bid
    exists and L >= 100 - bid (buying NO consumes YES-bid liquidity), at
    100 - bid, capped by the bid-side size. Unfilled remainder rests and can
    fill on advance_book(). Injected failures: the first *submit_429s* submit
    calls and first *cancel_429s* cancel calls return {"status": "429"}.
    Tickers in *race_fill_on_cancel* fill their resting remainder the moment a
    cancel arrives (the cancel-after-fill race).
    """

    def __init__(self, snapshots: Optional[Iterable[Dict[str, Any]]] = None, *,
                 submit_429s: int = 0, cancel_429s: int = 0,
                 race_fill_on_cancel: Iterable[str] = ()) -> None:
        self._books: Dict[str, Dict[str, Any]] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._idem: Dict[str, str] = {}
        self._settled: Dict[str, bool] = {}
        self._submit_429s = int(submit_429s)
        self._cancel_429s = int(cancel_429s)
        self._race = set(race_fill_on_cancel)
        self._seq = itertools.count(1)
        if snapshots:
            self.advance_book(snapshots)

    # -- book ------------------------------------------------------------
    def advance_book(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Load/refresh per-ticker books from book_depth-schema rows, then
        re-check every resting order against the new book. Returns rows used."""
        n = 0
        for r in rows:
            tk = r.get("ticker")
            if not tk:
                continue
            size = r.get("book_thinness")
            try:
                size = float(size) if size is not None else float("inf")
            except (TypeError, ValueError):
                size = float("inf")
            self._books[tk] = {"bid": _cents(r.get("best_bid")),
                               "ask": _cents(r.get("best_ask")),
                               "bid_sz": size, "ask_sz": size,
                               "ts": r.get("ts", "")}
            n += 1
        for o in sorted(self._orders.values(), key=lambda o: o["order_id"]):
            if o["state"] in ("resting", "partial"):
                self._try_fill(o)
        return n

    def book(self, ticker: str) -> Optional[Dict[str, Any]]:
        b = self._books.get(ticker)
        return dict(b) if b else None

    # -- fills -----------------------------------------------------------
    def _cross(self, o: Dict[str, Any]) -> Optional[tuple]:
        """(fill_price_cents, size_key) if the book crosses this order."""
        b = self._books.get(o["ticker"])
        if not b:
            return None
        if o["side"] == "yes":
            ask = b.get("ask")
            if ask is not None and o["price"] >= ask and b["ask_sz"] > 0:
                return ask, "ask_sz"
        else:
            bid = b.get("bid")
            if bid is not None and o["price"] >= 100 - bid and b["bid_sz"] > 0:
                return 100 - bid, "bid_sz"
        return None

    def _try_fill(self, o: Dict[str, Any]) -> None:
        cross = self._cross(o)
        if cross is None:
            return
        price, size_key = cross
        b = self._books[o["ticker"]]
        remaining = o["qty"] - o["filled"]
        got = int(min(remaining, b[size_key]))
        if got <= 0:
            return
        b[size_key] -= got
        notional = o["avg"] * o["filled"] + price * got
        o["filled"] += got
        o["avg"] = round(notional / o["filled"], 4)
        o["state"] = "filled" if o["filled"] >= o["qty"] else "partial"

    def _force_fill_remainder(self, o: Dict[str, Any]) -> None:
        remaining = o["qty"] - o["filled"]
        if remaining <= 0:
            return
        notional = o["avg"] * o["filled"] + o["price"] * remaining
        o["filled"] = o["qty"]
        o["avg"] = round(notional / o["filled"], 4)
        o["state"] = "filled"

    # -- order API -------------------------------------------------------
    def submit(self, ticker: str, side: str, qty: int, price_cents: int,
               idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        if self._submit_429s > 0:
            self._submit_429s -= 1
            return {"status": "429"}
        if idempotency_key and idempotency_key in self._idem:
            oid = self._idem[idempotency_key]
            return {"status": "ack", "order_id": oid, "duplicate": True}
        reason = validate_order(side, qty, price_cents)
        if reason is None and ticker not in self._books:
            reason = "unknown ticker (no captured book)"
        if reason is not None:
            return {"status": "rejected", "reason": reason}
        oid = "mock_%06d" % next(self._seq)
        o = {"order_id": oid, "ticker": ticker, "side": side, "qty": int(qty),
             "price": int(price_cents), "filled": 0, "avg": 0.0,
             "state": "resting", "idempotency_key": idempotency_key}
        self._orders[oid] = o
        if idempotency_key:
            self._idem[idempotency_key] = oid
        self._try_fill(o)
        return {"status": "ack", "order_id": oid}

    def status(self, order_id: str) -> Optional[Dict[str, Any]]:
        o = self._orders.get(order_id)
        return dict(o) if o else None

    def cancel(self, order_id: str) -> Dict[str, Any]:
        if self._cancel_429s > 0:
            self._cancel_429s -= 1
            return {"status": "429"}
        o = self._orders.get(order_id)
        if o is None:
            return {"status": "unknown_order"}
        if o["ticker"] in self._race and o["state"] in ("resting", "partial"):
            self._force_fill_remainder(o)  # the fill beat the cancel
        if o["state"] == "filled":
            return {"status": "already_filled"}
        if o["state"] == "cancelled":
            return {"status": "cancelled", "duplicate": True}
        o["state"] = "cancelled"
        return {"status": "cancelled", "filled": o["filled"]}

    # -- settlement -------------------------------------------------------
    def settle_market(self, ticker: str, yes_result: bool) -> None:
        self._settled[ticker] = bool(yes_result)

    def settlement_value(self, order_id: str) -> Optional[int]:
        """Cents per filled contract (100 or 0) once the market settled."""
        o = self._orders.get(order_id)
        if o is None or o["ticker"] not in self._settled:
            return None
        won = self._settled[o["ticker"]] == (o["side"] == "yes")
        return 100 if won else 0


__all__ = ["MockKalshiExchange", "validate_order", "VALID_SIDES"]
