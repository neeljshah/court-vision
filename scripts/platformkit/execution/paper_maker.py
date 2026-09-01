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
        exchange = MockKalshiExchange([_seed_book(ticker, "yes" if side == "home" else "no", price)])
        order = ExecOrder(ticker=ticker, side="yes" if side == "home" else "no",
                          qty=1, price_cents=price, sport=sport)
        executor = OrderExecutor(exchange)
        executor.submit(order)
        ttl = _ttl_seconds(sport, tick)
        return {"status": "resting", "sport": sport, "order": order, "exchange": exchange,
                "executor": executor, "expires_at": now.timestamp() + ttl,
                "quote_prob": price / 100.0, "ttl_seconds": ttl,
                "maker_fee_units": fee_kalshi_maker(1.0, price / 100.0),
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
        raw_home = tick.get("yes_home_prob")
        try:
            home = float(raw_home)
        except (TypeError, ValueError):
            return {"status": "resting", "order": order, "quote": quote}
        if not 0.0 < home < 1.0:
            return {"status": "resting", "order": order, "quote": quote}
        row = {"ticker": order.ticker, "best_bid": home, "best_ask": home}
        exchange.advance_book([row])
        executor.refresh(order)
        if order.filled_qty > 0:
            return {"status": "filled", "order": order, "quote": quote}
        return {"status": "resting", "order": order, "quote": quote}


__all__ = ["PaperMakerAdapter"]
