"""Tests for scripts/execute_loop/L27_tax_tracking.py.

Run:
    conda run -n basketball_ai --no-capture-output \
        python -m pytest scripts/execute_loop/tests/test_L27_tax.py -v
"""
from __future__ import annotations

import csv
import os
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Ensure project root on path & stub heavy imports
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_DIR))

# Stub nba_api_headers_patch so L27 import doesn't crash
_api_stub = types.ModuleType("src.data.nba_api_headers_patch")
sys.modules.setdefault("src.data.nba_api_headers_patch", _api_stub)

import scripts.execute_loop.L27_tax_tracking as L27  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SETTLED_ISO = "2026-04-01T12:00:00+00:00"  # Q2

def _make_bets(*rows: dict) -> pd.DataFrame:
    """Build a minimal bets DataFrame from dicts (only relevant columns)."""
    defaults = {
        "bet_id": "x",
        "book": "draftkings_dfs",
        "status": "WON",
        "settled_at_iso": _SETTLED_ISO,
        "pnl": 0.0,
    }
    records = []
    for r in rows:
        rec = dict(defaults)
        rec.update(r)
        records.append(rec)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Autouse fixture: redirect all ledger I/O to tmp_path
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolated_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(L27, "_LEDGER_DIR", tmp_path)
    monkeypatch.setattr(L27, "_LEDGER_PATH", tmp_path / "bets.parquet")
    monkeypatch.setattr(L27, "_LEDGER_CSV", tmp_path / "bets.csv")
    # Reset tax rates to known values
    monkeypatch.setattr(L27, "FEDERAL_TAX_RATE", 0.24)
    monkeypatch.setattr(L27, "STATE_TAX_RATE", 0.00)
    yield


# ---------------------------------------------------------------------------
# Test 1: basic DFS bucket — 100 win + 50 loss → net=50, fed=12
# ---------------------------------------------------------------------------
def test_compute_tax_buckets_dfs_basic(tmp_path, monkeypatch):
    df = _make_bets(
        {"book": "draftkings_dfs", "status": "WON", "pnl": 100.0,
         "settled_at_iso": "2026-06-01T00:00:00+00:00"},
        {"book": "draftkings_dfs", "status": "LOST", "pnl": -50.0,
         "settled_at_iso": "2026-06-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    buckets = L27.compute_tax_buckets(2026)
    dfs = next(b for b in buckets if b.source_type == "DFS")

    assert dfs.gross_winnings == pytest.approx(100.0)
    assert dfs.gross_losses == pytest.approx(50.0)
    assert dfs.net == pytest.approx(50.0)
    assert dfs.fed_tax_estimated == pytest.approx(12.0)
    assert dfs.ytd_total == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Test 2: Q2 quarterly payment — Apr-Jun bets, due 2026-06-15
# ---------------------------------------------------------------------------
def test_estimate_quarterly_payment_q2(monkeypatch):
    df = _make_bets(
        {"book": "draftkings_dfs", "status": "WON", "pnl": 200.0,
         "settled_at_iso": "2026-05-15T00:00:00+00:00"},
        {"book": "draftkings_dfs", "status": "LOST", "pnl": -50.0,
         "settled_at_iso": "2026-05-20T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    result = L27.estimate_quarterly_payment(2026, 2)

    assert result["quarter"] == 2
    assert result["due_date"] == "2026-06-15"
    assert result["federal_due"] == pytest.approx(150.0 * 0.24)
    assert result["state_due"] == pytest.approx(0.0)
    assert result["calc_basis"]["gross_winnings"] == pytest.approx(200.0)
    assert result["calc_basis"]["gross_losses"] == pytest.approx(50.0)
    assert result["calc_basis"]["net"] == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# Test 3: export_1099_ready writes valid CSV reloadable via pandas
# ---------------------------------------------------------------------------
def test_export_1099_ready_valid_csv(tmp_path, monkeypatch):
    df = _make_bets(
        {"book": "dk_props", "status": "WON", "pnl": 75.0,
         "settled_at_iso": "2026-03-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    out_path = str(tmp_path / "test_1099.csv")
    returned = L27.export_1099_ready(2026, out_path=out_path)

    assert returned == out_path
    loaded = pd.read_csv(out_path)
    assert set(loaded.columns) >= {"source_type", "gross_winnings", "gross_losses", "net", "year"}
    # All 4 standard types present
    assert set(loaded["source_type"].tolist()) >= {"DFS", "Sportsbook", "Prediction Market", "DeFi"}
    assert all(loaded["year"] == 2026)


# ---------------------------------------------------------------------------
# Test 4: empty / missing ledger → all-zero report, no exceptions
# ---------------------------------------------------------------------------
def test_empty_ledger_no_exception(monkeypatch):
    monkeypatch.setattr(L27, "_load_ledger", lambda: pd.DataFrame())

    buckets = L27.compute_tax_buckets(2026)
    assert len(buckets) == 4
    for b in buckets:
        assert b.gross_winnings == 0.0
        assert b.gross_losses == 0.0
        assert b.net == 0.0
        assert b.fed_tax_estimated == 0.0

    report = L27.annual_tax_report(2026)
    assert report["total_net"] == 0.0
    assert report["total_fed_estimated"] == 0.0
    assert "buckets" in report


# ---------------------------------------------------------------------------
# Test 5: multi-source mix → 3+ distinct buckets with correct sums
# ---------------------------------------------------------------------------
def test_multi_source_mix(monkeypatch):
    df = _make_bets(
        {"book": "draftkings_dfs", "status": "WON", "pnl": 100.0,
         "settled_at_iso": "2026-01-10T00:00:00+00:00"},
        {"book": "dk_props", "status": "WON", "pnl": 60.0,
         "settled_at_iso": "2026-01-10T00:00:00+00:00"},
        {"book": "dk_props", "status": "LOST", "pnl": -20.0,
         "settled_at_iso": "2026-01-10T00:00:00+00:00"},
        {"book": "kalshi", "status": "WON", "pnl": 30.0,
         "settled_at_iso": "2026-01-10T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    buckets = L27.compute_tax_buckets(2026)
    by_type = {b.source_type: b for b in buckets}

    assert "DFS" in by_type
    assert "Sportsbook" in by_type
    assert "Prediction Market" in by_type

    assert by_type["DFS"].net == pytest.approx(100.0)
    assert by_type["Sportsbook"].net == pytest.approx(40.0)
    assert by_type["Prediction Market"].net == pytest.approx(30.0)
    # At least 3 non-zero source types
    non_zero = [b for b in buckets if b.net != 0.0]
    assert len(non_zero) >= 3


# ---------------------------------------------------------------------------
# Test 6: PUSH bets don't change winnings/losses
# ---------------------------------------------------------------------------
def test_push_bets_no_impact(monkeypatch):
    df = _make_bets(
        {"book": "draftkings_dfs", "status": "WON", "pnl": 80.0,
         "settled_at_iso": "2026-02-01T00:00:00+00:00"},
        {"book": "draftkings_dfs", "status": "PUSH", "pnl": 0.0,
         "settled_at_iso": "2026-02-01T00:00:00+00:00"},
        {"book": "draftkings_dfs", "status": "PUSH", "pnl": 0.0,
         "settled_at_iso": "2026-02-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    buckets = L27.compute_tax_buckets(2026)
    dfs = next(b for b in buckets if b.source_type == "DFS")

    assert dfs.gross_winnings == pytest.approx(80.0)
    assert dfs.gross_losses == pytest.approx(0.0)
    assert dfs.net == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# Test 7: negative net bucket → fed_tax_estimated == 0
# ---------------------------------------------------------------------------
def test_negative_net_zero_tax(monkeypatch):
    df = _make_bets(
        {"book": "fanduel_dfs", "status": "WON", "pnl": 20.0,
         "settled_at_iso": "2026-07-01T00:00:00+00:00"},
        {"book": "fanduel_dfs", "status": "LOST", "pnl": -100.0,
         "settled_at_iso": "2026-07-01T00:00:00+00:00"},
    )
    monkeypatch.setattr(L27, "_load_ledger", lambda: df)

    buckets = L27.compute_tax_buckets(2026)
    dfs = next(b for b in buckets if b.source_type == "DFS")

    assert dfs.net == pytest.approx(-80.0)
    assert dfs.fed_tax_estimated == pytest.approx(0.0)
    assert dfs.state_tax_estimated == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Test 8: _atomic_write_text replaces an existing file with new content
# ---------------------------------------------------------------------------
def test_atomic_write_replaces_existing_file(tmp_path):
    dest = tmp_path / "out.csv"
    dest.write_text("old content", encoding="utf-8")

    L27._atomic_write_text(dest, "new content")

    assert dest.read_text(encoding="utf-8") == "new content"
    # No leftover .tmp files
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Unexpected .tmp files: {tmp_files}"


# ---------------------------------------------------------------------------
# Test 9: _atomic_write_text leaves original intact and cleans .tmp on failure
# ---------------------------------------------------------------------------
def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    dest = tmp_path / "safe.csv"
    dest.write_text("original", encoding="utf-8")

    # Patch os.replace to simulate a failure after the temp file is written
    real_replace = os.replace

    def _boom(src, dst):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", _boom)

    with pytest.raises(OSError, match="simulated replace failure"):
        L27._atomic_write_text(dest, "should not land")

    # Original file must be unchanged
    assert dest.read_text(encoding="utf-8") == "original"
    # Temp file must have been cleaned up
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Leaked .tmp files: {tmp_files}"
