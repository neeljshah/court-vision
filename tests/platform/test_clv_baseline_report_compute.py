"""Numeric-correctness tests for clv_baseline_report_compute helpers.

Covers: percentile, stdev, mean, build_pairs.
All expected values are hand-computed from the exact algorithm in the module.
"""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.capture.clv_baseline_report_compute import (
    build_pairs,
    mean,
    percentile,
    stdev,
)

# ---------------------------------------------------------------------------
# percentile
# ---------------------------------------------------------------------------
# Implementation: linear interpolation via idx = (p / 100) * (n - 1)
# For [0,1,2,3,4] (n=5):  idx = (p/100) * 4
#   p=50  -> idx=2.0  -> lo=2, hi=3, frac=0.0 -> 2 + 0*1 = 2.0
#   p=25  -> idx=1.0  -> lo=1, hi=2, frac=0.0 -> 1.0
#   p=75  -> idx=3.0  -> lo=3, hi=4, frac=0.0 -> 3.0
#   p=60  -> idx=2.4  -> lo=2, hi=3, frac=0.4 -> 2 + 0.4*1 = 2.4
#   p=0   -> idx=0.0  -> 0.0
#   p=100 -> idx=4.0  -> lo=4, hi=4, frac=0.0 -> 4.0


class TestPercentile:
    def test_median_five_element(self):
        assert percentile([0, 1, 2, 3, 4], 50) == 2.0

    def test_p25_five_element(self):
        assert percentile([0, 1, 2, 3, 4], 25) == 1.0

    def test_p75_five_element(self):
        assert percentile([0, 1, 2, 3, 4], 75) == 3.0

    def test_p0_returns_minimum(self):
        assert percentile([0, 1, 2, 3, 4], 0) == 0.0

    def test_p100_returns_maximum(self):
        assert percentile([0, 1, 2, 3, 4], 100) == 4.0

    def test_non_integer_percentile_linear_interpolation(self):
        # p=60 on [0,1,2,3,4]: idx = 0.6*4 = 2.4
        # lo=2, hi=3, frac=0.4 -> 2 + 0.4*(3-2) = 2.4
        result = percentile([0, 1, 2, 3, 4], 60)
        assert abs(result - 2.4) < 1e-12, f"Expected 2.4, got {result}"

    def test_single_element_returns_that_element(self):
        assert percentile([42.0], 50) == 42.0

    def test_single_element_any_p_returns_same(self):
        assert percentile([7.0], 0) == 7.0
        assert percentile([7.0], 100) == 7.0

    def test_empty_returns_nan(self):
        result = percentile([], 50)
        assert math.isnan(result)

    def test_two_element_p50_midpoint(self):
        # [10, 20], n=2: idx = 0.5*1 = 0.5 -> lo=0, hi=1, frac=0.5
        # 10 + 0.5*(20-10) = 15.0
        assert percentile([10, 20], 50) == 15.0

    def test_non_uniform_values(self):
        # [1.0, 3.0, 9.0], p=50: n=3, idx=0.5*2=1.0 -> lo=1, frac=0 -> 3.0
        assert percentile([1.0, 3.0, 9.0], 50) == 3.0


# ---------------------------------------------------------------------------
# stdev
# ---------------------------------------------------------------------------
# Implementation: POPULATION std-dev (divides by len(vals), not len-1).
# Docstring: "Return population std-dev of *vals*, or NaN if < 2 items."
#
# [1, 2, 3]: mu=2, variance=(1+0+1)/3 = 2/3, stdev = sqrt(2/3) ≈ 0.816496...
# (sample stdev would be sqrt(1.0) = 1.0 — that is NOT what this impl does)


