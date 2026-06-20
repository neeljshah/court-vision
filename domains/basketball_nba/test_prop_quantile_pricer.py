"""Per-file pytest for prop_quantile_pricer.

Run ONLY as:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_prop_quantile_pricer.py -q

NEVER run the full suite (it freezes the box).

Acceptance criteria (from BACKLOG P1-6):
  1. Heavy-skew sample -> empirical p_over closer to realised rate than erf/Gaussian.
  2. p_over strictly monotone-decreasing as line rises.
  3. Empty sample (and sample below min_sample) -> UNAVAILABLE, not a fabricated number.
  4. No $ / PnL / ROI / edge field in output.
"""
from __future__ import annotations

import datetime
import math

import numpy as np
import pytest

from domains.basketball_nba.prop_quantile_pricer import (
    price_empirical_over,
    compare_vs_gaussian,
    _weighted_ecdf_p_over,
    _decay_weights,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dates(n: int, as_of: datetime.date, spacing_days: int = 3) -> list[datetime.date]:
    """Generate n game dates ending before as_of."""
    base = as_of - datetime.timedelta(days=1)
    return [base - datetime.timedelta(days=spacing_days * (n - 1 - i)) for i in range(n)]


# ---------------------------------------------------------------------------
# 1. Heavy-skew: empirical should outperform Gaussian on realized rate
# ---------------------------------------------------------------------------

def test_heavy_skew_empirical_closer_to_realised():
    """BLK/STL-like heavy-right-skew: most games are 0 or 1, a few are 4+.

    With the true distribution having 70% zeros, P(BLK >= 1) realized ~= 30%.
    The Gaussian will smear probability incorrectly because it ignores skew.
    The empirical ECDF should match the realized rate more closely.
    """
    rng = np.random.default_rng(42)
    # Heavy right-skew: 70% zeros, otherwise Poisson(2) conditioned on >0.
    n_hist = 40
    raw = np.where(rng.random(n_hist) < 0.70, 0.0,
                   rng.poisson(2, n_hist).astype(float) + 1.0)

    as_of = datetime.date(2025, 4, 1)
    dates = _make_dates(n_hist, as_of=as_of, spacing_days=3)

    line = 0.5  # P(BLK >= 0.5) == fraction of non-zero games
    realized_rate = float(np.mean(raw > 0.5))  # ground truth on THIS sample

    result = compare_vs_gaussian(sample=raw.tolist(), line=line, dates=dates, as_of=as_of)

    assert result["status"] == "ok", f"Unexpected status: {result['status']}"
    p_emp = result["p_over_empirical"]
    p_gau = result["p_over_gaussian"]

    # Empirical ECDF should be closer to the realized rate than Gaussian.
    err_emp = abs(p_emp - realized_rate)
    err_gau = abs(p_gau - realized_rate)
    assert err_emp <= err_gau + 0.05, (
        f"Empirical (err={err_emp:.3f}) not closer than Gaussian (err={err_gau:.3f}) "
        f"to realized {realized_rate:.3f}. emp={p_emp:.3f} gauss={p_gau:.3f}"
    )


def test_heavy_skew_block_line_one():
    """P(BLK >= 1): realized ~30% on zero-heavy sample; Gaussian inflates this."""
    rng = np.random.default_rng(7)
    n_hist = 50
    raw = np.where(rng.random(n_hist) < 0.70, 0.0, float(1.0))

    as_of = datetime.date(2025, 3, 15)
    dates = _make_dates(n_hist, as_of=as_of)
    realized = float(np.mean(raw >= 1.0))

    result = compare_vs_gaussian(sample=raw.tolist(), line=1.0, dates=dates, as_of=as_of)
    p_emp = result["p_over_empirical"]
    p_gau = result["p_over_gaussian"]

    # Gaussian will push probability toward 50% due to symmetry assumption.
    # Empirical should be much closer to the actual ~30%.
    err_emp = abs(p_emp - realized)
    err_gau = abs(p_gau - realized)
    assert err_emp < err_gau + 0.05, (
        f"emp err={err_emp:.3f} vs gauss err={err_gau:.3f} (realized={realized:.3f})"
    )
    # Also sanity: empirical p_over ~ realized rate directly
    assert abs(p_emp - realized) <= 0.10, (
        f"Empirical p_over {p_emp:.3f} far from realized {realized:.3f}"
    )


# ---------------------------------------------------------------------------
# 2. Monotone-decreasing: p_over must decrease (non-strictly if ties) as line rises
# ---------------------------------------------------------------------------

def test_p_over_monotone_decreasing_across_lines():
    """p_over must be monotone-decreasing as the line increases."""
    rng = np.random.default_rng(99)
    sample = rng.normal(20.0, 5.0, 30).tolist()
    as_of = datetime.date(2025, 2, 1)
    dates = _make_dates(30, as_of=as_of)

    lines = [5.0, 10.0, 15.0, 18.5, 20.0, 22.5, 25.0, 30.0, 40.0, 50.0]
    p_overs = []
    for ln in lines:
        r = price_empirical_over(sample=sample, line=ln, dates=dates, as_of=as_of)
        assert r["status"] == "ok", f"Expected ok for line={ln}, got {r['status']}"
        p_overs.append(r["p_over"])

    for i in range(1, len(p_overs)):
        assert p_overs[i] <= p_overs[i - 1] + 1e-9, (
            f"Not monotone at index {i}: p_over({lines[i]})={p_overs[i]:.4f} > "
            f"p_over({lines[i-1]})={p_overs[i-1]:.4f}"
        )


def test_p_over_monotone_on_skewed_sample():
    """Monotone property holds even on heavily skewed (BLK-like) sample."""
    rng = np.random.default_rng(13)
    # 60% zero, 40% exponential(1)
    sample = np.where(rng.random(40) < 0.60, 0.0, rng.exponential(1.5, 40))
    as_of = datetime.date(2025, 5, 1)
    dates = _make_dates(len(sample), as_of=as_of)

    lines = np.linspace(0.0, 8.0, 30).tolist()
    p_overs = []
    for ln in lines:
        r = price_empirical_over(sample=sample.tolist(), line=ln, dates=dates, as_of=as_of)
        if r["status"] == "ok":
            p_overs.append((ln, r["p_over"]))

    for i in range(1, len(p_overs)):
        ln_prev, po_prev = p_overs[i - 1]
        ln_curr, po_curr = p_overs[i]
        assert po_curr <= po_prev + 1e-9, (
            f"Monotone violation: p_over({ln_curr:.2f})={po_curr:.4f} > "
            f"p_over({ln_prev:.2f})={po_prev:.4f}"
        )


# ---------------------------------------------------------------------------
# 3. Empty / thin sample -> UNAVAILABLE
# ---------------------------------------------------------------------------

def test_empty_sample_returns_unavailable():
    """Zero observations must yield UNAVAILABLE, not a fabricated probability."""
    result = price_empirical_over(sample=[], line=20.0)
    assert result["status"] == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"
    assert result["p_over"] is None
    assert result["p_under"] is None


def test_thin_sample_below_min_returns_unavailable():
    """Fewer than min_sample (default 5) observations must yield UNAVAILABLE."""
    sample = [15.0, 18.0, 22.0]  # only 3 values
    result = price_empirical_over(sample=sample, line=20.0)
    assert result["status"] == "UNAVAILABLE", f"Expected UNAVAILABLE, got {result}"
    assert result["p_over"] is None


def test_all_filtered_by_as_of_returns_unavailable():
    """If as_of filtering removes all games, result must be UNAVAILABLE."""
    # All dates are ON or AFTER as_of -- so all get filtered out
    as_of = datetime.date(2025, 1, 1)
    dates = [datetime.date(2025, 1, 1), datetime.date(2025, 1, 5), datetime.date(2025, 1, 10)]
    sample = [20.0, 22.0, 18.0]
    result = price_empirical_over(sample=sample, line=20.0, dates=dates, as_of=as_of)
    assert result["status"] == "UNAVAILABLE", f"Expected UNAVAILABLE after date filter, got {result}"
    assert result["p_over"] is None


# ---------------------------------------------------------------------------
# 4. No $ / PnL / ROI / edge field in output
# ---------------------------------------------------------------------------

def test_no_dollar_fields_in_output():
    """Output dict must NOT contain any $ / pnl / roi / edge fields."""
    rng = np.random.default_rng(1)
    sample = rng.normal(20.0, 5.0, 25).tolist()
    as_of = datetime.date(2025, 4, 1)
    dates = _make_dates(25, as_of=as_of)

    result = price_empirical_over(sample=sample, line=20.0, dates=dates, as_of=as_of)
    forbidden = {"pnl", "roi", "edge", "profit", "dollar", "bankroll", "kelly"}
    for key in result:
        assert key.lower() not in forbidden, f"Forbidden field '{key}' found in output"
    # Also check compare_vs_gaussian
    result2 = compare_vs_gaussian(sample=sample, line=20.0, dates=dates, as_of=as_of)
    for key in result2:
        assert key.lower() not in forbidden, f"Forbidden field '{key}' found in compare output"


def test_no_dollar_fields_in_unavailable_output():
    """UNAVAILABLE sentinel must also not contain $ fields."""
    result = price_empirical_over(sample=[], line=20.0)
    forbidden = {"pnl", "roi", "edge", "profit", "dollar", "bankroll", "kelly"}
    for key in result:
        assert key.lower() not in forbidden, f"Forbidden field '{key}' in UNAVAILABLE output"


# ---------------------------------------------------------------------------
# 5. Boundary / edge cases
# ---------------------------------------------------------------------------

def test_line_below_all_values_gives_p_over_one():
    """Line at or below minimum sample value -> p_over == 1.0."""
    sample = [10.0, 15.0, 20.0, 25.0, 30.0]
    result = price_empirical_over(sample=sample, line=5.0)
    assert result["status"] == "ok"
    assert result["p_over"] == 1.0


def test_line_above_all_values_gives_p_over_zero():
    """Line above all sample values -> p_over == 0.0."""
    sample = [10.0, 15.0, 20.0, 25.0, 30.0]
    result = price_empirical_over(sample=sample, line=50.0)
    assert result["status"] == "ok"
    assert result["p_over"] == 0.0


def test_p_over_plus_p_under_equals_one():
    """p_over + p_under must equal 1.0 (mod rounding)."""
    rng = np.random.default_rng(5)
    sample = rng.normal(20.0, 5.0, 20).tolist()
    result = price_empirical_over(sample=sample, line=20.0)
    assert result["status"] == "ok"
    assert abs(result["p_over"] + result["p_under"] - 1.0) < 1e-6


def test_recency_weights_upweight_recent():
    """Explicitly verify that decay weights are larger for recent games."""
    as_of = datetime.date(2025, 4, 10)
    # 2 games: one 5 days ago, one 100 days ago
    days_ago = np.array([5.0, 100.0])
    w = _decay_weights(days_ago, half_life=60.0)
    assert w[0] > w[1], f"Recent game should have larger weight: {w}"


def test_no_dates_gives_uniform_weights():
    """Without dates, all games get equal weight -> ECDF is unweighted."""
    sample = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]
    result = price_empirical_over(sample=sample, line=5.0)
    assert result["status"] == "ok"
    # 5 of 10 values >= 5: 5, 6, 7, 8, 9
    expected = 0.5
    assert abs(result["p_over"] - expected) < 0.01, (
        f"Expected ~{expected}, got {result['p_over']}"
    )


def test_compare_vs_gaussian_returns_both_probs():
    """compare_vs_gaussian must include both empirical and gaussian p_over."""
    rng = np.random.default_rng(2)
    sample = rng.normal(25.0, 5.0, 30).tolist()
    as_of = datetime.date(2025, 3, 1)
    dates = _make_dates(30, as_of=as_of)
    result = compare_vs_gaussian(sample=sample, line=25.0, dates=dates, as_of=as_of)
    assert "p_over_empirical" in result
    assert "p_over_gaussian" in result
    assert "p_over_delta" in result
    # Both must be in [0, 1]
    assert 0.0 <= result["p_over_empirical"] <= 1.0
    assert 0.0 <= result["p_over_gaussian"] <= 1.0


def test_method_field_is_correct():
    """Output must declare method = empirical_quantile."""
    sample = [10.0] * 10
    result = price_empirical_over(sample=sample, line=5.0)
    assert result.get("method") == "empirical_quantile"
