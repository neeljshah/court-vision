"""test_L12_prophet.py — Tests for L12_prophet_client.py (paper mode only).

All 6 required tests + bonuses. No HTTP calls; seed dirs and ledger redirected
to tmp_path fixtures.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup — import L12 directly
# ---------------------------------------------------------------------------
_TEST_DIR = Path(__file__).resolve().parent
_LOOP_DIR = _TEST_DIR.parent
sys.path.insert(0, str(_LOOP_DIR))

import L12_prophet_client as L12

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def paper_mode(monkeypatch):
    """Ensure paper mode for every test by clearing live env vars."""
    monkeypatch.delenv("PROPHET_LIVE_ENABLED", raising=False)
    monkeypatch.delenv("PROPHET_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def clear_idempotency_cache():
    """Wipe the in-process idempotency cache before each test."""
    L12._IDEMPOTENCY_CACHE.clear()
    yield
    L12._IDEMPOTENCY_CACHE.clear()


@pytest.fixture()
def seed_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect L12 seed dir to a fresh tmp_path subdir and populate test data."""
    sdir = tmp_path / "exchange_seed" / "prophet"
    sdir.mkdir(parents=True)

    # markets_2026-05-25.json
    markets_file = sdir / "markets_2026-05-25.json"
    markets_file.write_text(
        json.dumps([
            {
                "market_id": "nba_lebron_pts_25_5",
                "player": "LeBron James",
                "stat": "PTS",
                "line": 25.5,
                "tipoff": "2026-05-25T20:00Z",
            }
        ]),
        encoding="utf-8",
    )

    # nba_lebron_pts_25_5.json — orderbook seed
    ob_file = sdir / "nba_lebron_pts_25_5.json"
    ob_file.write_text(
        json.dumps({
            "market_id": "nba_lebron_pts_25_5",
            "bids": [[1.85, 100], [1.80, 200]],
            "asks": [[1.95, 100], [2.00, 200]],
            "ts": 1716663600,
        }),
        encoding="utf-8",
    )

    monkeypatch.setattr(L12, "_SEED_DIR", sdir)
    return sdir


@pytest.fixture()
def ledger_dir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect L12 ledger dir to a fresh tmp_path subdir."""
    ldir = tmp_path / "ledger"
    ldir.mkdir(parents=True)
    monkeypatch.setattr(L12, "_LEDGER_DIR", ldir)
    return ldir


# ---------------------------------------------------------------------------
# Test 1: get_orderbook reads seed → returns dict with non-empty bids/asks
# ---------------------------------------------------------------------------

def test_get_orderbook_returns_bids_asks(seed_dir, ledger_dir):
    book = L12.get_orderbook("nba_lebron_pts_25_5")
    assert isinstance(book, dict)
    assert "bids" in book and len(book["bids"]) > 0
    assert "asks" in book and len(book["asks"]) > 0
    assert book["bids"][0][0] == 1.85
    assert book["asks"][0][0] == 1.95
    assert book["ts"] == 1716663600


# ---------------------------------------------------------------------------
# Test 2: post_order paper → order_id starts with "paper-", ledger gains 1 row
# ---------------------------------------------------------------------------

def test_post_order_paper_returns_paper_prefix_and_writes_ledger(seed_dir, ledger_dir):
    result = L12.post_order(
        market_id="nba_lebron_pts_25_5",
        side="over",
        qty=10.0,
        price_decimal=1.90,
    )
    assert "order_id" in result
    assert result["order_id"].startswith("paper-")
    assert result["status"] == "filled"

    ledger_file = ledger_dir / "paper_prophet_orders.json"
    assert ledger_file.exists()
    orders = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(orders) == 1
    assert orders[0]["market_id"] == "nba_lebron_pts_25_5"
    assert orders[0]["side"] == "over"
    assert orders[0]["qty"] == 10.0
    assert orders[0]["price_decimal"] == 1.90


# ---------------------------------------------------------------------------
# Test 3: Same idempotency_key twice → same order_id, ledger length unchanged
# ---------------------------------------------------------------------------

def test_idempotency_key_no_double_write(seed_dir, ledger_dir):
    ikey = "idem-prophet-abc-999"
    r1 = L12.post_order(
        "nba_lebron_pts_25_5", "over", 5.0, 1.90, idempotency_key=ikey
    )
    r2 = L12.post_order(
        "nba_lebron_pts_25_5", "over", 5.0, 1.90, idempotency_key=ikey
    )

    assert r1["order_id"] == r2["order_id"]

    ledger_file = ledger_dir / "paper_prophet_orders.json"
    orders = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert len(orders) == 1  # second call must NOT append a new row


# ---------------------------------------------------------------------------
# Test 4a: post_order(price_decimal=1.0) → ValueError (boundary: exactly 1.0)
# Test 4b: post_order(price_decimal=100.5) → ValueError (above 100)
# ---------------------------------------------------------------------------

def test_post_order_price_decimal_at_lower_boundary_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="price_decimal"):
        L12.post_order("nba_lebron_pts_25_5", "over", 5.0, 1.0)


def test_post_order_price_decimal_above_100_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="price_decimal"):
        L12.post_order("nba_lebron_pts_25_5", "over", 5.0, 100.5)


# ---------------------------------------------------------------------------
# Test 5: PROPHET_LIVE_ENABLED=1 without PROPHET_API_KEY → PermissionError
# ---------------------------------------------------------------------------

def test_live_enabled_without_api_key_raises(monkeypatch, seed_dir, ledger_dir):
    monkeypatch.setenv("PROPHET_LIVE_ENABLED", "1")
    monkeypatch.delenv("PROPHET_API_KEY", raising=False)

    with pytest.raises(PermissionError, match="PROPHET_API_KEY"):
        L12.find_nba_prop_markets("2026-05-25")

    with pytest.raises(PermissionError):
        L12.get_orderbook("nba_lebron_pts_25_5")

    with pytest.raises(PermissionError):
        L12.post_order("nba_lebron_pts_25_5", "over", 5.0, 1.90)


# ---------------------------------------------------------------------------
# Test 6: get_positions aggregates 2 fills same (market_id, side)
#          at 1.85 + 1.95 qty 10/10 → 1 position qty=20, avg=1.90
# ---------------------------------------------------------------------------

def test_get_positions_aggregates_two_fills(seed_dir, ledger_dir):
    L12.post_order("nba_lebron_pts_25_5", "over", 10.0, 1.85)
    L12.post_order("nba_lebron_pts_25_5", "over", 10.0, 1.95)

    positions = L12.get_positions()
    assert isinstance(positions, list)
    assert len(positions) == 1

    pos = positions[0]
    assert pos.market_id == "nba_lebron_pts_25_5"
    assert pos.side == "over"
    assert pos.qty == 20.0
    # VWAP: (10*1.85 + 10*1.95) / 20 = 38.0 / 20 = 1.90
    assert abs(pos.avg_price - 1.90) < 1e-6
    assert isinstance(pos.unrealized_pnl, float)


# ---------------------------------------------------------------------------
# Bonus: get_orderbook missing market → KeyError
# ---------------------------------------------------------------------------

def test_get_orderbook_missing_market_raises(seed_dir, ledger_dir):
    with pytest.raises(KeyError):
        L12.get_orderbook("nonexistent_market_xyz")


# ---------------------------------------------------------------------------
# Bonus: post_order(qty=0) → ValueError
# ---------------------------------------------------------------------------

def test_post_order_zero_qty_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="qty must be > 0"):
        L12.post_order("nba_lebron_pts_25_5", "over", 0.0, 1.90)


# ---------------------------------------------------------------------------
# Bonus: post_order with invalid side → ValueError
# ---------------------------------------------------------------------------

def test_post_order_invalid_side_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="side"):
        L12.post_order("nba_lebron_pts_25_5", "back", 5.0, 1.90)


# ---------------------------------------------------------------------------
# Bonus: post_order with empty market_id → ValueError
# ---------------------------------------------------------------------------

def test_post_order_empty_market_id_raises(seed_dir, ledger_dir):
    with pytest.raises(ValueError, match="market_id"):
        L12.post_order("", "over", 5.0, 1.90)


# ---------------------------------------------------------------------------
# Bonus: cancel_order in paper mode → True
# ---------------------------------------------------------------------------

def test_cancel_order_paper_returns_true(seed_dir, ledger_dir):
    result = L12.post_order("nba_lebron_pts_25_5", "over", 5.0, 1.90)
    ok = L12.cancel_order(result["order_id"])
    assert ok is True


# ---------------------------------------------------------------------------
# Bonus: find_nba_prop_markets reads seed and returns correct market
# ---------------------------------------------------------------------------

def test_find_nba_prop_markets_returns_list(seed_dir, ledger_dir):
    markets = L12.find_nba_prop_markets("2026-05-25")
    assert isinstance(markets, list)
    assert len(markets) >= 1
    assert markets[0]["market_id"] == "nba_lebron_pts_25_5"
    assert markets[0]["player"] == "LeBron James"
    assert markets[0]["stat"] == "PTS"
    assert markets[0]["line"] == 25.5
