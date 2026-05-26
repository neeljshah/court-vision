"""test_L11_sporttrade.py — Tests for L11_sporttrade_client.py (paper mode only).

All 8 required tests + 2 atomic-write hardening tests.
No HTTP calls; seed dirs and ledger redirected to tmp_path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Path setup — import L11 directly
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
sys.path.insert(0, str(_LOOP_DIR))

import L11_sporttrade_client as L11

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def paper_mode(monkeypatch):
    """Ensure paper mode for every test by clearing live env vars."""
    monkeypatch.delenv("SPORTTRADE_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("SPORTTRADE_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    """Wipe the in-process idempotency cache before each test."""
    L11._IDEMPOTENCY_CACHE.clear()
    yield
    L11._IDEMPOTENCY_CACHE.clear()


@pytest.fixture()
def seed_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect L11 seed dir to a fresh tmp_path subdir and populate with test data."""
    sdir = tmp_path / "exchange_seed" / "sporttrade"
    sdir.mkdir(parents=True)

    # events_2026-05-25.json
    events_file = sdir / "events_2026-05-25.json"
    events_file.write_text(
        json.dumps([{"event_id": "evt_1", "home": "LAL", "away": "DEN",
                     "tipoff": "2026-05-25T20:00Z"}]),
        encoding="utf-8",
    )

    # mkt_test.json
    mkt_file = sdir / "mkt_test.json"
    mkt_file.write_text(
        json.dumps({
            "market_id": "mkt_test",
            "market_type": "ml",
            "bids": [[55, 100], [54, 200]],
            "asks": [[56, 100], [57, 200]],
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(L11, "_SEED_DIR", sdir)
    return sdir


@pytest.fixture()
def ledger_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect L11 ledger dir to a fresh tmp_path subdir."""
    ldir = tmp_path / "ledger"
    ldir.mkdir(parents=True)
    monkeypatch.setattr(L11, "_LEDGER_DIR", ldir)
    return ldir


# ---------------------------------------------------------------------------
# Test 1: find_nba_events reads seed file and returns list with event_id
# ---------------------------------------------------------------------------

def test_find_nba_events_paper_returns_list(seed_dir, ledger_dir):
    events = L11.find_nba_events("2026-05-25")
    assert isinstance(events, list)
    assert len(events) >= 1
    assert events[0]["event_id"] == "evt_1"
    assert events[0]["home"] == "LAL"


# ---------------------------------------------------------------------------
# Test 2: get_orderbook returns dict with bids and asks
# ---------------------------------------------------------------------------

def test_get_orderbook_returns_bids_asks(seed_dir, ledger_dir):
    book = L11.get_orderbook("mkt_test")
    assert isinstance(book, dict)
    assert "bids" in book
    assert "asks" in book
    assert book["bids"][0][0] == 55
    assert book["asks"][0][0] == 56


# ---------------------------------------------------------------------------
# Test 3: post_order paper returns paper-st-<id>, ledger appended
# ---------------------------------------------------------------------------

def test_post_order_paper_returns_order_id_and_ledger_written(seed_dir, ledger_dir):
    result = L11.post_order("mkt_test", "back", 10, 55.0)
    assert "order_id" in result
    assert result["order_id"].startswith("paper-st-")
    assert result["status"] == "filled"

    # Ledger should contain exactly one record
    ledger_file = ledger_dir / "paper_sporttrade_orders.json"
    assert ledger_file.exists()
    orders = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(orders) == 1
    assert orders[0]["market_id"] == "mkt_test"
    assert orders[0]["side"] == "back"
    assert orders[0]["qty"] == 10
    assert orders[0]["price"] == 55.0


# ---------------------------------------------------------------------------
# Test 4: Same idempotency_key twice → second returns cached, ledger NOT doubled
# ---------------------------------------------------------------------------

def test_idempotency_key_no_double_write(seed_dir, ledger_dir):
    ikey = "idem-abc-123"
    r1 = L11.post_order("mkt_test", "back", 5, 55.0, idempotency_key=ikey)
    r2 = L11.post_order("mkt_test", "back", 5, 55.0, idempotency_key=ikey)

    # Same result object returned
    assert r1["order_id"] == r2["order_id"]

    # Ledger has exactly ONE record (not two)
    ledger_file = ledger_dir / "paper_sporttrade_orders.json"
    orders = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(orders) == 1


# ---------------------------------------------------------------------------
# Test 5: post_order(price=100) → ValueError
# ---------------------------------------------------------------------------

def test_post_order_price_100_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="price must be in"):
        L11.post_order("mkt_test", "back", 5, 100.0)


# ---------------------------------------------------------------------------
# Test 6: post_order(price=0) → ValueError
# ---------------------------------------------------------------------------

def test_post_order_price_0_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="price must be in"):
        L11.post_order("mkt_test", "back", 5, 0.0)


# ---------------------------------------------------------------------------
# Test 7: SPORTTRADE_LIVE_ENABLED=1 without API_KEY → PermissionError
# ---------------------------------------------------------------------------

def test_live_enabled_without_api_key_raises(monkeypatch, seed_dir, ledger_dir):
    monkeypatch.setenv("SPORTTRADE_LIVE_ENABLED", "1")
    monkeypatch.delenv("SPORTTRADE_API_KEY", raising=False)

    with pytest.raises(PermissionError, match="SPORTTRADE_API_KEY"):
        L11.find_nba_events("2026-05-25")

    with pytest.raises(PermissionError):
        L11.get_orderbook("mkt_test")

    with pytest.raises(PermissionError):
        L11.post_order("mkt_test", "back", 5, 55.0)


# ---------------------------------------------------------------------------
# Test 8: get_positions aggregates — 2 orders same (market_id, side) →
#          one position, weighted avg price, summed qty
# ---------------------------------------------------------------------------

def test_get_positions_aggregates_two_orders(seed_dir, ledger_dir):
    # Order 1: qty=10 @ 55.0
    L11.post_order("mkt_test", "back", 10, 55.0)
    # Order 2: qty=20 @ 58.0
    L11.post_order("mkt_test", "back", 20, 58.0)

    positions = L11.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 1

    pos = positions[0]
    assert pos.market_id == "mkt_test"
    assert pos.side == "back"
    assert pos.qty == 30  # 10 + 20

    # Weighted avg: (10*55 + 20*58) / 30 = (550 + 1160) / 30 = 1710 / 30 = 57.0
    assert abs(pos.avg_price - 57.0) < 1e-6

    # unrealized_pnl: mid = (55+56)/2 = 55.5; pnl = (55.5 - 57.0) * 30 = -45.0
    assert isinstance(pos.unrealized_pnl, float)


# ---------------------------------------------------------------------------
# Bonus: get_orderbook missing market → KeyError
# ---------------------------------------------------------------------------

def test_get_orderbook_missing_market_raises_key_error(seed_dir, ledger_dir):
    with pytest.raises(KeyError):
        L11.get_orderbook("nonexistent_market")


# ---------------------------------------------------------------------------
# Bonus: post_order qty <= 0 → ValueError
# ---------------------------------------------------------------------------

def test_post_order_zero_qty_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="qty must be > 0"):
        L11.post_order("mkt_test", "back", 0, 55.0)


# ---------------------------------------------------------------------------
# Atomic-write Test 1: _atomic_write_json replaces an existing file correctly
# ---------------------------------------------------------------------------

def test_atomic_write_replaces_existing_file(tmp_path):
    target = tmp_path / "orders.json"
    # Write initial content
    target.write_text(json.dumps([{"old": True}]), encoding="utf-8")

    new_payload = [{"order_id": "paper-st-abc", "status": "filled"}]
    L11._atomic_write_json(target, new_payload)

    assert target.exists()
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result == new_payload
    # No .tmp files left behind
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


# ---------------------------------------------------------------------------
# Atomic-write Test 2: on os.replace failure, original file is unchanged
#                       and .tmp file is cleaned up
# ---------------------------------------------------------------------------

def test_atomic_write_no_partial_on_failure(tmp_path):
    target = tmp_path / "orders.json"
    original_payload = [{"order_id": "paper-st-original"}]
    target.write_text(json.dumps(original_payload), encoding="utf-8")

    new_payload = [{"order_id": "paper-st-new"}]

    with patch("L11_sporttrade_client.os.replace", side_effect=OSError("simulated failure")):
        with pytest.raises(OSError, match="simulated failure"):
            L11._atomic_write_json(target, new_payload)

    # Original file must be intact
    assert target.exists()
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result == original_payload

    # No orphaned .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []
