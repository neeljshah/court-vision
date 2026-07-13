"""Unit tests for scripts.platformkit.benchmarks.clv_replay.replay_mlb --
hand-built frames (deterministic, no file IO) covering the binding rails:
devig reuse / degenerate exclusion, same-book discipline, post-commence
exclusion, and time-bucket math. See replay_mlb.py's module docstring for the
DEVIG REUSE + SAME-BOOK DISCIPLINE framing.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/benchmarks/clv_replay/test_replay_mlb.py -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.benchmarks.clv_replay.replay_mlb import (
    aggregate, bucket_time_to_close, build_speed_curve, compute_clv,
    load_total_snapshots, parse_and_filter_pregame, policy_a, policy_b,
)


def _raw_row(game_id, book, side, odds, devig, captured_at, commence_time="2026-07-01T00:00:00+00:00"):
    return {"market_type": "total", "game_id": game_id, "book": book, "side": side, "odds": odds,
            "devigged_prob": devig, "captured_at": captured_at, "commence_time": commence_time}


def test_degenerate_pair_excluded(tmp_path):
    """A row with devigged_prob None (the both-sides-priced devig check
    failing upstream in markets._devig_pair) never enters the loaded frame --
    real corpus has 0/624466 such rows today, so this is exercised synthetically."""
    import json
    d = tmp_path / "mlb"
    d.mkdir()
    (d / "2026-07-01.jsonl").write_text(
        "\n".join(json.dumps(r) for r in [
            _raw_row("g1", "espn:DraftKings", "over", 1.9, 0.51, "2026-06-30T20:00:00+00:00"),
            _raw_row("g1", "espn:DraftKings", "under", 1.9, None, "2026-06-30T20:00:00+00:00"),
        ]), encoding="utf-8")
    df = load_total_snapshots(d)
    assert len(df) == 1
    assert df.iloc[0]["side"] == "over"


def test_post_commence_snapshot_excluded():
    raw = pd.DataFrame([
        _raw_row("g1", "b1", "over", 1.9, 0.50, "2026-06-30T20:00:00+00:00", "2026-07-01T00:00:00+00:00"),
        _raw_row("g1", "b1", "over", 1.9, 0.60, "2026-07-01T01:00:00+00:00", "2026-07-01T00:00:00+00:00"),
    ])
    out = parse_and_filter_pregame(raw)
    assert len(out) == 1
    assert out.iloc[0]["devigged_prob"] == 0.50


def test_same_book_discipline_no_cross_book_close():
    """Book A closes at 0.55, book B closes at 0.70 -- an early snapshot on
    book A must be graded against A's own close (0.55), never B's (0.70)."""
    raw = pd.DataFrame([
        _raw_row("g1", "bookA", "over", 1.9, 0.50, "2026-06-30T10:00:00+00:00", "2026-07-01T00:00:00+00:00"),
        _raw_row("g1", "bookA", "over", 1.9, 0.55, "2026-06-30T23:00:00+00:00", "2026-07-01T00:00:00+00:00"),
        _raw_row("g1", "bookB", "over", 2.0, 0.70, "2026-06-30T23:00:00+00:00", "2026-07-01T00:00:00+00:00"),
    ])
    pregame = parse_and_filter_pregame(raw)
    clv = compute_clv(pregame)
    early_a = clv[(clv["book"] == "bookA") & (clv["captured_at"] == "2026-06-30T10:00:00+00:00")].iloc[0]
    assert early_a["close_prob"] == pytest.approx(0.55)
    assert early_a["clv_prob"] == pytest.approx(0.05)

    # policy B (best price at that same tick) still uses the taken book's own close.
    b = policy_b(clv)
    tick = b[b["captured_at"] == "2026-06-30T23:00:00+00:00"]
    picked = tick[tick["side"] == "over"].iloc[0]
    assert picked["book"] == "bookB"  # higher odds (2.0 > 1.9)
    assert picked["close_prob"] == pytest.approx(0.70)  # bookB's own close, not bookA's


def test_policy_a_includes_every_snapshot_both_sides():
    raw = pd.DataFrame([
        _raw_row("g1", "b1", "over", 1.9, 0.50, "2026-06-30T20:00:00+00:00"),
        _raw_row("g1", "b1", "under", 1.9, 0.50, "2026-06-30T20:00:00+00:00"),
        _raw_row("g1", "b1", "over", 1.9, 0.55, "2026-06-30T23:00:00+00:00"),
        _raw_row("g1", "b1", "under", 1.9, 0.45, "2026-06-30T23:00:00+00:00"),
    ])
    clv = compute_clv(parse_and_filter_pregame(raw))
    a = policy_a(clv)
    assert len(a) == 4  # nothing collapsed


def test_time_bucket_boundaries():
    assert bucket_time_to_close(0.5) == "<1h"
    assert bucket_time_to_close(0.999) == "<1h"
    assert bucket_time_to_close(1.0) == "1-6h"
    assert bucket_time_to_close(5.99) == "1-6h"
    assert bucket_time_to_close(6.0) == "6-24h"
    assert bucket_time_to_close(23.99) == "6-24h"
    assert bucket_time_to_close(24.0) == ">24h"
    assert bucket_time_to_close(200.0) == ">24h"


def test_speed_curve_monotone_bins_and_deterministic():
    raw = pd.DataFrame([
        _raw_row("g1", "b1", "over", 1.9, 0.50, "2026-06-30T18:00:00+00:00", "2026-07-01T00:00:00+00:00"),  # 6h
        _raw_row("g1", "b1", "over", 1.9, 0.53, "2026-06-30T23:30:00+00:00", "2026-07-01T00:00:00+00:00"),  # 0.5h
        _raw_row("g1", "b1", "over", 1.9, 0.55, "2026-07-01T00:00:00+00:00", "2026-07-01T00:00:00+00:00"),  # 0h (close)
    ])
    clv = compute_clv(parse_and_filter_pregame(raw))
    curve1 = build_speed_curve(policy_a(clv))
    curve2 = build_speed_curve(policy_a(clv))
    assert curve1 == curve2  # deterministic, no randomness anywhere in the pipeline
    labels = [row["hours_before_close"] for row in curve1]
    assert "<=0.5h" in labels and "<=6h" in labels
    six_h_block = next(r for r in curve1 if r["hours_before_close"] == "<=6h")
    assert six_h_block["n"] == 1
    assert six_h_block["mean"] == pytest.approx(0.05)  # 0.55 - 0.50


def test_aggregate_shape():
    raw = pd.DataFrame([
        _raw_row("g1", "b1", "over", 1.9, 0.50, "2026-06-30T20:00:00+00:00"),
        _raw_row("g1", "b1", "over", 1.9, 0.55, "2026-06-30T23:00:00+00:00"),
    ])
    clv = compute_clv(parse_and_filter_pregame(raw))
    agg = aggregate(policy_a(clv))
    assert set(agg.keys()) == {"overall", "by_time_bucket", "by_book"}
    assert agg["overall"]["n"] == 2
    assert "b1" in agg["by_book"]
