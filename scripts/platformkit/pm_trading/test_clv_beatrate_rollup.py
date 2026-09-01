"""Per-file test for clv_beatrate_rollup (BE-R4-5).

Acceptance criteria:
  A. 5 settled true-close kalshi rows -> beat_rate computed (verdict="graded").
  B. Fewer than MIN_N true-close rows -> verdict=INSUFFICIENT_DATA, beat_rate=None.
  C. All-proxy rows -> beat_rate=None, verdict="vs_close UNPROVEN" (not a number).
  D. No $ / dollar / roi / pnl / profit key in any output row.
  E. Missing ledger (load_and_rollup with no file) -> safe empty list, no raise.
  F. Mixed proxy+true-close: proxy rows excluded from beat-rate denominator.
  G. Multiple (sport, market) buckets -> separate rows sorted by (sport, market).
  H. Open rows are silently skipped (only settled rows count).
  I. beat_rate is in [0, 100] when graded.
  J. mean_clv_pct sign is correct (positive when beats > total/2).

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/pm_trading/test_clv_beatrate_rollup.py -q
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from scripts.platformkit.pm_trading.clv_beatrate_rollup import (
    MIN_N,
    MODE_LEGACY,
    MODE_MAKER,
    MODE_TAKER,
    _VERDICT_GRADED,
    _VERDICT_INSUFFICIENT,
    _VERDICT_PROXY_ONLY,
    build_mode_rollup,
    build_rollup,
    load_and_rollup,
)

# ---------------------------------------------------------------------------
# Helpers: fixture factories
# ---------------------------------------------------------------------------

def _settled(
    sport: str,
    market: str,
    clv_pct: Optional[float],
    *,
    clv_is_proxy: bool = False,
    taken_book: str = "kalshi",
) -> Dict[str, Any]:
    """Minimal settled CLV ledger row for testing."""
    row: Dict[str, Any] = {
        "status": "settled",
        "sport": sport,
        "market": market,
        "clv_pct": clv_pct,
        "clv_is_proxy": clv_is_proxy,
        "taken_book": taken_book,
        "stake_units": 1.0,
        "executed": False,
    }
    return row


def _open(sport: str, market: str) -> Dict[str, Any]:
    """Minimal open (unsettled) row."""
    return {
        "status": "open",
        "sport": sport,
        "market": market,
        "clv_pct": None,
        "clv_is_proxy": False,
        "stake_units": 1.0,
        "executed": False,
    }


def _find_row(rollup: List[Dict[str, Any]], sport: str, market: str) -> Optional[Dict[str, Any]]:
    sport_n = sport.strip().lower()
    market_n = market.strip().lower()
    for row in rollup:
        if row["sport"] == sport_n and row["market"] == market_n:
            return row
    return None


# ---------------------------------------------------------------------------
# Forbidden field check
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "$", "dollar", "roi", "pnl", "profit", "usd", "cash",
    "dollar_edge", "roi_edge", "guaranteed",
}


def _assert_no_dollar_fields(rollup: List[Dict[str, Any]]) -> None:
    """Assert no $ / dollar / roi / pnl field is present in any output row."""
    for row in rollup:
        for key in row:
            lower_key = key.lower()
            for forbidden in _FORBIDDEN_KEYS:
                assert forbidden not in lower_key, (
                    "Forbidden field key found: %r contains %r" % (key, forbidden)
                )


# ---------------------------------------------------------------------------
# Test A: 5 settled true-close rows -> beat_rate graded
# ---------------------------------------------------------------------------

def test_five_true_close_rows_produce_graded_beat_rate():
    """Acceptance A: 5 settled true-close kalshi rows -> graded beat_rate."""
    rows = [
        _settled("nba", "moneyline", clv_pct=+2.0, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=+1.5, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=-0.5, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=+3.0, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=+0.1, taken_book="kalshi"),
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]

    assert row["verdict"] == _VERDICT_GRADED, "Expected graded verdict"
    assert row["beat_rate"] is not None, "beat_rate should be computed"
    assert isinstance(row["beat_rate"], float)
    assert 0.0 <= row["beat_rate"] <= 100.0
    assert row["n_true_close"] == 5
    assert row["n_proxy"] == 0
    # 4 out of 5 beat the close (clv_pct > 0)
    assert row["beat_rate"] == pytest.approx(80.0, abs=0.01)
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test B: fewer than MIN_N true-close rows -> INSUFFICIENT_DATA
# ---------------------------------------------------------------------------

def test_fewer_than_min_n_rows_is_insufficient_data():
    """Acceptance B: fewer than MIN_N rows -> INSUFFICIENT_DATA, beat_rate=None."""
    assert MIN_N == 5, "Sanity: MIN_N expected to be 5 for this test"
    rows = [
        _settled("mlb", "totals", clv_pct=+1.0),
        _settled("mlb", "totals", clv_pct=+2.0),
        # Only 2 true-close rows -- below MIN_N=5
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]

    assert row["verdict"] == _VERDICT_INSUFFICIENT
    assert row["beat_rate"] is None
    assert row["mean_clv_pct"] is None
    assert row["n_true_close"] == 2
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test C: all-proxy rows -> vs_close UNPROVEN
# ---------------------------------------------------------------------------

def test_all_proxy_rows_produce_unproven_verdict():
    """Acceptance C: all-proxy rows -> verdict='vs_close UNPROVEN', beat_rate=None."""
    rows = [
        _settled("tennis", "spread", clv_pct=+1.0, clv_is_proxy=True),
        _settled("tennis", "spread", clv_pct=+2.0, clv_is_proxy=True),
        _settled("tennis", "spread", clv_pct=-0.5, clv_is_proxy=True),
        _settled("tennis", "spread", clv_pct=+0.8, clv_is_proxy=True),
        _settled("tennis", "spread", clv_pct=+1.1, clv_is_proxy=True),
        _settled("tennis", "spread", clv_pct=+0.3, clv_is_proxy=True),
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]

    assert row["verdict"] == _VERDICT_PROXY_ONLY
    assert row["beat_rate"] is None
    assert row["mean_clv_pct"] is None
    assert row["n_proxy"] == 6
    assert row["n_true_close"] == 0
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test D: no $ fields anywhere
# ---------------------------------------------------------------------------

def test_no_dollar_fields_in_any_output():
    """Acceptance D: no $ / roi / pnl / profit key in any output row."""
    rows = [_settled("soccer", "totals", clv_pct=float(i)) for i in range(MIN_N + 2)]
    rollup = build_rollup(rows)
    _assert_no_dollar_fields(rollup)
    # Also check the graded row directly
    assert "roi" not in rollup[0]
    assert "pnl" not in rollup[0]
    assert "profit" not in rollup[0]
    assert "dollar" not in str(rollup[0]).lower()


# ---------------------------------------------------------------------------
# Test E: missing ledger -> safe empty list
# ---------------------------------------------------------------------------

def test_load_and_rollup_missing_ledger_returns_empty():
    """Acceptance E: missing ledger path -> safe empty list, no exception."""
    nonexistent = Path("/tmp/does_not_exist_clv_ledger_be_r4_5.jsonl")
    result = load_and_rollup(path=nonexistent)
    assert isinstance(result, list)
    assert result == []


# ---------------------------------------------------------------------------
# Test F: mixed proxy + true-close -- proxy excluded from denominator
# ---------------------------------------------------------------------------

def test_mixed_proxy_and_true_close_excludes_proxy_from_beat_rate():
    """Acceptance F: proxy rows excluded from beat-rate numerator/denominator."""
    rows = [
        # 5 true-close rows; 4 beat the close
        _settled("nba", "spread", clv_pct=+1.0, clv_is_proxy=False),
        _settled("nba", "spread", clv_pct=+2.0, clv_is_proxy=False),
        _settled("nba", "spread", clv_pct=-3.0, clv_is_proxy=False),
        _settled("nba", "spread", clv_pct=+0.5, clv_is_proxy=False),
        _settled("nba", "spread", clv_pct=+1.5, clv_is_proxy=False),
        # 10 proxy rows that all lose (should NOT count)
        *[_settled("nba", "spread", clv_pct=-10.0, clv_is_proxy=True) for _ in range(10)],
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]

    assert row["verdict"] == _VERDICT_GRADED
    assert row["n_true_close"] == 5
    assert row["n_proxy"] == 10
    # 4/5 = 80% based ONLY on the true-close rows
    assert row["beat_rate"] == pytest.approx(80.0, abs=0.01)
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test G: multiple (sport, market) buckets
# ---------------------------------------------------------------------------

def test_multiple_sport_market_buckets_produce_separate_sorted_rows():
    """Acceptance G: multiple buckets -> separate rows, sorted by (sport, market)."""
    rows = [
        # MLB totals: 5 true-close, all positive
        *[_settled("mlb", "totals", clv_pct=+1.0) for _ in range(MIN_N)],
        # NBA moneyline: 3 true-close -- below MIN_N -> INSUFFICIENT_DATA
        *[_settled("nba", "moneyline", clv_pct=+0.5) for _ in range(3)],
        # Soccer spread: 5 proxy -- all proxy -> vs_close UNPROVEN
        *[_settled("soccer", "spread", clv_pct=+0.5, clv_is_proxy=True) for _ in range(MIN_N)],
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 3

    # Sort order: (sport, market) -> mlb/totals, nba/moneyline, soccer/spread
    assert rollup[0]["sport"] == "mlb"
    assert rollup[0]["market"] == "totals"
    assert rollup[0]["verdict"] == _VERDICT_GRADED

    assert rollup[1]["sport"] == "nba"
    assert rollup[1]["market"] == "moneyline"
    assert rollup[1]["verdict"] == _VERDICT_INSUFFICIENT

    assert rollup[2]["sport"] == "soccer"
    assert rollup[2]["market"] == "spread"
    assert rollup[2]["verdict"] == _VERDICT_PROXY_ONLY

    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test H: open rows skipped
# ---------------------------------------------------------------------------

def test_open_rows_are_skipped():
    """Acceptance H: open rows are silently skipped."""
    rows = [
        _open("nba", "moneyline"),
        _open("mlb", "totals"),
        _settled("nba", "moneyline", clv_pct=+1.0),
        _settled("nba", "moneyline", clv_pct=+1.0),
    ]
    rollup = build_rollup(rows)
    # Only settled rows contribute; only nba/moneyline has settled rows
    assert len(rollup) == 1
    assert rollup[0]["n_settled"] == 2
    assert rollup[0]["sport"] == "nba"
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test I: beat_rate in [0, 100] when graded
# ---------------------------------------------------------------------------

def test_beat_rate_in_valid_range():
    """Acceptance I: beat_rate is a float in [0, 100] when verdict is graded."""
    rows = [_settled("tennis", "moneyline", clv_pct=float(i % 3) - 1.0)
            for i in range(MIN_N + 3)]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]
    assert row["verdict"] == _VERDICT_GRADED
    br = row["beat_rate"]
    assert isinstance(br, float) and math.isfinite(br)
    assert 0.0 <= br <= 100.0


# ---------------------------------------------------------------------------
# Test J: mean_clv_pct sign
# ---------------------------------------------------------------------------

def test_mean_clv_pct_sign_matches_expectation():
    """Acceptance J: mean_clv_pct is positive when majority of rows are positive."""
    rows = [
        _settled("mlb", "moneyline", clv_pct=+3.0),
        _settled("mlb", "moneyline", clv_pct=+3.0),
        _settled("mlb", "moneyline", clv_pct=+3.0),
        _settled("mlb", "moneyline", clv_pct=+3.0),
        _settled("mlb", "moneyline", clv_pct=-1.0),  # one loser
    ]
    rollup = build_rollup(rows)
    assert len(rollup) == 1
    row = rollup[0]
    assert row["verdict"] == _VERDICT_GRADED
    assert row["mean_clv_pct"] is not None
    assert row["mean_clv_pct"] > 0.0, "Expected positive mean CLV"
    # Exact: (3+3+3+3-1)/5 = 11/5 = 2.2
    assert row["mean_clv_pct"] == pytest.approx(2.2, abs=1e-4)
    _assert_no_dollar_fields(rollup)


# ---------------------------------------------------------------------------
# Test: empty input
# ---------------------------------------------------------------------------

def test_empty_rows_returns_empty_list():
    """Empty input produces an empty rollup."""
    assert build_rollup([]) == []


# ---------------------------------------------------------------------------
# Test: real_money_deny is always True
# ---------------------------------------------------------------------------

def test_real_money_deny_always_true():
    """Invariant: real_money_deny=True on every output row."""
    rows = [_settled("nba", "moneyline", clv_pct=+1.0) for _ in range(MIN_N)]
    rollup = build_rollup(rows)
    for row in rollup:
        assert row.get("real_money_deny") is True


# ---------------------------------------------------------------------------
# Test: non-dict items in input are silently skipped
# ---------------------------------------------------------------------------

def test_non_dict_items_skipped():
    """Non-dict items in the input list are silently skipped."""
    rows: Any = [
        None,
        "garbage",
        42,
        _settled("nba", "moneyline", clv_pct=+1.0),
    ]
    result = build_rollup(rows)
    # Only 1 settled row; below MIN_N
    assert len(result) == 1
    assert result[0]["n_settled"] == 1
    assert result[0]["verdict"] == _VERDICT_INSUFFICIENT


# ---------------------------------------------------------------------------
# Execution-mode axis (S1f, matrix R9): maker / taker / legacy
# ---------------------------------------------------------------------------

def _ingame(taken_book: str, clv_pct: Optional[float], unit_result: Optional[float] = None) -> Dict[str, Any]:
    """Minimal settled paper_ingame-channel row (the only channel with a
    maker/legacy split -- see _row_exec_mode)."""
    row: Dict[str, Any] = {
        "status": "settled",
        "sport": "nba",
        "market": "moneyline",
        "channel": "paper_ingame",
        "clv_pct": clv_pct,
        "clv_is_proxy": False,
        "taken_book": taken_book,
        "stake_units": 1.0,
    }
    if unit_result is not None:
        row["unit_result"] = unit_result
    return row


def test_mode_axis_three_modes_correct_counts_legacy_excluded_maker_honest():
    """Synthetic ledger with maker+taker+legacy rows:
      - build_mode_rollup shows all three modes with correct counts.
      - build_rollup's headline (sport, market) series excludes legacy rows.
      - the empty maker pool reports n_settled=0, never taker's numbers.
    """
    rows = [
        # taker: real venue, immediate fill (no channel -> not paper_ingame)
        _settled("nba", "moneyline", clv_pct=+1.0, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=+1.0, taken_book="kalshi"),
        _settled("nba", "moneyline", clv_pct=-0.5, taken_book="kalshi"),
        # legacy: paper_ingame channel, pre-maker-tag default taken_book
        _ingame(taken_book="paper_ingame", clv_pct=+2.0),
        _ingame(taken_book="paper_ingame", clv_pct=+2.0),
        # NOTE: zero maker-tagged rows -- the maker pool is genuinely empty,
        # matching the real ledger as of 2026-09-01 (matrix R9).
    ]

    mode_rollup = build_mode_rollup(rows)
    assert set(mode_rollup) == {MODE_MAKER, MODE_TAKER, MODE_LEGACY}

    maker = mode_rollup[MODE_MAKER]
    assert maker["n_settled"] == 0
    assert maker["beat_rate"] is None
    assert maker["mean_clv_pct"] is None
    assert maker["verdict"] == _VERDICT_INSUFFICIENT

    taker = mode_rollup[MODE_TAKER]
    assert taker["n_settled"] == 3
    # Empty maker pool never silently reports the taker bucket's numbers.
    assert maker["n_settled"] != taker["n_settled"]

    legacy = mode_rollup[MODE_LEGACY]
    assert legacy["n_settled"] == 2

    # Headline (sport, market) series excludes legacy: only the 3 taker rows.
    headline = build_rollup(rows)
    assert len(headline) == 1
    assert headline[0]["sport"] == "nba"
    assert headline[0]["n_settled"] == 3


def test_mode_axis_maker_tagged_row_classifies_as_maker_fees_netted():
    """A row explicitly tagged paper_ingame_maker is "maker"; its fees-netted
    unit_result (grade_paper_one) surfaces as mean_unit_result, context-only."""
    rows = [_ingame(taken_book="paper_ingame_maker", clv_pct=+1.5, unit_result=0.42)]
    maker = build_mode_rollup(rows)[MODE_MAKER]
    assert maker["n_settled"] == 1
    assert maker["n_unit_result"] == 1
    assert maker["mean_unit_result"] == pytest.approx(0.42)


def test_mode_axis_non_ingame_rows_are_never_legacy():
    """Pregame/PM rows (no paper_ingame channel) are always "taker", never
    misclassified as the paper_ingame-specific "legacy" bucket."""
    rows = [_settled("mlb", "totals", clv_pct=+1.0, taken_book="fanduel")]
    mode_rollup = build_mode_rollup(rows)
    assert mode_rollup[MODE_TAKER]["n_settled"] == 1
    assert mode_rollup[MODE_LEGACY]["n_settled"] == 0
