"""Smoke tests for the VaR / CVaR daily risk reporter."""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from src.prediction.risk_reporter import build_report, _compute_var_cvar


# ── Unit: core metrics ────────────────────────────────────────────────────────

def test_var_cvar_smoke():
    """Feed a synthetic 60-day P&L series; VaR values must be non-zero and finite."""
    rng = np.random.default_rng(42)
    pnl = rng.normal(loc=5.0, scale=50.0, size=60)

    result = _compute_var_cvar(pnl)

    for key in ("parametric_var_95", "historical_var_95", "cvar_95", "expected_shortfall_95"):
        val = result[key]
        assert math.isfinite(val), f"{key} must be finite, got {val}"
        assert val != 0.0, f"{key} must be non-zero"

    assert result["n_observations"] == 60


def test_var_ordering():
    """CVaR must be >= historical VaR (CVaR is a tail mean, VaR is a percentile)."""
    rng = np.random.default_rng(7)
    pnl = rng.normal(0, 100, size=120)
    result = _compute_var_cvar(pnl)
    assert result["cvar_95"] >= result["historical_var_95"], (
        "CVaR should be at least as large as VaR (deeper tail)"
    )


def test_empty_series_returns_nan():
    """An empty P&L array must not raise and must return NaN for all metrics."""
    result = _compute_var_cvar(np.array([], dtype=float))
    assert result["n_observations"] == 0
    for key in ("parametric_var_95", "historical_var_95", "cvar_95"):
        assert math.isnan(result[key]), f"{key} should be NaN for empty input"


# ── Integration: build_report ─────────────────────────────────────────────────

def _synthetic_ledger(n: int = 60) -> pd.DataFrame:
    dates = pd.date_range(end="2026-05-21", periods=n, freq="D")
    rng = np.random.default_rng(0)
    return pd.DataFrame({"date": dates, "pnl": rng.normal(10.0, 40.0, size=n)})


def test_build_report_from_dataframe(tmp_path, monkeypatch):
    """build_report should write a JSON file and return a valid dict."""
    from src.prediction import risk_reporter as rr
    monkeypatch.setattr(rr, "RISK_DIR", tmp_path / "risk")

    df = _synthetic_ledger(60)
    report = build_report(df=df, report_date=date(2026, 5, 21))

    # JSON file must have been written
    out = tmp_path / "risk" / "risk_20260521.json"
    assert out.exists(), "report JSON was not written"

    # Return dict must contain expected keys with finite, non-zero values
    for key in ("parametric_var_95", "historical_var_95", "cvar_95", "expected_shortfall_95"):
        val = report[key]
        assert math.isfinite(val), f"{key} must be finite"
        assert val != 0.0, f"{key} must be non-zero"


def test_build_report_missing_ledger(tmp_path, monkeypatch):
    """build_report must NOT crash when the ledger CSV is absent."""
    from src.prediction import risk_reporter as rr
    monkeypatch.setattr(rr, "RISK_DIR", tmp_path / "risk")
    # Point to a non-existent file
    absent = tmp_path / "bet_ledger.csv"
    report = build_report(ledger=absent, report_date=date(2026, 5, 21))
    # Should return a report with n_observations == 0
    assert report["n_observations"] == 0


def test_build_report_ledger_path(tmp_path, monkeypatch):
    """build_report should accept a Path to a real CSV ledger."""
    from src.prediction import risk_reporter as rr
    monkeypatch.setattr(rr, "RISK_DIR", tmp_path / "risk")

    df = _synthetic_ledger(60)
    ledger_path = tmp_path / "bet_ledger.csv"
    df.to_csv(ledger_path, index=False)

    report = build_report(ledger=ledger_path, report_date=date(2026, 5, 21))
    assert report["n_observations"] > 0
    assert math.isfinite(report["historical_var_95"])
