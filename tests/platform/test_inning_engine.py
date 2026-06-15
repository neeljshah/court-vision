"""tests/platform/test_inning_engine.py

Unit tests for domains.mlb.inning_engine (independent-Poisson runs engine).
All tests: accuracy/calibration/coherence only. NO edge claimed; gate decides.

Run: python -m pytest tests/platform/test_inning_engine.py -q
"""
from __future__ import annotations

import pytest

from domains.mlb.inning_engine import (
    _TOTAL_LINES,
    anchor_lambdas_to_winprob,
    markets_from_matrix,
    runs_matrix,
)


# 1. Joint runs matrix PMF sums to ~1 (truncation-renormalised)
@pytest.mark.parametrize("lam_h,lam_a", [
    (4.5, 4.0), (4.0, 4.0), (0.5, 0.5), (10.0, 2.0), (6.2, 5.8),
])
def test_runs_matrix_sums_to_one(lam_h, lam_a):
    P = runs_matrix(lam_h, lam_a)
    assert abs(P.sum() - 1.0) < 1e-9, f"PMF sum={P.sum():.10f} for lam=({lam_h},{lam_a})"


def test_runs_matrix_rejects_nonpositive():
    with pytest.raises(ValueError):
        runs_matrix(0.0, 4.0)
    with pytest.raises(ValueError):
        runs_matrix(4.0, -1.0)


# 2. Moneyline is complementary: ml_home + ml_away ~= 1.0
@pytest.mark.parametrize("lam_h,lam_a", [
    (4.5, 4.0), (4.0, 4.0), (10.0, 2.0), (3.0, 6.0),
])
def test_ml_complementary(lam_h, lam_a):
    m = markets_from_matrix(runs_matrix(lam_h, lam_a))
    assert abs(m["ml_home"] + m["ml_away"] - 1.0) < 1e-9


def test_run_line_complementary():
    m = markets_from_matrix(runs_matrix(4.5, 4.0))
    assert abs(m["rl_home_minus15"] + m["rl_away_plus15"] - 1.0) < 1e-9


# 3. Over/Under monotonicity across the total lines (6.5..10.5)
def test_over_under_complementary():
    m = markets_from_matrix(runs_matrix(4.5, 4.0))
    for line in _TOTAL_LINES:
        s = m[f"over_{line:g}"] + m[f"under_{line:g}"]
        assert abs(s - 1.0) < 1e-9


def test_over_monotone_decreasing():
    m = markets_from_matrix(runs_matrix(4.5, 4.0))
    overs = [m[f"over_{line:g}"] for line in _TOTAL_LINES]
    for a, b in zip(overs, overs[1:]):
        assert b <= a + 1e-12, f"over not monotone decreasing: {overs}"
    for p in overs:
        assert 0.0 <= p <= 1.0


def test_under_monotone_increasing():
    m = markets_from_matrix(runs_matrix(4.5, 4.0))
    unders = [m[f"under_{line:g}"] for line in _TOTAL_LINES]
    for a, b in zip(unders, unders[1:]):
        assert b >= a - 1e-12, f"under not monotone increasing: {unders}"


# 4. Elo-anchor: SUM preserved exactly, ML driven to the target win prob
@pytest.mark.parametrize("target", [0.40, 0.50, 0.60, 0.70])
def test_anchor_preserves_lambda_sum(target):
    lam_h, lam_a = 4.0, 4.0
    lh, la = anchor_lambdas_to_winprob(lam_h, lam_a, target)
    assert abs((lh + la) - (lam_h + lam_a)) < 1e-9


@pytest.mark.parametrize("target", [0.40, 0.50, 0.60, 0.70])
def test_anchor_drives_ml_to_target(target):
    lh, la = anchor_lambdas_to_winprob(4.0, 4.0, target)
    ml = markets_from_matrix(runs_matrix(lh, la))["ml_home"]
    assert abs(ml - target) < 1e-3


def test_anchor_noop_when_already_at_target():
    lh, la = anchor_lambdas_to_winprob(4.0, 4.0, 0.5)
    assert (lh, la) == (4.0, 4.0)


def test_anchor_rejects_degenerate_target():
    with pytest.raises(ValueError):
        anchor_lambdas_to_winprob(4.0, 4.0, 0.0)
    with pytest.raises(ValueError):
        anchor_lambdas_to_winprob(4.0, 4.0, 1.0)


# 5. F5 surface appears only when first-5 lambdas are supplied
def test_f5_surface_optional():
    P = runs_matrix(4.5, 4.0)
    plain = markets_from_matrix(P)
    assert not any(k.startswith("f5_") for k in plain)
    with_f5 = markets_from_matrix(P, f5_lam_home=2.5, f5_lam_away=2.2)
    assert abs(with_f5["f5_ml_home"] + with_f5["f5_ml_away"] - 1.0) < 1e-9
    assert abs(with_f5["f5_over_4.5"] + with_f5["f5_under_4.5"] - 1.0) < 1e-9
