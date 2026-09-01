"""scripts.platformkit.execution.executor.lifecycle -- Kalshi order lifecycle
state machine: submit -> ack -> partial/fill -> cancel/replace -> settle.
Idempotency keys, bounded retry on 429 (hard caps), governor-routed via the
shared scripts.platformkit.odds_provider.kalshi_rate_governor helpers.

DOUBLE-GATED LIVE PATH -- no real order is placeable from this module:
  gate (a) env flag COURTVISION_KALSHI_LIVE_ORDERS -- intentionally does NOT
           exist anywhere in this repo and is never created by agents;
  gate (b) an explicit per-run live=True argument (a CLI --live flag).
Both absent by default; and even if BOTH were present, resolve_exchange()
still hard-refuses (NotImplementedError) because the live HTTP client is
deliberately not wired -- wiring it is a HUMAN go-live step (same discipline
as scripts/platformkit/pm_trading/venues/live_stubs.py). Default and every
test use MockKalshiExchange.

INVARIANTS: <=300 LOC; ASCII; stdlib only; never writes data/registry/;
never flips a flag; no $/ROI/edge language; politeness 1 req/s on any
(unreachable) live path via a dedicated governor share.
Test: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_lifecycle.py -q
"""
from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.odds_provider.kalshi_rate_governor import (
    BASE_RPS, KalshiRateGovernor, before_request, report_429)
from scripts.platformkit.execution.executor.mock_exchange import MockKalshiExchange

# Gate (a): this flag intentionally does not exist in any env/config in this
# repo. Agents never set it; only a human go-live would.
LIVE_FLAG_ENV = "COURTVISION_KALSHI_LIVE_ORDERS"


class OrderState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"          # submit dispatched, awaiting exchange ack
    ACKED = "ACKED"                  # exchange acknowledged, resting
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"              # gave up (timeout/retry caps exhausted)
    SETTLED = "SETTLED"


ALLOWED: Dict[OrderState, frozenset] = {
    OrderState.NEW: frozenset({OrderState.SUBMITTED, OrderState.REJECTED}),
    OrderState.SUBMITTED: frozenset({OrderState.ACKED, OrderState.REJECTED,
                                     OrderState.EXPIRED}),
    OrderState.ACKED: frozenset({OrderState.PARTIAL, OrderState.FILLED,
                                 OrderState.CANCEL_PENDING, OrderState.EXPIRED}),
    OrderState.PARTIAL: frozenset({OrderState.PARTIAL, OrderState.FILLED,
                                   OrderState.CANCEL_PENDING, OrderState.EXPIRED}),
    OrderState.CANCEL_PENDING: frozenset({OrderState.CANCELLED, OrderState.FILLED,
                                          OrderState.EXPIRED}),
    OrderState.FILLED: frozenset({OrderState.SETTLED}),
    OrderState.CANCELLED: frozenset({OrderState.SETTLED}),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
    OrderState.SETTLED: frozenset(),
}


class InvalidTransition(RuntimeError):
    pass


@dataclass
class ExecOrder:
    ticker: str
    side: str                        # "yes" | "no"
    qty: int
    price_cents: int                 # limit, Kalshi cents 1..99
    sport: str = "unknown"
    idempotency_key: str = ""
    state: OrderState = OrderState.NEW
    order_id: str = ""
    filled_qty: int = 0
    avg_fill_price_cents: float = 0.0
    settlement_cents: Optional[int] = None
    reason: str = ""
    replaces: str = ""               # idempotency_key of the order this replaced
    history: List[Tuple[float, str]] = field(default_factory=list)


def transition(order: ExecOrder, new_state: OrderState,
               clock: Callable[[], float] = time.time) -> ExecOrder:
    """Apply a lifecycle transition or raise InvalidTransition. Every applied
    transition is stamped into order.history (as-of audit trail)."""
    if new_state not in ALLOWED[order.state]:
        raise InvalidTransition("%s -> %s not allowed" % (order.state.value,
                                                          new_state.value))
    order.state = new_state
    order.history.append((clock(), new_state.value))
    return order


