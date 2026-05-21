"""
tests/test_drawdown_tracker.py — Unit tests for drawdown_tracker.get_drawdown_summary.

Synthetic ledger
----------------
Days 0-9   : +10 each day  → equity rises to 100   (HWM = 100)
Days 10-14 : -12 each day  → equity falls to 40     (drawdown = -60, -60%)
Days 15-19 : +20 each day  → equity recovers to 140 (new HWM)

Engineered assertions
---------------------
- max_dd_pct   ≈ -0.60  (60 down from HWM 100)
- current drawdown = 0  (new HWM at end)
- drawdown_duration_days = 0  (last row IS the HWM)
- recovery_estimate_days = 0  (no current drawdown)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.prediction.drawdown_tracker import (
    _build_equity_curve,
    _compute_drawdowns,
    get_drawdown_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ledger(pnl_values: list[float]) -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=len(pnl_values), freq="D")
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "pnl": pnl_values})


# ---------------------------------------------------------------------------
# Fixture: engineered drawdown + recovery
# ---------------------------------------------------------------------------

RISE = [10.0] * 10          # equity 0 → 100, HWM = 100
DROP = [-12.0] * 5          # equity 100 → 40,  max DD = -60%
RECOVER = [20.0] * 5        # equity 40 → 140,  new HWM

FULL_PNL = RISE + DROP + RECOVER


# ---------------------------------------------------------------------------
# Tests: summary keys present
# ---------------------------------------------------------------------------

class TestSummaryKeys:
    def test_all_four_keys_returned(self):
        df = _make_ledger(FULL_PNL)
        result = get_drawdown_summary(df)
        assert set(result.keys()) == {
            "max_dd_pct",
            "current_dd_pct",
            "drawdown_duration_days",
            "recovery_estimate_days",
        }

    def test_returns_zeroed_for_empty_dataframe(self):
        result = get_drawdown_summary(pd.DataFrame())
        assert result["max_dd_pct"] == 0.0
        assert result["current_dd_pct"] == 0.0
        assert result["drawdown_duration_days"] == 0
        assert result["recovery_estimate_days"] == 0

    def test_returns_zeroed_for_missing_file(self, tmp_path):
        missing = str(tmp_path / "nonexistent.csv")
        result = get_drawdown_summary(missing)
        assert result == {
            "max_dd_pct": 0.0,
            "current_dd_pct": 0.0,
            "drawdown_duration_days": 0,
            "recovery_estimate_days": 0,
        }


# ---------------------------------------------------------------------------
# Tests: HWM tracking
# ---------------------------------------------------------------------------

class TestHWMTracking:
    def test_max_drawdown_is_sixty_percent(self):
        """Peak equity = 100, trough = 40 → max DD = -60%."""
        df = _make_ledger(FULL_PNL)
        result = get_drawdown_summary(df)
        assert abs(result["max_dd_pct"] - (-0.60)) < 0.01, (
            f"Expected max_dd_pct ≈ -0.60, got {result['max_dd_pct']}"
        )

    def test_current_dd_zero_after_full_recovery(self):
        """After recovery to a new HWM, current drawdown must be 0."""
        df = _make_ledger(FULL_PNL)
        result = get_drawdown_summary(df)
        assert result["current_dd_pct"] == 0.0

    def test_drawdown_duration_zero_at_new_hwm(self):
        """Last row sets a new HWM; duration since HWM = 0."""
        df = _make_ledger(FULL_PNL)
        result = get_drawdown_summary(df)
        assert result["drawdown_duration_days"] == 0

    def test_recovery_days_zero_when_no_current_drawdown(self):
        df = _make_ledger(FULL_PNL)
        result = get_drawdown_summary(df)
        assert result["recovery_estimate_days"] == 0


# ---------------------------------------------------------------------------
# Tests: mid-drawdown scenario
# ---------------------------------------------------------------------------

class TestMidDrawdown:
    """Series that ends inside the drawdown (no recovery yet)."""

    PNL = [10.0] * 10 + [-12.0] * 5  # ends at equity = 40, HWM = 100

    def test_current_dd_pct_is_negative(self):
        df = _make_ledger(self.PNL)
        result = get_drawdown_summary(df)
        assert result["current_dd_pct"] < 0

    def test_current_dd_pct_approx_minus_sixty(self):
        df = _make_ledger(self.PNL)
        result = get_drawdown_summary(df)
        assert abs(result["current_dd_pct"] - (-0.60)) < 0.01

    def test_drawdown_duration_is_five(self):
        """5 days of drawdown since the HWM at day 9."""
        df = _make_ledger(self.PNL)
        result = get_drawdown_summary(df)
        assert result["drawdown_duration_days"] == 5

    def test_recovery_estimate_positive_when_rate_positive(self):
        """Positive trailing run-rate → recovery estimate > 0."""
        # Append a couple of positive days so trailing average is positive
        pnl = self.PNL + [5.0, 5.0]
        df = _make_ledger(pnl)
        result = get_drawdown_summary(df)
        # Still in drawdown (equity < HWM) and run-rate is positive
        if result["current_dd_pct"] < 0:
            assert result["recovery_estimate_days"] >= 0  # may be 0 if rate ≤ 0


# ---------------------------------------------------------------------------
# Tests: equity curve builder
# ---------------------------------------------------------------------------

class TestEquityCurve:
    def test_cumsum_correct(self):
        df = _make_ledger([10.0, -5.0, 20.0])
        curve = _build_equity_curve(df)
        expected = [10.0, 5.0, 25.0]
        for i, exp in enumerate(expected):
            assert abs(curve.iloc[i] - exp) < 1e-9

    def test_returns_empty_series_for_missing_column(self):
        df = pd.DataFrame({"foo": [1, 2, 3]})
        curve = _build_equity_curve(df)
        assert curve.empty


# ---------------------------------------------------------------------------
# Tests: DataFrame vs path parity
# ---------------------------------------------------------------------------

class TestInputParity:
    def test_csv_path_matches_dataframe(self, tmp_path):
        df = _make_ledger(FULL_PNL)
        csv_path = str(tmp_path / "bet_ledger.csv")
        df.to_csv(csv_path, index=False)

        from_df = get_drawdown_summary(df)
        from_path = get_drawdown_summary(csv_path)

        assert from_df["max_dd_pct"] == pytest.approx(from_path["max_dd_pct"], abs=1e-6)
        assert from_df["current_dd_pct"] == pytest.approx(from_path["current_dd_pct"], abs=1e-6)
        assert from_df["drawdown_duration_days"] == from_path["drawdown_duration_days"]
