"""Tests for scripts/execute_loop/L09_kalshi_client.py (paper mode only).

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L09_kalshi.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import types
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Project root on path + stub heavy imports before loading module
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub src.data.nba_api_headers_patch so module load doesn't fail if absent
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

import scripts.execute_loop.L09_kalshi_client as L09  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_seed(seed_dir: Path, ticker: str, data: dict | None = None) -> None:
    """Write a seed JSON file for the given ticker into seed_dir."""
    seed_dir.mkdir(parents=True, exist_ok=True)
    payload = data or {
        "market_ticker": ticker,
        "yes_bids": [[55, 100], [54, 200]],
        "yes_asks": [[56, 100], [57, 200]],
        "no_bids": [[44, 100], [43, 200]],
        "no_asks": [[45, 100], [46, 200]],
    }
    (seed_dir / f"{ticker}.json").write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def paper_env(monkeypatch):
    """Ensure paper mode for every test by clearing live-mode env vars."""
    monkeypatch.delenv("KALSHI_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)


@pytest.fixture()
def isolated_paths(tmp_path, monkeypatch):
    """Redirect seed dir and ledger dir to tmp_path for isolation."""
    seed_dir = tmp_path / "exchange_seed" / "kalshi"
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(L09, "_SEED_DIR", seed_dir)
    monkeypatch.setattr(L09, "_LEDGER_DIR", ledger_dir)
    monkeypatch.setattr(L09, "_PAPER_ORDERS_FILE", ledger_dir / "paper_kalshi_orders.json")

    return seed_dir, ledger_dir


# ---------------------------------------------------------------------------
# Test 1: get_orderbook reads seed JSON and returns dict with 4 keys
# ---------------------------------------------------------------------------

def test_get_orderbook_reads_seed(isolated_paths):
    seed_dir, _ = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")

    ob = L09.get_orderbook("NBA-TEST")

    assert isinstance(ob, dict)
    assert set(ob.keys()) == {"yes_bids", "yes_asks", "no_bids", "no_asks"}
    assert ob["yes_bids"] == [[55, 100], [54, 200]]
    assert ob["no_asks"] == [[45, 100], [46, 200]]


def test_get_orderbook_missing_ticker_raises(isolated_paths):
    """Missing seed file → KeyError with descriptive message."""
    seed_dir, _ = isolated_paths
    seed_dir.mkdir(parents=True, exist_ok=True)  # dir exists but no file

    with pytest.raises(KeyError, match="unknown market_ticker: GHOST-MARKET"):
        L09.get_orderbook("GHOST-MARKET")


# ---------------------------------------------------------------------------
# Test 2: post_order returns paper_kalshi_<uuid> and ledger grows by 1
# ---------------------------------------------------------------------------

def test_post_order_creates_ledger_entry(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")
    orders_file = ledger_dir / "paper_kalshi_orders.json"

    result = L09.post_order("NBA-TEST", "yes", 5, 60)

    assert result["status"] == "filled"
    assert result["order_id"].startswith("paper_kalshi_")
    assert len(result["order_id"]) == len("paper_kalshi_") + 12

    assert orders_file.exists()
    orders = json.loads(orders_file.read_text(encoding="utf-8"))
    assert len(orders) == 1
    assert orders[0]["market_ticker"] == "NBA-TEST"
    assert orders[0]["side"] == "yes"
    assert orders[0]["qty"] == 5
    assert orders[0]["price"] == 60


def test_post_order_increments_ledger(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")
    orders_file = ledger_dir / "paper_kalshi_orders.json"

    L09.post_order("NBA-TEST", "yes", 5, 60)
    L09.post_order("NBA-TEST", "no", 3, 44)

    orders = json.loads(orders_file.read_text(encoding="utf-8"))
    assert len(orders) == 2


# ---------------------------------------------------------------------------
# Test 3: idempotency key — same key twice → identical response, no new entry
# ---------------------------------------------------------------------------

def test_idempotency_same_key_no_duplicate(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")
    orders_file = ledger_dir / "paper_kalshi_orders.json"

    key = "idem-key-abc123"
    r1 = L09.post_order("NBA-TEST", "yes", 5, 60, idempotency_key=key)
    r2 = L09.post_order("NBA-TEST", "yes", 5, 60, idempotency_key=key)

    assert r1["order_id"] == r2["order_id"]
    assert r1["status"] == r2["status"]

    orders = json.loads(orders_file.read_text(encoding="utf-8"))
    assert len(orders) == 1  # ledger unchanged after second call


def test_idempotency_different_keys_two_entries(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")
    orders_file = ledger_dir / "paper_kalshi_orders.json"

    r1 = L09.post_order("NBA-TEST", "yes", 5, 60, idempotency_key="key-A")
    r2 = L09.post_order("NBA-TEST", "yes", 5, 60, idempotency_key="key-B")

    assert r1["order_id"] != r2["order_id"]
    orders = json.loads(orders_file.read_text(encoding="utf-8"))
    assert len(orders) == 2


# ---------------------------------------------------------------------------
# Test 4: post_order(price=100) → ValueError
# ---------------------------------------------------------------------------

def test_post_order_price_100_raises(isolated_paths):
    with pytest.raises(ValueError, match="price must be 1-99 cents"):
        L09.post_order("NBA-TEST", "yes", 5, 100)


def test_post_order_price_0_raises(isolated_paths):
    with pytest.raises(ValueError, match="price must be 1-99 cents"):
        L09.post_order("NBA-TEST", "yes", 5, 0)


def test_post_order_invalid_side_raises(isolated_paths):
    with pytest.raises(ValueError, match="side must be"):
        L09.post_order("NBA-TEST", "maybe", 5, 60)


def test_post_order_zero_qty_raises(isolated_paths):
    with pytest.raises(ValueError, match="qty must be"):
        L09.post_order("NBA-TEST", "yes", 0, 60)


def test_post_order_negative_qty_raises(isolated_paths):
    with pytest.raises(ValueError, match="qty must be"):
        L09.post_order("NBA-TEST", "yes", -1, 60)


# ---------------------------------------------------------------------------
# Test 5: LIVE mode without API key → PermissionError
# ---------------------------------------------------------------------------

def test_live_mode_without_key_raises(monkeypatch):
    monkeypatch.setenv("KALSHI_LIVE_ENABLED", "1")
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)

    with pytest.raises(PermissionError, match="KALSHI_API_KEY"):
        L09.get_orderbook("NBA-TEST")


def test_live_mode_without_key_raises_on_post(monkeypatch):
    monkeypatch.setenv("KALSHI_LIVE_ENABLED", "1")
    monkeypatch.delenv("KALSHI_API_KEY", raising=False)
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)

    with pytest.raises(PermissionError):
        L09.post_order("NBA-TEST", "yes", 5, 60)


def test_live_mode_with_both_keys_no_permission_error(monkeypatch):
    """Having both keys set must NOT raise PermissionError (even though HTTP will fail)."""
    monkeypatch.setenv("KALSHI_LIVE_ENABLED", "1")
    monkeypatch.setenv("KALSHI_API_KEY", "fake_key")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "fake_id")

    # _check_live_permissions should pass; then _http_get raises RuntimeError
    with pytest.raises((RuntimeError, NotImplementedError)):
        L09.get_orderbook("NBA-TEST")


# ---------------------------------------------------------------------------
# Test 6: get_positions aggregates two buys → qty=10, avg_price=65
# ---------------------------------------------------------------------------

def test_get_positions_aggregates_buys(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")

    # Buy 5 at 60, then 5 at 70
    L09.post_order("NBA-TEST", "yes", 5, 60)
    L09.post_order("NBA-TEST", "yes", 5, 70)

    positions = L09.get_positions()

    assert len(positions) == 1
    pos = positions[0]
    assert pos.market_ticker == "NBA-TEST"
    assert pos.side == "yes"
    assert pos.qty == 10
    assert pos.avg_price == pytest.approx(65.0)


def test_get_positions_empty_ledger(isolated_paths):
    positions = L09.get_positions()
    assert positions == []


def test_get_positions_separate_sides(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")

    L09.post_order("NBA-TEST", "yes", 3, 60)
    L09.post_order("NBA-TEST", "no", 7, 44)

    positions = L09.get_positions()
    assert len(positions) == 2

    sides = {p.side for p in positions}
    assert sides == {"yes", "no"}


def test_get_positions_unrealized_pnl_yes(isolated_paths):
    """PnL for a yes position: (mid - avg_price) * qty."""
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")  # yes_bids=[55,100], yes_asks=[56,100] → mid=55.5

    L09.post_order("NBA-TEST", "yes", 10, 50)

    positions = L09.get_positions()
    pos = next(p for p in positions if p.side == "yes")
    # mid = (55+56)/2 = 55.5; avg_price = 50; pnl = (55.5-50)*10 = 55
    assert pos.unrealized_pnl == pytest.approx(55.5, abs=1.0)


# ---------------------------------------------------------------------------
# Test: cancel_order marks order as cancelled
# ---------------------------------------------------------------------------

def test_cancel_order_marks_cancelled(isolated_paths):
    seed_dir, ledger_dir = isolated_paths
    _write_seed(seed_dir, "NBA-TEST")
    orders_file = ledger_dir / "paper_kalshi_orders.json"

    result = L09.post_order("NBA-TEST", "yes", 5, 60)
    order_id = result["order_id"]

    success = L09.cancel_order(order_id)
    assert success is True

    orders = json.loads(orders_file.read_text(encoding="utf-8"))
    cancelled = [o for o in orders if o["order_id"] == order_id]
    assert cancelled[0]["status"] == "cancelled"


def test_cancel_order_unknown_id_returns_false(isolated_paths):
    result = L09.cancel_order("paper_kalshi_nonexistent")
    assert result is False
