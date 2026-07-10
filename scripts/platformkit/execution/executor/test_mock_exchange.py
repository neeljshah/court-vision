"""Per-file tests: MockKalshiExchange deterministic fills from captured
book_depth snapshots (depth-capped), partial fills, book advance, settlement.
Run: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/executor/test_mock_exchange.py -q
"""
from __future__ import annotations

from scripts.platformkit.execution.executor.mock_exchange import (
    MockKalshiExchange, validate_order)

SNAP = {"ticker": "KXM-A", "best_bid": 0.55, "best_ask": 0.62,
        "book_thinness": 50.0, "ts": "2026-07-09T00:00:00Z"}


def test_validate_order_rules():
    assert validate_order("yes", 1, 50) is None
    assert validate_order("maybe", 1, 50) is not None
    assert validate_order("yes", 0, 50) is not None
    assert validate_order("yes", 1, 0) is not None
    assert validate_order("no", 1, 100) is not None


def test_yes_buy_fills_only_if_limit_crosses_ask():
    ex = MockKalshiExchange([SNAP])
    resting = ex.submit("KXM-A", "yes", 5, 61)   # 61 < ask 62 -> rests
    crossed = ex.submit("KXM-A", "yes", 5, 62)   # crosses -> fills AT 62
    assert ex.status(resting["order_id"])["state"] == "resting"
    st = ex.status(crossed["order_id"])
    assert st["state"] == "filled" and st["avg"] == 62.0 and st["filled"] == 5


def test_no_buy_consumes_yes_bid_liquidity():
    ex = MockKalshiExchange([SNAP])
    # NO at 45 crosses (100 - bid 55 = 45); NO at 44 does not.
    rest = ex.submit("KXM-A", "no", 5, 44)
    fill = ex.submit("KXM-A", "no", 5, 45)
    assert ex.status(rest["order_id"])["state"] == "resting"
    st = ex.status(fill["order_id"])
    assert st["state"] == "filled" and st["avg"] == 45.0


def test_partial_fill_capped_by_captured_depth():
    ex = MockKalshiExchange([{**SNAP, "book_thinness": 7.0}])
    r = ex.submit("KXM-A", "yes", 10, 70)
    st = ex.status(r["order_id"])
    assert st["state"] == "partial" and st["filled"] == 7
    # Depth is depleted: a second crossing order finds no ask size left.
    r2 = ex.submit("KXM-A", "yes", 3, 70)
    assert ex.status(r2["order_id"])["state"] == "resting"


def test_advance_book_fills_resting_order():
    ex = MockKalshiExchange([SNAP])
    r = ex.submit("KXM-A", "yes", 4, 58)  # below ask 62 -> rests
    assert ex.status(r["order_id"])["state"] == "resting"
    ex.advance_book([{**SNAP, "best_ask": 0.57, "ts": "2026-07-09T00:01:00Z"}])
    st = ex.status(r["order_id"])
    assert st["state"] == "filled" and st["avg"] == 57.0


def test_cancel_states_and_unknown_order():
    ex = MockKalshiExchange([SNAP])
    r = ex.submit("KXM-A", "yes", 4, 58)
    assert ex.cancel(r["order_id"])["status"] == "cancelled"
    assert ex.cancel(r["order_id"])["status"] == "cancelled"  # idempotent
    assert ex.cancel("nope")["status"] == "unknown_order"
    filled = ex.submit("KXM-A", "yes", 2, 62)
    assert ex.cancel(filled["order_id"])["status"] == "already_filled"


def test_settlement_values():
    ex = MockKalshiExchange([SNAP])
    y = ex.submit("KXM-A", "yes", 2, 62)
    assert ex.settlement_value(y["order_id"]) is None  # not settled yet
    ex.settle_market("KXM-A", yes_result=False)
    assert ex.settlement_value(y["order_id"]) == 0
    ex.settle_market("KXM-A", yes_result=True)
    assert ex.settlement_value(y["order_id"]) == 100


def test_injected_429s_deplete():
    ex = MockKalshiExchange([SNAP], submit_429s=1, cancel_429s=1)
    assert ex.submit("KXM-A", "yes", 1, 62)["status"] == "429"
    ok = ex.submit("KXM-A", "yes", 1, 62)
    assert ok["status"] == "ack"
    r = ex.submit("KXM-A", "yes", 1, 50)
    assert ex.cancel(r["order_id"])["status"] == "429"
    assert ex.cancel(r["order_id"])["status"] == "cancelled"


def test_malformed_snapshot_rows_never_raise():
    ex = MockKalshiExchange([{"ticker": "KXM-B", "best_bid": None,
                              "best_ask": "bad", "book_thinness": "x", "ts": ""},
                             {"no_ticker": True}])
    r = ex.submit("KXM-B", "yes", 1, 50)  # unquoted book -> rests
    assert ex.status(r["order_id"])["state"] == "resting"
