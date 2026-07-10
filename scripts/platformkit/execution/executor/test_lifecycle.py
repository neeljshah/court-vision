"""Per-file tests: order lifecycle state machine, retries/idempotency, and the
double-gated (unreachable) live path.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_lifecycle.py -q
"""
from __future__ import annotations

import os

import pytest

from scripts.platformkit.execution.executor.lifecycle import (
    ALLOWED, ExecOrder, InvalidTransition, LIVE_FLAG_ENV, OrderExecutor,
    OrderState, idem_key, resolve_exchange, transition)
from scripts.platformkit.execution.executor.mock_exchange import MockKalshiExchange

SNAP = {"ticker": "KXTEST-A", "best_bid": 0.40, "best_ask": 0.45,
        "book_thinness": 100.0, "ts": "2026-07-09T00:00:00Z"}
THIN = {"ticker": "KXTEST-THIN", "best_bid": 0.40, "best_ask": 0.45,
        "book_thinness": 3.0, "ts": "2026-07-09T00:00:00Z"}


def _executor(exchange, **kw):
    kw.setdefault("sleep_fn", lambda _s: None)
    return OrderExecutor(exchange, governor=None, **kw)


def _order(ticker="KXTEST-A", side="yes", qty=5, price=50):
    return ExecOrder(ticker=ticker, side=side, qty=qty, price_cents=price,
                     idempotency_key=idem_key(ticker, side, price, "t"))


# -- state machine: every legal transition, and illegal ones raise ----------

def test_every_legal_transition_applies():
    n = 0
    for src, dsts in ALLOWED.items():
        for dst in dsts:
            o = _order()
            o.state = src
            transition(o, dst, clock=lambda: 1.0)
            assert o.state == dst and o.history == [(1.0, dst.value)]
            n += 1
    assert n == sum(len(d) for d in ALLOWED.values()) and n >= 15


def test_illegal_transitions_raise():
    for src, dst in [(OrderState.NEW, OrderState.FILLED),
                     (OrderState.FILLED, OrderState.CANCELLED),
                     (OrderState.SETTLED, OrderState.NEW),
                     (OrderState.REJECTED, OrderState.SUBMITTED),
                     (OrderState.CANCELLED, OrderState.PARTIAL)]:
        o = _order()
        o.state = src
        with pytest.raises(InvalidTransition):
            transition(o, dst)


def test_terminal_states_have_no_exits_except_settlement():
    assert ALLOWED[OrderState.REJECTED] == frozenset()
    assert ALLOWED[OrderState.EXPIRED] == frozenset()
    assert ALLOWED[OrderState.SETTLED] == frozenset()
    assert ALLOWED[OrderState.FILLED] == {OrderState.SETTLED}
    assert ALLOWED[OrderState.CANCELLED] == {OrderState.SETTLED}


# -- submit -> ack -> fill / partial / cancel / replace / settle ------------

def test_submit_crossing_order_fills_and_settles():
    ex = MockKalshiExchange([SNAP])
    o = _executor(ex).execute(_order(price=50), timeout_s=0.0)
    assert o.state is OrderState.FILLED
    assert o.filled_qty == 5 and o.avg_fill_price_cents == 45.0  # fills AT the ask
    assert [s for _t, s in o.history] == ["SUBMITTED", "ACKED", "FILLED"]
    ex.settle_market("KXTEST-A", yes_result=True)
    _executor(ex).settle(o)
    assert o.state is OrderState.SETTLED and o.settlement_cents == 100


def test_partial_fill_then_timeout_cancel():
    ex = MockKalshiExchange([THIN])
    o = _executor(ex).execute(_order(ticker="KXTEST-THIN", qty=10, price=50),
                              timeout_s=0.0)
    assert o.state is OrderState.CANCELLED and o.filled_qty == 3
    assert "PARTIAL" in [s for _t, s in o.history]
    assert "CANCEL_PENDING" in [s for _t, s in o.history]


def test_noncrossing_order_rests_then_cancels_on_timeout():
    ex = MockKalshiExchange([SNAP])
    o = _executor(ex).execute(_order(price=30), timeout_s=0.0)  # below the 45 ask
    assert o.state is OrderState.CANCELLED and o.filled_qty == 0


