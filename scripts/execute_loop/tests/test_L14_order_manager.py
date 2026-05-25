"""test_L14_order_manager.py — Tests for L14_order_manager.py

Seven tests covering the complete public API. All exchange clients are
injected via sys.modules mocking; no real HTTP calls are made. Each test
uses tmp_path to isolate file I/O via monkeypatching the module-level path
constants.
"""
from __future__ import annotations

import json
import sys
import time
import types
from pathlib import Path
from dataclasses import dataclass
from typing import List
from unittest.mock import MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
if str(_LOOP_DIR) not in sys.path:
    sys.path.insert(0, str(_LOOP_DIR))

import L14_order_manager as L14


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """Redirect all file I/O to tmp_path and reset in-memory state."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    orders_file = ledger_dir / "open_orders.json"

    monkeypatch.setattr(L14, "_LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(L14, "_ORDERS_FILE", orders_file)

    # Reset module-level in-memory state
    L14._reset_state()

    yield

    # Cleanup sys.modules injection between tests
    for mod in ["L09_kalshi_client", "L10_polymarket_client",
                "L11_sporttrade_client", "L07_pnl_ledger", "L22_alerting"]:
        sys.modules.pop(mod, None)


def _make_kalshi_mock(positions: list = None):
    """Build a mock Kalshi client module."""
    mock_mod = types.ModuleType("L09_kalshi_client")
    mock_mod.get_positions = MagicMock(return_value=positions or [])
    mock_mod.cancel_order = MagicMock(return_value=True)
    mock_mod.post_order = MagicMock(return_value={"order_id": "new_id", "status": "resting"})
    return mock_mod


@dataclass
class _FakePosition:
    market_ticker: str
    side: str
    qty: int


# ===========================================================================
# Test 1 — track_order persists and get_open_orders returns it
# ===========================================================================

def test_track_order_persists(tmp_path):
    """track_order creates OrderState, writes JSON, get_open_orders returns it."""
    order = L14.track_order("o1", "kalshi", "NBA-TEST", "yes", 10, 55, 0.6)

    assert order.order_id == "o1"
    assert order.exchange == "kalshi"
    assert order.market_id == "NBA-TEST"
    assert order.side == "yes"
    assert order.qty == 10
    assert order.qty_filled == 0
    assert order.price == 55
    assert order.status == "OPEN"
    assert order.model_p == 0.6
    assert order.current_model_p == 0.6
    assert order.placed_at > 0.0

    # Confirm JSON was written
    assert L14._ORDERS_FILE.exists()
    raw = json.loads(L14._ORDERS_FILE.read_text())
    assert len(raw) == 1
    assert raw[0]["order_id"] == "o1"

    # get_open_orders reads from in-memory (which was updated)
    orders = L14.get_open_orders()
    assert len(orders) == 1
    assert orders[0].order_id == "o1"


# ===========================================================================
# Test 2 — update_from_exchange_fills detects fill, calls L07.place_bet once
# ===========================================================================

def test_update_fills_triggers_l07(monkeypatch):
    """Mocked Kalshi returning qty=10 fills a qty=10 order; L07.place_bet called once."""
    # Track an order first
    L14.track_order("o2", "kalshi", "NBA-FILL", "yes", 10, 60, 0.65)

    # Build mocked position indicating fully filled
    filled_pos = _FakePosition(market_ticker="NBA-FILL", side="yes", qty=10)
    kalshi_mock = _make_kalshi_mock(positions=[filled_pos])
    sys.modules["L09_kalshi_client"] = kalshi_mock

    # Mock L07
    l07_mock = types.ModuleType("L07_pnl_ledger")

    @dataclass
    class FakeBetRow:
        bet_id: str = ""
        book: str = ""
        market: str = ""
        side: str = ""
        stake: float = 0.0
        odds: int = 0
        model_p_side: float = 0.0

    l07_mock.BetRow = FakeBetRow
    l07_mock.place_bet = MagicMock(return_value="o2")
    sys.modules["L07_pnl_ledger"] = l07_mock

    # Mock L22
    l22_mock = types.ModuleType("L22_alerting")
    l22_mock.send_fill_alert = MagicMock(return_value=True)
    sys.modules["L22_alerting"] = l22_mock

    n = L14.update_from_exchange_fills()

    assert n == 1
    l07_mock.place_bet.assert_called_once()
    l22_mock.send_fill_alert.assert_called_once()

    # Order should be removed from open_orders (fully filled)
    assert len(L14.get_open_orders()) == 0


# ===========================================================================
# Test 3 — check_for_reprice: boundary at 0.05 drift
# ===========================================================================

def test_check_for_reprice_boundary():
    """Drift >0.05 → in reprice list; drift <=0.05 → not in list.

    Note: float arithmetic means 0.55 - 0.50 = 0.05000...004 (> 0.05), so
    the exact-boundary test uses values that stay strictly under 0.05.
    """
    # model_p=0.5, new=0.56  → drift=0.06  → reprice
    L14.track_order("o3a", "kalshi", "MKT-A", "yes", 5, 50, 0.5)
    # model_p=0.5, new=0.545 → drift=0.045 → no reprice
    L14.track_order("o3b", "kalshi", "MKT-B", "yes", 5, 50, 0.5)
    # model_p=0.5, new=0.549 → drift=0.049 → no reprice (strictly < 0.05)
    L14.track_order("o3c", "kalshi", "MKT-C", "yes", 5, 50, 0.5)

    model_predictions = {
        "MKT-A": 0.56,    # drift = 0.06  → reprice
        "MKT-B": 0.545,   # drift = 0.045 → no reprice
        "MKT-C": 0.549,   # drift = 0.049 → no reprice (< 0.05)
    }

    reprice_list = L14.check_for_reprice(model_predictions)

    reprice_ids = {o.order_id for o in reprice_list}
    assert "o3a" in reprice_ids, "drift=0.06 must trigger reprice"
    assert "o3b" not in reprice_ids, "drift=0.045 must NOT trigger reprice"
    assert "o3c" not in reprice_ids, "drift=0.049 must NOT trigger reprice"


# ===========================================================================
# Test 4 — cancel_stale: old order → exchange.cancel_order called, removed
# ===========================================================================

def test_cancel_stale_removes_old_order(monkeypatch):
    """Order with placed_at 2000s ago is cancelled and removed from open_orders."""
    # Track order then manually age it
    L14.track_order("o4", "kalshi", "NBA-STALE", "yes", 5, 55, 0.6)

    # Age the order by patching placed_at
    order = L14._open_orders[0]
    order.placed_at = time.time() - 2000

    kalshi_mock = _make_kalshi_mock()
    sys.modules["L09_kalshi_client"] = kalshi_mock

    n = L14.cancel_stale(max_age_seconds=1800)

    assert n == 1
    kalshi_mock.cancel_order.assert_called_once_with("o4")
    assert len(L14.get_open_orders()) == 0

    # Verify disk state also cleared
    raw = json.loads(L14._ORDERS_FILE.read_text())
    assert len(raw) == 0


# ===========================================================================
# Test 5 — reprice_order: cancels old, tracks new with new_price
# ===========================================================================

def test_reprice_order_cancels_and_repost(monkeypatch):
    """reprice_order cancels existing order and creates new tracked order."""
    L14.track_order("o5", "kalshi", "NBA-REPRICE", "yes", 10, 55, 0.6)
    order = L14._open_orders[0]

    kalshi_mock = _make_kalshi_mock()
    sys.modules["L09_kalshi_client"] = kalshi_mock

    result = L14.reprice_order(order, new_price=65)

    assert result is True
    kalshi_mock.cancel_order.assert_called_once_with("o5")
    kalshi_mock.post_order.assert_called_once()
    post_kwargs = kalshi_mock.post_order.call_args
    # Check new price was passed
    called_price = (
        post_kwargs.kwargs.get("price")
        or (post_kwargs.args[3] if len(post_kwargs.args) > 3 else None)
    )
    assert called_price == 65

    # Old order gone, new one present
    orders = L14.get_open_orders()
    assert len(orders) == 1
    new_order = orders[0]
    assert new_order.price == 65
    assert new_order.order_id != "o5"
    assert "repriced_o5" in new_order.order_id


# ===========================================================================
# Test 6 — Idempotent fill: same fill seen twice → L07.place_bet called once
# ===========================================================================

def test_idempotent_fill_no_double_credit(monkeypatch):
    """Calling update_from_exchange_fills twice with same fill emits L07 event once."""
    L14.track_order("o6", "kalshi", "NBA-IDEM", "yes", 10, 60, 0.5)

    filled_pos = _FakePosition(market_ticker="NBA-IDEM", side="yes", qty=10)
    kalshi_mock = _make_kalshi_mock(positions=[filled_pos])
    sys.modules["L09_kalshi_client"] = kalshi_mock

    l07_mock = types.ModuleType("L07_pnl_ledger")

    @dataclass
    class FakeBetRow2:
        bet_id: str = ""
        book: str = ""
        market: str = ""
        side: str = ""
        stake: float = 0.0
        odds: int = 0
        model_p_side: float = 0.0

    l07_mock.BetRow = FakeBetRow2
    l07_mock.place_bet = MagicMock(return_value="o6")
    sys.modules["L07_pnl_ledger"] = l07_mock

    l22_mock = types.ModuleType("L22_alerting")
    l22_mock.send_fill_alert = MagicMock(return_value=True)
    sys.modules["L22_alerting"] = l22_mock

    # First update — fills order
    n1 = L14.update_from_exchange_fills()
    assert n1 == 1
    assert l07_mock.place_bet.call_count == 1

    # Second update — order is no longer in open_orders (removed after FILLED)
    # Re-inject the filled position; update should not process it again
    kalshi_mock.get_positions = MagicMock(return_value=[filled_pos])
    n2 = L14.update_from_exchange_fills()
    # No open orders remain, so 0 additional updates
    assert n2 == 0
    assert l07_mock.place_bet.call_count == 1  # still exactly once


# ===========================================================================
# Test 7 — track_order with unknown exchange raises ValueError
# ===========================================================================

def test_track_order_unknown_exchange_raises():
    """Passing an unrecognised exchange string raises ValueError."""
    with pytest.raises(ValueError, match="Unknown exchange"):
        L14.track_order("o7", "betfair", "MKT-X", "yes", 5, 50, 0.5)


# ===========================================================================
# Bonus test — qty=0 raises ValueError
# ===========================================================================

def test_track_order_zero_qty_raises():
    """qty=0 should raise ValueError."""
    with pytest.raises(ValueError, match="qty must be"):
        L14.track_order("o8", "kalshi", "MKT-X", "yes", 0, 55, 0.5)
