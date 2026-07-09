"""Per-file test for book_replay.py -- synthetic ladder+tape, tmp_path only.
Covers: fill-condition (quote-cross) detection, half-spread math, phase
bucketing, ladder parsing (yes_asks = raw no_dollars convention).
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/execution/test_book_replay.py -q
"""
from __future__ import annotations

import pytest

from scripts.platformkit.execution import book_replay as br


def test_half_spread_math():
    assert br.half_spread(0.40, 0.44) == pytest.approx(0.02)
    assert br.half_spread(None, 0.44) is None
    assert br.half_spread(0.50, 0.40) is None  # crossed book -> None, never negative


def test_ladder_best_uses_no_dollars_inversion():
    # yes_bids best = 0.39 (max price); yes_asks (RAW no_dollars) best = 0.56 -> yes_ask = 1-0.56 = 0.44
    yes_bids = [[0.01, 100.0], [0.39, 5.0]]
    yes_asks = [[0.01, 100.0], [0.56, 3.0]]
    out = br.ladder_best(yes_bids, yes_asks)
    assert out["best_bid"] == 0.39
    assert abs(out["best_ask"] - 0.44) < 1e-9
    assert out["thin3"] == 100.0 + 5.0 + 100.0 + 3.0


def test_ladder_best_empty_side_is_none_not_zero():
    out = br.ladder_best([], [[0.5, 1.0]])
    assert out["best_bid"] is None
    assert out["best_ask"] == 0.5


def test_phase_bucket_terciles():
    assert br.phase_bucket(0, 9) == "early"
    assert br.phase_bucket(4, 9) == "mid"
    assert br.phase_bucket(8, 9) == "late"
    assert br.phase_bucket(0, 1) == "mid"  # degenerate n=1


def test_thinness_tercile_and_breakpoints():
    bps = br.quantile_breakpoints([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert br.thinness_tercile(0.5, bps) == "thin"
    assert br.thinness_tercile(9.0, bps) == "thick"


def test_detect_quote_cross_within_horizon():
    # join best_bid=0.30 at t=0; ask falls to 0.30 at t=100 (within 300s) -> cross
    snaps = [(0.0, 0.30, 0.35), (100.0, 0.31, 0.30), (500.0, 0.31, 0.20)]
    assert br.detect_quote_cross(snaps, 0, 300) == 100.0
    # smaller horizon misses it
    assert br.detect_quote_cross(snaps, 0, 60) is None


def test_detect_quote_cross_no_cross_ever():
    snaps = [(0.0, 0.30, 0.35), (100.0, 0.31, 0.36)]
    assert br.detect_quote_cross(snaps, 0, 900) is None


def test_mid_at_or_after_respects_slack():
    snaps = [(0.0, 0.30, 0.34), (400.0, 0.32, 0.36)]
    # target 300, nearest snap at 400 -> 100s late, within default 120s slack
    assert br.mid_at_or_after(snaps, 300.0) == pytest.approx((0.32 + 0.36) / 2.0)
    # target 100, nearest snap 400 -> 300s late, exceeds slack -> None
    assert br.mid_at_or_after(snaps, 100.0) is None


def test_build_profile_and_taker_cost_synthetic_ticker(tmp_path):
    rows = [
        {"ticker": "T-A", "ts": "2026-01-01T00:00:00Z", "best_bid": 0.40, "best_ask": 0.44, "thin3": 10.0},
        {"ticker": "T-A", "ts": "2026-01-01T00:10:00Z", "best_bid": 0.42, "best_ask": 0.45, "thin3": 20.0},
        {"ticker": "T-A", "ts": "2026-01-01T00:20:00Z", "best_bid": 0.50, "best_ask": 0.60, "thin3": 5.0},
    ]
    profile, taker = br.build_profile_and_taker_cost({"synthsport": rows})
    assert profile["synthsport"]["early"]["spread_price"]["n"] == 1
    assert profile["synthsport"]["late"]["spread_price"]["n"] == 1
    assert sum(v["n"] for v in taker["synthsport"].values()) == 3


def test_build_maker_fill_and_adverse_synthetic():
    rows = [
        {"ticker": "T-A", "ts": "2026-01-01T00:00:00Z", "best_bid": 0.30, "best_ask": 0.35},
        {"ticker": "T-A", "ts": "2026-01-01T00:01:00Z", "best_bid": 0.31, "best_ask": 0.30},
        {"ticker": "T-A", "ts": "2026-01-01T00:06:00Z", "best_bid": 0.34, "best_ask": 0.36},
    ]
    out = br.build_maker_fill_and_adverse(rows)
    assert out["quote_cross_proxy"]["300s"]["n_joins"] >= 1
    assert out["quote_cross_proxy"]["300s"]["pct_crossed"] > 0


def test_load_jsonl_skips_malformed(tmp_path):
    p = tmp_path / "sample.jsonl"
    p.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    rows = br.load_jsonl(p)
    assert rows == [{"a": 1}, {"b": 2}]


if __name__ == "__main__":
    import sys
    import pytest as _pytest
    sys.exit(_pytest.main([__file__, "-q"]))