class TestStdev:
    def test_three_values_population(self):
        # sqrt(2/3) = 0.8164965809277261
        expected = math.sqrt(2 / 3)
        result = stdev([1, 2, 3])
        assert abs(result - expected) < 1e-12, (
            f"Expected population stdev sqrt(2/3)={expected:.10f}, got {result:.10f}. "
            "If this fails the impl switched to sample stdev."
        )

    def test_not_sample_stdev(self):
        # Guard: sample stdev of [1,2,3] = 1.0; population = sqrt(2/3) < 1.0
        result = stdev([1, 2, 3])
        assert result < 1.0, (
            f"stdev([1,2,3])={result} >= 1.0 implies sample formula, not population"
        )

    def test_identical_values_zero(self):
        assert stdev([5.0, 5.0, 5.0]) == 0.0

    def test_two_values(self):
        # [0, 2]: mu=1, variance=(1+1)/2=1, stdev=1.0
        assert stdev([0, 2]) == 1.0

    def test_single_item_returns_nan(self):
        result = stdev([42.0])
        assert math.isnan(result)

    def test_empty_returns_nan(self):
        result = stdev([])
        assert math.isnan(result)

    def test_larger_list(self):
        # [2, 4, 4, 4, 5, 5, 7, 9]: n=8, mu=5
        # variance = (9+1+1+1+0+0+4+16)/8 = 32/8 = 4.0, stdev=2.0
        vals = [2, 4, 4, 4, 5, 5, 7, 9]
        assert abs(stdev(vals) - 2.0) < 1e-12


# ---------------------------------------------------------------------------
# mean
# ---------------------------------------------------------------------------


class TestMean:
    def test_empty_returns_nan(self):
        result = mean([])
        assert math.isnan(result)

    def test_two_values(self):
        assert mean([2, 4]) == 3.0

    def test_single_value(self):
        assert mean([7.0]) == 7.0

    def test_identical_values(self):
        assert mean([5, 5, 5]) == 5.0

    def test_floats(self):
        assert abs(mean([1.0, 2.0, 3.0]) - 2.0) < 1e-12

    def test_negative_values(self):
        assert mean([-1.0, 1.0]) == 0.0


# ---------------------------------------------------------------------------
# build_pairs
# ---------------------------------------------------------------------------

_BASE = {
    "sport": "nba",
    "event_id": "game1",
    "market": "pts",
    "book": "fanduel",
    "side": "over",
}


def _row(kind: str, **overrides) -> dict:
    r = dict(_BASE)
    r["kind"] = kind
    r.update(overrides)
    return r


class TestBuildPairs:
    def test_empty_input(self):
        assert build_pairs([]) == []

    def test_unpaired_open_yields_zero_pairs(self):
        result = build_pairs([_row("open")])
        assert result == []

    def test_unpaired_close_yields_zero_pairs(self):
        result = build_pairs([_row("close")])
        assert result == []

    def test_matched_open_close_yields_one_pair(self):
        open_row = _row("open")
        close_row = _row("close")
        pairs = build_pairs([open_row, close_row])
        assert len(pairs) == 1
        got_open, got_close = pairs[0]
        assert got_open["kind"] == "open"
        assert got_close["kind"] == "close"

    def test_order_open_then_close(self):
        # order should not matter for matching
        open_row = _row("open")
        close_row = _row("close")
        assert len(build_pairs([close_row, open_row])) == 1

    def test_duplicate_opens_only_first_used(self):
        # Two opens for same key; only the first is recorded (pk not in opens guard)
        o1 = _row("open", book="fanduel")
        o2 = _row("open", book="fanduel")
        c1 = _row("close", book="fanduel")
        pairs = build_pairs([o1, o2, c1])
        assert len(pairs) == 1

    def test_different_keys_are_independent(self):
        o_fd = _row("open", book="fanduel")
        c_fd = _row("close", book="fanduel")
        o_dk = _row("open", book="draftkings")
        c_dk = _row("close", book="draftkings")
        pairs = build_pairs([o_fd, c_fd, o_dk, c_dk])
        assert len(pairs) == 2

    def test_open_without_matching_close_excluded(self):
        o_fd = _row("open", book="fanduel")
        o_dk = _row("open", book="draftkings")
        c_dk = _row("close", book="draftkings")
        pairs = build_pairs([o_fd, o_dk, c_dk])
        assert len(pairs) == 1
        _, close_row = pairs[0]
        assert close_row["book"] == "draftkings"

    def test_unknown_kind_ignored(self):
        rows = [_row("open"), {"kind": "unknown"}, _row("close")]
        pairs = build_pairs(rows)
        assert len(pairs) == 1

    def test_pair_preserves_row_identity(self):
        open_row = _row("open")
        open_row["price"] = 1.95
        close_row = _row("close")
        close_row["price"] = 1.88
        got_open, got_close = build_pairs([open_row, close_row])[0]
        assert got_open["price"] == 1.95
        assert got_close["price"] == 1.88
