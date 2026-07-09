"""Per-file test for fill_model/meta_label_buckets.py -- synthetic ledger in
tmp_path, monkeypatched LEDGER_PATH, no real data/ read.
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_fill_model_meta_label.py -q
"""
from __future__ import annotations

import json

import pytest

from scripts.platformkit.execution.fill_model import meta_label_buckets as mlb


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_load_true_close_kalshi_bets_drops_proxy_and_ungraded(tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    monkeypatch.setattr(mlb, "LEDGER_PATH", ledger)
    _write_jsonl(ledger, [
        {"taken_book": "kalshi", "graded": True, "clv_is_proxy": False, "beat_close": True, "sport": "mlb"},
        {"taken_book": "kalshi", "graded": True, "clv_is_proxy": True, "beat_close": True, "sport": "mlb"},
        {"taken_book": "kalshi", "graded": False, "clv_is_proxy": False, "beat_close": True, "sport": "mlb"},
        {"taken_book": "fanduel", "graded": True, "clv_is_proxy": False, "beat_close": True, "sport": "mlb"},
    ])
    rows = mlb.load_true_close_kalshi_bets()
    assert len(rows) == 1


def test_wilson_ci_symmetric_around_half_at_large_n():
    ci = mlb.wilson_ci(50, 100)
    assert ci is not None
    lo, hi = ci
    assert lo < 0.5 < hi
    assert mlb.wilson_ci(0, 0) is None


def test_edge_bucket_label_quartile_assignment():
    qs = [0.02, 0.05, 0.10]
    assert mlb.edge_bucket_label(0.01, qs) == "Q1_smallest_divergence"
    assert mlb.edge_bucket_label(0.03, qs) == "Q2"
    assert mlb.edge_bucket_label(0.07, qs) == "Q3"
    assert mlb.edge_bucket_label(0.20, qs) == "Q4_largest_divergence"


def test_build_bucket_table_flags_thin_buckets_and_never_blends_proxy(tmp_path, monkeypatch):
    ledger = tmp_path / "clv_ledger.jsonl"
    monkeypatch.setattr(mlb, "LEDGER_PATH", ledger)
    rows = [
        {"taken_book": "kalshi", "graded": True, "clv_is_proxy": False, "beat_close": True,
         "sport": "mlb", "edge": 0.01 + 0.001 * i, "tier": "A"}
        for i in range(8)
    ] + [
        {"taken_book": "kalshi", "graded": True, "clv_is_proxy": True, "beat_close": False,
         "sport": "mlb", "edge": 0.5, "tier": "A"}  # proxy row must never count
    ]
    _write_jsonl(ledger, rows)
    table = mlb.build_bucket_table()
    assert table["n_total_true_close_kalshi_bets"] == 8
    # every non-proxy row beat_close True -> proxy row's False must not leak in
    assert table["by_tier"]["A"]["clv_positive_n"] == 8
    assert table["by_tier"]["A"]["trustworthy"] is False  # n=8 < MIN_BUCKET_N=10


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