def test_unknown_ticker_rejected():
    o = _executor(MockKalshiExchange([SNAP])).submit(_order(ticker="KXNOPE"))
    assert o.state is OrderState.REJECTED and "unknown ticker" in o.reason


def test_cancel_after_fill_race_ends_filled():
    ex = MockKalshiExchange([SNAP], race_fill_on_cancel=["KXTEST-A"])
    o = _executor(ex).execute(_order(price=30), timeout_s=0.0)  # rests, then cancel races
    assert o.state is OrderState.FILLED and o.filled_qty == 5


def test_replace_moves_remainder_to_new_price():
    ex = MockKalshiExchange([THIN])
    execu = _executor(ex)
    old = execu.submit(_order(ticker="KXTEST-THIN", qty=10, price=50))
    assert old.state is OrderState.PARTIAL and old.filled_qty == 3
    old, new = execu.replace(old, new_price_cents=60)
    assert old.state is OrderState.CANCELLED
    assert new.qty == 7 and new.price_cents == 60
    assert new.replaces == old.idempotency_key
    assert new.idempotency_key != old.idempotency_key


# -- retries, hard caps, idempotency, governor routing ----------------------

def test_429_submit_retries_then_succeeds_with_same_idem_key():
    ex = MockKalshiExchange([SNAP], submit_429s=2)
    o = _executor(ex).execute(_order(price=50), timeout_s=0.0)
    assert o.state is OrderState.FILLED  # retried past the two 429s
    assert len(ex._idem) == 1            # one idempotency key, no double-submit


def test_429_submit_hard_cap_rejects():
    ex = MockKalshiExchange([SNAP], submit_429s=99)
    o = _executor(ex, max_submit_retries=3).submit(_order(price=50))
    assert o.state is OrderState.REJECTED and "retry cap" in o.reason


def test_429_cancel_hard_cap_expires():
    ex = MockKalshiExchange([SNAP], cancel_429s=99)
    o = _executor(ex, max_cancel_retries=2).execute(_order(price=30), timeout_s=0.0)
    assert o.state is OrderState.EXPIRED and "retry cap" in o.reason


def test_idempotent_resubmit_returns_same_order():
    ex = MockKalshiExchange([SNAP])
    r1 = ex.submit("KXTEST-A", "yes", 5, 50, idempotency_key="k1")
    r2 = ex.submit("KXTEST-A", "yes", 5, 50, idempotency_key="k1")
    assert r1["order_id"] == r2["order_id"] and r2.get("duplicate") is True
    assert len(ex._orders) == 1


def test_429s_are_reported_to_governor():
    calls = []

    class StubGov:
        def acquire(self, sport, **kw):
            calls.append(("acquire", sport))
            return True

        def on_429(self):
            calls.append(("429", None))

    ex = MockKalshiExchange([SNAP], submit_429s=1)
    OrderExecutor(ex, governor=StubGov(), sleep_fn=lambda _s: None
                  ).execute(_order(price=50), timeout_s=0.0)
    assert ("429", None) in calls and ("acquire", "unknown") in calls


# -- THE DOUBLE GATE: real-order path is unreachable -------------------------

def test_gate_default_is_mock():
    assert isinstance(resolve_exchange(live=False), MockKalshiExchange)


def test_gate_live_arg_alone_raises_config_absent():
    assert LIVE_FLAG_ENV not in os.environ  # the enabling config does not exist
    with pytest.raises(RuntimeError, match="not set"):
        resolve_exchange(live=True)


def test_gate_even_both_gates_hard_refuse(monkeypatch):
    # Even if a (nonexistent-in-repo) env flag were set AND --live passed,
    # the live client is not wired: NotImplementedError, no order path.
    monkeypatch.setenv(LIVE_FLAG_ENV, "1")
    with pytest.raises(NotImplementedError, match="not wired"):
        resolve_exchange(live=True)


def test_gate_env_flag_alone_without_live_arg_stays_mock(monkeypatch):
    monkeypatch.setenv(LIVE_FLAG_ENV, "1")
    assert isinstance(resolve_exchange(live=False), MockKalshiExchange)