def idem_key(ticker: str, side: str, price_cents: int, day: str) -> str:
    """Deterministic idempotency key: same intent on the same day never
    double-submits (retries and re-runs reuse it)."""
    raw = "%s|%s|%d|%s" % (ticker, side, price_cents, day)
    return hashlib.sha1(raw.encode("ascii", "replace")).hexdigest()[:16]


def _live_flag_set() -> bool:
    return os.environ.get(LIVE_FLAG_ENV, "").strip().lower() in ("1", "true")


def resolve_exchange(live: bool = False,
                     mock: Optional[MockKalshiExchange] = None) -> MockKalshiExchange:
    """Double gate. live=False (default, and every test/dry-run) -> mock.
    live=True without the (nonexistent) env flag -> RuntimeError.
    live=True WITH the env flag -> still NotImplementedError: the real HTTP
    order client is deliberately not wired; wiring it is a human go-live step.
    """
    if not live:
        return mock if mock is not None else MockKalshiExchange()
    if not _live_flag_set():
        raise RuntimeError(
            "live path refused: env flag %s is not set (it does not exist in "
            "this repo by design). No real order was sent." % LIVE_FLAG_ENV)
    raise NotImplementedError(
        "live path refused: both gates passed but the real Kalshi order "
        "client is intentionally not wired (human go-live step; see "
        "pm_trading/venues/live_stubs.py discipline). No real order was sent.")


def executor_governor() -> KalshiRateGovernor:
    """Dedicated governor share for the (unreachable) live path: rate_share
    1/BASE_RPS -> 1 req/s politeness, coordinated with the shared 429 wall."""
    return KalshiRateGovernor(caller="executor", rate_share=1.0 / BASE_RPS)


class OrderExecutor:
    """Drives one ExecOrder through the full lifecycle against an exchange
    that speaks the MockKalshiExchange API (submit/status/cancel/settlement).
    Every exchange call is governor-routed (governor=None -> no-op, the
    dry-run/mock case: no network to pace). Injected clock/sleep keep tests
    instant and deterministic."""

    def __init__(self, exchange: Any, *, governor: Any = None,
                 max_submit_retries: int = 3, max_cancel_retries: int = 3,
                 backoff_s: float = 0.5,
                 sleep_fn: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.time) -> None:
        self.exchange = exchange
        self.governor = governor
        self.max_submit_retries = int(max_submit_retries)   # hard cap
        self.max_cancel_retries = int(max_cancel_retries)   # hard cap
        self.backoff_s = float(backoff_s)
        self.sleep_fn = sleep_fn
        self.clock = clock

    def _t(self, order: ExecOrder, s: OrderState) -> None:
        transition(order, s, clock=self.clock)

    def _call(self, fn: Callable[[], Dict[str, Any]], sport: str,
              max_retries: int) -> Optional[Dict[str, Any]]:
        """Governor-routed call with bounded 429 retry. None = cap exhausted."""
        for attempt in range(max_retries + 1):
            before_request(self.governor, sport)
            resp = fn()
            if resp.get("status") != "429":
                return resp
            report_429(self.governor)
            if attempt < max_retries:
                self.sleep_fn(self.backoff_s * (2 ** attempt))
        return None

    def _sync_fill_state(self, order: ExecOrder) -> None:
        st = self.exchange.status(order.order_id) or {}
        order.filled_qty = int(st.get("filled", order.filled_qty))
        order.avg_fill_price_cents = float(st.get("avg", order.avg_fill_price_cents))
        if st.get("state") == "filled" and order.state != OrderState.FILLED:
            self._t(order, OrderState.FILLED)
        elif st.get("state") == "partial" and order.state in (OrderState.ACKED,
                                                              OrderState.PARTIAL):
            self._t(order, OrderState.PARTIAL)

    def submit(self, order: ExecOrder) -> ExecOrder:
        """NEW -> SUBMITTED -> ACKED (-> PARTIAL/FILLED if it crossed)."""
        if not order.idempotency_key:
            order.idempotency_key = idem_key(order.ticker, order.side,
                                             order.price_cents, "")
        resp = self._call(lambda: self.exchange.submit(
            order.ticker, order.side, order.qty, order.price_cents,
            idempotency_key=order.idempotency_key),
            order.sport, self.max_submit_retries)
        if resp is None:
            order.reason = "submit retry cap (%d) exhausted on 429" % self.max_submit_retries
            self._t(order, OrderState.REJECTED)
            return order
        self._t(order, OrderState.SUBMITTED)
        if resp.get("status") == "rejected":
            order.reason = str(resp.get("reason", "rejected"))
            self._t(order, OrderState.REJECTED)
            return order
        order.order_id = resp.get("order_id", "")
        self._t(order, OrderState.ACKED)
        self._sync_fill_state(order)
        return order

    def cancel(self, order: ExecOrder) -> ExecOrder:
        """ACKED/PARTIAL -> CANCEL_PENDING -> CANCELLED (or FILLED on the
        cancel-after-fill race; EXPIRED if cancel retries exhaust)."""
        self._t(order, OrderState.CANCEL_PENDING)
        resp = self._call(lambda: self.exchange.cancel(order.order_id),
                          order.sport, self.max_cancel_retries)
        if resp is None:
            order.reason = "cancel retry cap (%d) exhausted on 429" % self.max_cancel_retries
            self._t(order, OrderState.EXPIRED)
            return order
        if resp.get("status") == "already_filled":
            self._sync_fill_state(order)          # race: fill beat the cancel
            if order.state != OrderState.FILLED:
                self._t(order, OrderState.FILLED)
            return order
        self._sync_fill_state_quiet(order)
        self._t(order, OrderState.CANCELLED)
        return order

    def _sync_fill_state_quiet(self, order: ExecOrder) -> None:
        st = self.exchange.status(order.order_id) or {}
        order.filled_qty = int(st.get("filled", order.filled_qty))
        order.avg_fill_price_cents = float(st.get("avg", order.avg_fill_price_cents))

    def refresh(self, order: ExecOrder) -> ExecOrder:
        """Synchronize one resting mock order after a captured paper tick."""
        self._sync_fill_state(order)
        return order

    def execute(self, order: ExecOrder, *, timeout_s: float = 0.0,
                poll_interval_s: float = 1.0) -> ExecOrder:
        """Full pass: submit, poll until filled or deadline, cancel remainder.
        timeout_s=0 is immediate-or-cancel (the dry-run default)."""
        self.submit(order)
        if order.state in (OrderState.REJECTED, OrderState.FILLED):
            return order
        deadline = self.clock() + max(0.0, timeout_s)
        while order.state in (OrderState.ACKED, OrderState.PARTIAL):
            if self.clock() >= deadline:
                return self.cancel(order)
            self.sleep_fn(poll_interval_s)
            self._sync_fill_state(order)
        return order

    def replace(self, order: ExecOrder, new_price_cents: int) -> Tuple[ExecOrder, ExecOrder]:
        """Cancel/replace: cancel the working order, resubmit the unfilled
        remainder at the new price under a derived idempotency key."""
        self.cancel(order)
        remainder = order.qty - order.filled_qty
        new = ExecOrder(ticker=order.ticker, side=order.side,
                        qty=max(remainder, 0) or order.qty,
                        price_cents=int(new_price_cents), sport=order.sport,
                        idempotency_key=order.idempotency_key + ":r",
                        replaces=order.idempotency_key)
        if order.state == OrderState.FILLED or remainder <= 0:
            new.reason = "replace skipped: original fully filled before cancel"
            return order, new
        return order, self.submit(new)

    def settle(self, order: ExecOrder) -> ExecOrder:
        """FILLED/CANCELLED(with or without fills) -> SETTLED once the market
        resolved; settlement_cents is per-contract (100/0)."""
        val = self.exchange.settlement_value(order.order_id)
        if val is None:
            return order
        order.settlement_cents = int(val)
        self._t(order, OrderState.SETTLED)
        return order


__all__ = ["OrderState", "ALLOWED", "InvalidTransition", "ExecOrder",
           "transition", "idem_key", "resolve_exchange", "executor_governor",
           "OrderExecutor", "LIVE_FLAG_ENV"]
