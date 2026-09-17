"""Paper-only resting maker quotes backed by the lifecycle state machine.

Quotes are submitted to MockKalshiExchange and only a later captured tick may
cross them.  This module has no live venue path, no network, and no writes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from scripts.platformkit.execution.venue_fees import fee_kalshi_maker
from scripts.platformkit.execution.executor.lifecycle import ExecOrder, OrderExecutor
from scripts.platformkit.execution.executor.mock_exchange import MockKalshiExchange
from scripts.platformkit.ingame import inplay_tick_latency as _latency
from scripts.platformkit.ingame import quote_freshness as _freshness
from scripts.platformkit.pm_trading.execution import BestExecution, ExecConfig

# A tick carrying any of these means a real venue would have pulled/voided the
# book: a resting order must CANCEL, never fill retroactively off such a tick.
_SUSPENDED_MARKET = frozenset({"suspended", "halted", "paused", "closed",
                               "settled", "voided", "void"})
_TERMINAL_GAME = frozenset({"final", "post", "postponed", "suspended",
                            "canceled", "cancelled", "abandoned"})

# Contracts per paper quote. Named so the fee below is charged on the size
# actually quoted -- Kalshi's cent-ceiling applies ONCE per order batch
# (venue_fees module docstring), so a hardcoded 1.0 in the fee call makes the
# fee a constant $0.01 at every price and carries no price information.
_QTY = 1

# Half-spread assumed when a tick carries only a mid. Kalshi in-play spread_bp
# p50 = 200bp on n=191,424 (pre-registered 2026-07-15, execution/thresholds.py
# lines 19-23) -> 2 cents wide -> 1 cent per side.
# ponytail: ONE constant for every sport, price and game phase. Ceiling: it
# cannot see a widening late book, where the real half-spread is larger and this
# rule is therefore OPTIMISTIC. Upgrade path: read the per-tick spread_bp the
# book_depth capture already produces, once that capture has a ProcSpec.
_ASSUMED_HALF_SPREAD_CENTS = 1


def _market_suspended(tick: Dict[str, Any]) -> bool:
    """True when this tick says the market could not honestly fill a resting order:
    an explicit suspension/void marker, or a terminal/suspended game state."""
    if any(bool(tick.get(k)) for k in ("suspended", "voided", "market_suspended")):
        return True
    if str(tick.get("market_status") or "").strip().lower() in _SUSPENDED_MARKET:
        return True
    state = tick.get("state")
    status = str(state.get("status") or "").strip().lower() if isinstance(state, dict) else ""
    return status in _TERMINAL_GAME


def _quote_price(probability: Any) -> Optional[int]:
    """Round a probability through the established 0.01 execution helper."""
    try:
        value = float(probability)
    except (TypeError, ValueError):
        return None
    rounded = BestExecution(ExecConfig(tick=0.01))._round_tick(value)
    cents = int(round(rounded * 100.0))
    return cents if 1 <= cents <= 99 else None


def _ttl_seconds(sport: str, tick: Dict[str, Any]) -> float:
    """Use supplied/ledger tick p50; missing evidence falls back to 30 seconds."""
    p50 = tick.get("tick_p50_sec")
    try:
        p50 = float(p50)
    except (TypeError, ValueError):
        p50 = _latency.measure_sport(sport).get("gap_p50_sec")
    try:
        return max(2.0 * float(p50), 30.0)
    except (TypeError, ValueError):
        return 30.0


def _seed_book(ticker: str, side: str, price_cents: int) -> Dict[str, Any]:
    """A one-tick-away book guarantees submission itself never counts as a fill."""
    if side == "yes":
        return {"ticker": ticker, "best_bid": max(0.01, (price_cents - 1) / 100.0),
                "best_ask": min(0.99, (price_cents + 1) / 100.0)}
    return {"ticker": ticker, "best_bid": max(0.01, (99 - price_cents) / 100.0),
            "best_ask": min(0.99, (101 - price_cents) / 100.0)}


def _cents(value: Any) -> Optional[int]:
    try:
        c = int(round(float(value) * 100.0))
    except (TypeError, ValueError):
        return None
    return c if 1 <= c <= 99 else None


def observed_book(tick: Dict[str, Any]) -> Optional[tuple]:
    """(best_bid_cents, best_ask_cents) of the YES-home book this tick shows.

    Prefers the tick's own quoted book (best_bid/best_ask, the same fields
    ingame_exec_gate.build_exec_depth reads); falls back to the mid widened by
    _ASSUMED_HALF_SPREAD_CENTS when only yes_home_prob is present. None when the
    tick shows neither -- an unpriced tick can never fill a resting quote.
    """
    bid, ask = _cents(tick.get("best_bid")), _cents(tick.get("best_ask"))
    if bid is not None and ask is not None and ask >= bid:
        return bid, ask
    mid = _cents(tick.get("yes_home_prob"))
    if mid is None:
        return None
    return mid - _ASSUMED_HALF_SPREAD_CENTS, mid + _ASSUMED_HALF_SPREAD_CENTS


def trades_through(side: str, price_cents: int, book: tuple) -> bool:
    """True iff the observed book has traded THROUGH a resting quote at
    *price_cents*, i.e. a counterparty crossed it -- not merely touched it.

    A YES bid at L is only taken out once the yes offer sits strictly BELOW L; a
    NO bid at L is the mirror (the yes bid must rise strictly above 100 - L).
    Equality is the touch case and does NOT fill: at the touch the market is
    trading at our price, which fills only the front of a queue we do not model.
    """
    bid_c, ask_c = book
    return ask_c < price_cents if side == "yes" else bid_c > 100 - price_cents


def _fill_book(ticker: str, side: str, price_cents: int) -> Dict[str, Any]:
    """A book that crosses the resting order at OUR OWN price.

    The mock exchange hands a taker any price improvement between the limit and
    the touch; a maker has none -- the resting price IS the fill price. Pinning
    the crossing level to price_cents keeps that improvement out of the series.
    """
    if side == "yes":
        return {"ticker": ticker, "best_bid": max(0.01, (price_cents - 1) / 100.0),
                "best_ask": price_cents / 100.0}
    return {"ticker": ticker, "best_bid": (100 - price_cents) / 100.0,
            "best_ask": min(0.99, (101 - price_cents) / 100.0)}


def _fill_record(order: ExecOrder, quote: Dict[str, Any], tick: Dict[str, Any],
                 book: tuple, now: datetime) -> Dict[str, Any]:
    """The markout inputs for ONE fill, stamped at fill time.

    Everything execution.markout.markout() needs to score this fill against a
    LATER mid: the side, the price we actually filled at, the fee, and the fill
    timestamp a +N-tick mark is measured from. Nothing is scored here -- the
    later mid does not exist yet at fill time.
    """
    return {"side": order.side, "price": order.avg_fill_price_cents / 100.0,
            "qty": order.filled_qty,
            "fee_units": quote.get("maker_fee_units"),
            "fee_dollars": quote.get("maker_fee_dollars"),
            "book_cents": list(book),
            "fill_ts": tick.get("src_ts") or now.isoformat(),
            "ticker": order.ticker, "clv_series": quote.get("clv_series")}


class PaperMakerAdapter:
    """Owns simulated resting quotes for one in-process paper day-trader."""

    def quote(self, sport: str, game_id: str, side: str, fair_prob: Any, *,
              units: Dict[str, Any], tick: Dict[str, Any], now: datetime) -> Dict[str, Any]:
        if _market_suspended(tick):
            # entry-side kickoff/void: a tick a real venue has already pulled
            # must never seed a FRESH resting quote (advance() only covers the
            # fill side, one tick too late).
            return {"status": "rejected", "reason": "suspended_at_entry"}
        price = _quote_price(fair_prob)
        if price is None:
            return {"status": "rejected", "reason": "bad_quote_price"}
        ticker = str(tick.get("ticker") or game_id)
        order_side = "yes" if side == "home" else "no"
        exchange = MockKalshiExchange([_seed_book(ticker, order_side, price)])
        order = ExecOrder(ticker=ticker, side=order_side,
                          qty=_QTY, price_cents=price, sport=sport)
        executor = OrderExecutor(exchange)
        executor.submit(order)
        ttl = _ttl_seconds(sport, tick)
        # venue_fees is the ONE canonical schedule; charge it on the size actually
        # quoted so the cent-ceiling is applied once per order, as the schedule
        # specifies. fee_kalshi_maker returns DOLLARS for the whole order, hence
        # both fields: maker_fee_dollars is that order total, maker_fee_units is
        # the per-contract cost the units-denominated ledger consumes (a Kalshi
        # contract pays $1, so per-contract dollars ARE probability points).
        fee_dollars = fee_kalshi_maker(_QTY, price / 100.0)
        return {"status": "resting", "sport": sport, "order": order, "exchange": exchange,
                "executor": executor, "expires_at": now.timestamp() + ttl,
                "quote_prob": price / 100.0, "ttl_seconds": ttl,
                "maker_fee_dollars": fee_dollars, "maker_fee_contracts": _QTY,
                "maker_fee_units": fee_dollars / _QTY,
                "units": dict(units), "clv_series": "paper_ingame_maker"}

    def advance(self, position: Dict[str, Any], tick: Dict[str, Any], *,
                now: datetime) -> Dict[str, Any]:
        """Advance an existing quote with one subsequent captured tick."""
        quote = position.get("maker_quote")
        if not isinstance(quote, dict):
            return {"status": "ignored"}
        order, exchange, executor = quote.get("order"), quote.get("exchange"), quote.get("executor")
        if not isinstance(order, ExecOrder) or exchange is None or executor is None:
            return {"status": "rejected", "reason": "bad_resting_quote"}
        if _market_suspended(tick):
            # kickoff/void: a suspension cancels the resting order -- it never
            # fills retroactively off a tick a real venue would have wiped.
            executor.cancel(order)
            return {"status": "cancelled_suspended", "order": order, "quote": quote}
        if now.timestamp() >= float(quote.get("expires_at", 0.0)):
            executor.cancel(order)
            return {"status": "expired", "order": order, "quote": quote}
        age = _freshness.state_age_sec(now, [{"src_ts": tick.get("src_ts")}])
        if (age is not None and
                age > _freshness.state_age_ceiling_sec(str(quote.get("sport", "")))):
            # The FILL decision must never run off a stale state (same ceiling the
            # entry gate enforces): hold the quote resting until a fresh tick
            # arrives, or the TTL cancels it.
            return {"status": "resting", "order": order, "quote": quote,
                    "reason": "stale_state", "state_age_sec": age}
        book = observed_book(tick)
        if book is None:
            return {"status": "resting", "order": order, "quote": quote,
                    "reason": "no_observed_book"}
        if not trades_through(order.side, order.price_cents, book):
            # The market touched or sat away from the quote but never crossed it.
            # The previous rule collapsed the book to a point at the mid, so a
            # touch filled: adverse selection was impossible by construction and
            # the series read optimistic.
            return {"status": "resting", "order": order, "quote": quote,
                    "reason": "no_through_trade", "book_cents": list(book)}
        exchange.advance_book([_fill_book(order.ticker, order.side, order.price_cents)])
        executor.refresh(order)
        if order.filled_qty > 0:
            return {"status": "filled", "order": order, "quote": quote,
                    "fill": _fill_record(order, quote, tick, book, now)}
        return {"status": "resting", "order": order, "quote": quote}


__all__ = ["PaperMakerAdapter", "observed_book", "trades_through"]
