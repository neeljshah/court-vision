"""test_L10_polymarket.py — Tests for L10_polymarket_client.py (paper mode only).

Six focused tests — no real HTTP calls; seed files are read from disk or
monkeypatched away.  Private-key env tests use monkeypatch to isolate env.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — import L10 directly
# ---------------------------------------------------------------------------

_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
sys.path.insert(0, str(_LOOP_DIR))

import L10_polymarket_client as L10

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_REPO = _LOOP_DIR.parent.parent  # scripts/execute_loop -> scripts -> repo root
_SEED_DIR = _REPO / "data" / "exchange_seed" / "polymarket"
_OB_DIR = _SEED_DIR / "orderbooks"


@pytest.fixture(autouse=True)
def _isolated_ledger(tmp_path, monkeypatch):
    """Point ledger file at a fresh tmp directory for every test."""
    tmp_ledger = tmp_path / "ledger"
    tmp_ledger.mkdir()
    monkeypatch.setattr(L10, "_LEDGER_DIR", tmp_ledger)
    monkeypatch.setattr(L10, "_LEDGER_FILE", tmp_ledger / "paper_polymarket_orders.json")
    yield


# ---------------------------------------------------------------------------
# Test 1 — find_nba_markets returns ≥1 PolyMarket from seed file
# ---------------------------------------------------------------------------


def test_find_nba_markets_returns_seed(monkeypatch):
    """Paper mode: reading the 2026-05-25 seed file returns at least one NBA market."""
    markets = L10.find_nba_markets("2026-05-25")
    assert len(markets) >= 1, "Expected ≥1 NBA market from seed file"
    m = markets[0]
    assert isinstance(m, L10.PolyMarket)
    assert m.condition_id == "test_cid_1"
    assert "lakers" in m.slug.lower() or "nba" in m.slug.lower()
    assert len(m.outcome_prices) >= 1
    assert m.volume_24h > 0


# ---------------------------------------------------------------------------
# Test 2 — get_orderbook returns a PolyOrderbook with sorted asks/bids
# ---------------------------------------------------------------------------


def test_get_orderbook_sorted():
    """Paper mode: orderbook for test_cid_1 loads from seed with sorted levels."""
    ob = L10.get_orderbook("test_cid_1")
    assert ob is not None, "Expected orderbook seed for test_cid_1"
    assert isinstance(ob, L10.PolyOrderbook)
    assert ob.condition_id == "test_cid_1"
    # Asks sorted ascending by price
    ask_prices = [a["price"] for a in ob.asks]
    assert ask_prices == sorted(ask_prices), "Asks must be sorted ascending"
    # Bids sorted descending by price
    bid_prices = [b["price"] for b in ob.bids]
    assert bid_prices == sorted(bid_prices, reverse=True), "Bids must be sorted descending"
    # Basic sanity on seed values
    assert ob.asks[0]["price"] == pytest.approx(0.55)
    assert ob.bids[0]["price"] == pytest.approx(0.54)


# ---------------------------------------------------------------------------
# Test 3 — post_order paper: returns poly_paper_<id>, ledger appended
# ---------------------------------------------------------------------------


def test_post_order_paper_appends_ledger():
    """Paper post_order returns a valid order_id and appends to ledger."""
    result = L10.post_order(
        condition_id="test_cid_1",
        outcome="yes",
        side="buy",
        qty=50.0,
        price_usdc=0.55,
    )
    assert result["status"] == "filled"
    order_id = result["order_id"]
    assert order_id.startswith("poly_paper_"), f"Unexpected order_id format: {order_id}"
    assert len(order_id) == len("poly_paper_") + 12  # hex[:12]

    # Verify ledger file was written
    ledger_file = L10._LEDGER_FILE
    assert ledger_file.exists(), "Ledger file not created"
    data = json.loads(ledger_file.read_text())
    assert len(data["orders"]) == 1
    rec = data["orders"][0]
    assert rec["order_id"] == order_id
    assert rec["condition_id"] == "test_cid_1"
    assert rec["outcome"] == "yes"
    assert rec["qty"] == 50.0
    assert rec["price_usdc"] == pytest.approx(0.55)
    assert rec["status"] == "filled"


# ---------------------------------------------------------------------------
# Test 4 — live mode without POLYMARKET_PRIVATE_KEY raises PermissionError
# ---------------------------------------------------------------------------


def test_live_without_private_key_raises(monkeypatch):
    """Requesting live mode without the private key env var must raise PermissionError."""
    monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_USDC_FUNDED", raising=False)

    with pytest.raises(PermissionError, match="POLYMARKET_PRIVATE_KEY"):
        L10.post_order(
            condition_id="test_cid_1",
            outcome="yes",
            side="buy",
            qty=10.0,
            price_usdc=0.55,
            live=True,
        )


# ---------------------------------------------------------------------------
# Test 5 — price_usdc >= 1.0 raises ValueError
# ---------------------------------------------------------------------------


def test_post_order_price_too_high_raises():
    """Price at or above 1.0 must raise ValueError."""
    with pytest.raises(ValueError, match="price must be in"):
        L10.post_order(
            condition_id="test_cid_1",
            outcome="yes",
            side="buy",
            qty=10.0,
            price_usdc=1.5,
        )


# ---------------------------------------------------------------------------
# Test 6 — price_usdc <= 0 raises ValueError
# ---------------------------------------------------------------------------


def test_post_order_price_negative_raises():
    """Negative or zero price must raise ValueError."""
    with pytest.raises(ValueError, match="price must be in"):
        L10.post_order(
            condition_id="test_cid_1",
            outcome="yes",
            side="buy",
            qty=10.0,
            price_usdc=-0.1,
        )


# ---------------------------------------------------------------------------
# Bonus test 7 — idempotency key deduplicates orders
# ---------------------------------------------------------------------------


def test_idempotency_deduplication():
    """Repeated post_order with same idempotency_key returns cached result."""
    ikey = "test-idem-key-abc"
    r1 = L10.post_order(
        condition_id="test_cid_1",
        outcome="no",
        side="buy",
        qty=25.0,
        price_usdc=0.45,
        idempotency_key=ikey,
    )
    r2 = L10.post_order(
        condition_id="test_cid_1",
        outcome="no",
        side="buy",
        qty=25.0,
        price_usdc=0.45,
        idempotency_key=ikey,
    )
    assert r1["order_id"] == r2["order_id"], "Idempotent calls must return same order_id"
    # Ledger should have exactly ONE entry
    data = json.loads(L10._LEDGER_FILE.read_text())
    assert len(data["orders"]) == 1


# ---------------------------------------------------------------------------
# Bonus test 8 — get_orderbook returns None for unknown condition_id
# ---------------------------------------------------------------------------


def test_get_orderbook_missing_returns_none():
    """get_orderbook for an unknown condition_id must return None (not raise)."""
    ob = L10.get_orderbook("nonexistent_cid_xyz")
    assert ob is None


# ---------------------------------------------------------------------------
# Bonus test 9 — qty <= 0 raises ValueError
# ---------------------------------------------------------------------------


def test_post_order_zero_qty_raises():
    """qty of 0 must raise ValueError."""
    with pytest.raises(ValueError):
        L10.post_order(
            condition_id="test_cid_1",
            outcome="yes",
            side="buy",
            qty=0.0,
            price_usdc=0.55,
        )


# ---------------------------------------------------------------------------
# Bonus test 10 — PRIVATE_KEY set but USDC_FUNDED != 'true' → PermissionError
# ---------------------------------------------------------------------------


def test_live_funded_not_confirmed_raises(monkeypatch):
    """Private key present but USDC_FUNDED not 'true' must raise PermissionError."""
    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "0xdeadbeef")
    monkeypatch.setenv("POLYMARKET_USDC_FUNDED", "false")

    with pytest.raises(PermissionError, match="not confirmed funded"):
        L10.post_order(
            condition_id="test_cid_1",
            outcome="yes",
            side="buy",
            qty=10.0,
            price_usdc=0.55,
            live=True,
        )
