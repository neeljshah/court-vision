"""Per-file test for fill_model/fill_realism.py -- synthetic ledger+depth+tape
in tmp_path, monkeypatched paths, no real data/ read.
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_fill_model_fill_realism.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.execution.fill_model import fill_realism as fr


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


@pytest.fixture
def patched_paths(tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    depth_dir = tmp_path / "book_depth" / "kalshi"
    tape_dir = tmp_path / "book_depth" / "kalshi_trades"
    monkeypatch.setattr(fr, "LEDGER_PATH", ledger)
    monkeypatch.setattr(fr, "BOOK_DEPTH_DIR", depth_dir)
    monkeypatch.setattr(fr, "TRADE_TAPE_DIR", tape_dir)
    return ledger, depth_dir, tape_dir


def test_load_kalshi_orders_filters_non_kalshi_and_computes_implied_prob(patched_paths):
    ledger, _depth_dir, _tape_dir = patched_paths
    _write_jsonl(ledger, [
        {"taken_book": "kalshi", "ts": "2026-07-09T00:00:00Z", "market_id": "T-A",
         "taken_decimal": 2.0, "sport": "mlb"},
        {"taken_book": "fanduel", "ts": "2026-07-09T00:00:00Z", "market_id": "T-B",
         "taken_decimal": 2.0, "sport": "mlb"},
    ])
    orders = fr.load_kalshi_orders()
    assert len(orders) == 1
    assert orders[0]["implied_prob"] == pytest.approx(0.5)


def test_marketability_plausible_vs_optimistic():
    order = {"implied_prob": 0.40}
    inside = {"best_bid": 0.35, "best_ask": 0.45}
    outside = {"best_bid": 0.35, "best_ask": 0.38}
    assert fr.marketability(order, inside) == "plausible"
    assert fr.marketability(order, outside) == "optimistic"
    assert fr.marketability(order, {"best_bid": None, "best_ask": 0.5}) is None


def test_nearest_snapshot_respects_window():
    snaps = [{"ts": "2026-07-09T00:00:00Z"}, {"ts": "2026-07-09T00:20:00Z"}]
    t0 = fr._epoch("2026-07-09T00:01:00Z")
    hit = fr.nearest_snapshot(snaps, t0, window_s=600.0)
    assert hit["ts"] == "2026-07-09T00:00:00Z"
    miss = fr.nearest_snapshot(snaps, t0, window_s=30.0)
    assert miss is None


def test_trade_confirms_true_when_print_at_or_through_price():
    order = {"ts": "2026-07-09T00:00:00Z", "implied_prob": 0.50, "market_id": "T-A"}
    trades_by_ticker = {"T-A": [{"trade_ts": "2026-07-09T00:01:00Z", "price": 0.49}]}
    assert fr.trade_confirms(order, trades_by_ticker) is True


def test_trade_confirms_none_when_ticker_absent_from_tape():
    order = {"ts": "2026-07-09T00:00:00Z", "implied_prob": 0.50, "market_id": "T-Z"}
    assert fr.trade_confirms(order, {}) is None


def test_run_fill_realism_end_to_end_not_testable_when_no_overlap(patched_paths):
    ledger, depth_dir, tape_dir = patched_paths
    _write_jsonl(ledger, [
        {"taken_book": "kalshi", "ts": "2026-07-09T00:05:00Z", "market_id": "T-A",
         "taken_decimal": 2.5, "sport": "mlb"},
    ])
    _write_jsonl(depth_dir / "2026-07-09.jsonl", [
        {"ticker": "T-A", "ts": "2026-07-09T00:00:00Z", "best_bid": 0.35, "best_ask": 0.42, "sport": "mlb"},
    ])
    # trade tape ticker never overlaps the order's ticker -> NOT_TESTABLE
    _write_jsonl(tape_dir / "2026-07-09.jsonl", [
        {"ticker": "T-OTHER", "trade_ts": "2026-07-09T00:05:00Z", "price": 0.40, "sport": "mlb"},
    ])
    report = fr.run_fill_realism()
    assert report["n_kalshi_orders"] == 1
    assert report["spread_marketability"]["verdict"] == "measured"
    assert report["spread_marketability"]["n_depth_matched"] == 1
    assert report["trade_tape_confirmation"]["verdict"].startswith("NOT_TESTABLE")
    assert report["order_size_vs_depth_slippage"]["verdict"].startswith("NOT_TESTABLE")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
