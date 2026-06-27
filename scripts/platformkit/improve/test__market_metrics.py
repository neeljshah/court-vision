"""Per-file tests for scripts.platformkit.improve._market_metrics.

Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/improve/test__market_metrics.py -q
"""
from __future__ import annotations

import math

import pytest

from scripts.platformkit.improve._market_metrics import (
    _valid_close,
    _valid_scored,
    readout_for_segment,
)


# ---------------------------------------------------------------------------
# Helper: build a minimal valid row
# ---------------------------------------------------------------------------

def _row(p_raw=0.6, y=1.0, p_close=None):
    r = {"p_raw": p_raw, "y": y}
    if p_close is not None:
        r["p_close"] = p_close
    return r


# ---------------------------------------------------------------------------
# _valid_scored unit tests
# ---------------------------------------------------------------------------

class TestValidScored:
    def test_normal_row_valid(self):
        assert _valid_scored(_row(p_raw=0.6, y=1.0)) is True

    def test_y_none_invalid(self):
        assert _valid_scored({"p_raw": 0.5, "y": None}) is False

    def test_p_raw_none_invalid(self):
        assert _valid_scored({"p_raw": None, "y": 1.0}) is False

    def test_p_raw_nan_invalid(self):
        assert _valid_scored({"p_raw": float("nan"), "y": 1.0}) is False

    def test_p_raw_inf_invalid(self):
        assert _valid_scored({"p_raw": float("inf"), "y": 1.0}) is False

    def test_p_raw_out_of_range_high(self):
        assert _valid_scored({"p_raw": 1.5, "y": 1.0}) is False

    def test_p_raw_out_of_range_low(self):
        assert _valid_scored({"p_raw": -0.1, "y": 0.0}) is False

    def test_y_float_half_invalid(self):
        # y must be 0.0 or 1.0 exactly
        assert _valid_scored({"p_raw": 0.5, "y": 0.5}) is False

    def test_missing_key_invalid(self):
        assert _valid_scored({"p_raw": 0.5}) is False


# ---------------------------------------------------------------------------
# _valid_close unit tests
# ---------------------------------------------------------------------------

class TestValidClose:
    def test_finite_in_range(self):
        assert _valid_close({"p_close": 0.45}) is True

    def test_none_invalid(self):
        assert _valid_close({"p_close": None}) is False

    def test_nan_invalid(self):
        assert _valid_close({"p_close": float("nan")}) is False

    def test_out_of_range(self):
        assert _valid_close({"p_close": 1.2}) is False

    def test_missing_key(self):
        assert _valid_close({}) is False


# ---------------------------------------------------------------------------
# readout_for_segment tests
# ---------------------------------------------------------------------------

class TestReadoutForSegment:
    def test_empty_rows(self):
        """(a) empty rows -> {"n": 0}"""
        out = readout_for_segment([])
        assert out == {"n": 0}

    def test_void_row_excluded(self):
        """(b) void row with y=None among valid rows: no crash, excluded from n"""
        valid_rows = [_row(0.3, 0.0), _row(0.7, 1.0)]
        void_row = {"p_raw": 0.5, "y": None}
        rows = valid_rows + [void_row]
        out = readout_for_segment(rows)
        assert out["n"] == 2
        assert math.isfinite(out["raw_brier"])
        assert math.isfinite(out["raw_ece"])

    def test_nan_p_raw_excluded(self):
        """(c) row with p_raw=nan is excluded"""
        valid = [_row(0.4, 0.0), _row(0.6, 1.0)]
        bad = {"p_raw": float("nan"), "y": 1.0}
        out = readout_for_segment(valid + [bad])
        assert out["n"] == 2

    def test_out_of_range_p_raw_excluded(self):
        """(d) row with p_raw=1.5 is excluded"""
        valid = [_row(0.4, 0.0), _row(0.6, 1.0)]
        bad = {"p_raw": 1.5, "y": 1.0}
        out = readout_for_segment(valid + [bad])
        assert out["n"] == 2

    def test_normal_rows_finite_metrics(self):
        """(e) normal rows produce finite raw_brier/raw_ece and correct n"""
        rows = [
            _row(0.2, 0.0),
            _row(0.8, 1.0),
            _row(0.5, 1.0),
            _row(0.3, 0.0),
        ]
        out = readout_for_segment(rows)
        assert out["n"] == 4
        assert math.isfinite(out["raw_brier"])
        assert math.isfinite(out["raw_ece"])
        assert math.isfinite(out["base_rate"])
        assert math.isfinite(out["sharpness"])

    def test_with_close_only_valid_close_rows(self):
        """(f) with_close metrics computed only over rows with finite in-range p_close"""
        rows = [
            _row(0.6, 1.0, p_close=0.55),   # valid + valid close
            _row(0.4, 0.0, p_close=None),    # valid scored, no close
            _row(0.5, 1.0, p_close=float("nan")),  # valid scored, bad close
            _row(0.7, 1.0, p_close=1.3),     # valid scored, out-of-range close
        ]
        out = readout_for_segment(rows)
        assert out["n"] == 4
        assert out["n_with_close"] == 1
        assert out["bss_vs_close"] is not None
        assert math.isfinite(out["bss_vs_close"])

    def test_no_close_rows_gives_none_metrics(self):
        """(f) bss_vs_close / pct_beat_close are None when no valid p_close rows exist"""
        rows = [_row(0.4, 0.0), _row(0.6, 1.0)]
        out = readout_for_segment(rows)
        assert out["n_with_close"] == 0
        assert out["bss_vs_close"] is None
        assert out["pct_beat_close"] is None

    def test_all_void_rows_returns_n_zero(self):
        """All void rows -> n == 0, same shape as empty"""
        rows = [
            {"p_raw": None, "y": 1.0},
            {"p_raw": 0.5, "y": None},
        ]
        out = readout_for_segment(rows)
        assert out == {"n": 0}
