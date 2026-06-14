"""tests.soccer.test_scoreline_engine — fast synthetic unit tests for the DC scoreline engine.

All OFFLINE (no corpus read, no network).  Correctness anchors:
  A. scoreline_matrix sums to 1.0
  B. rho=0: engine over2.5 == closed-form P(Pois(lam_t)>=3) within 1e-6
  C. DC tau shifts individual low-score cells; sum preserved at 1.0
  D. 1X2 sums to 1.0; BTTS yes+no=1.0; O/U pairs complement
  E. markets_from_matrix has all expected keys
  F. build_engine_forecast returns correct dict shape (patched corpus)
"""
from __future__ import annotations

import math
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from domains.soccer.scoreline_engine import (
    _MAX_GOALS_DEFAULT,
    build_engine_forecast,
    engine_over25,
    markets_from_matrix,
    scoreline_matrix,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _closed_form_over25(lam_h: float, lam_a: float) -> float:
    lam_t = lam_h + lam_a
    return 1.0 - math.exp(-lam_t) * (1.0 + lam_t + lam_t * lam_t / 2.0)


def _make_synthetic_matches() -> pd.DataFrame:
    rows = []
    for k in range(10):
        hg, ag = k % 4, (k + 1) % 3
        rows.append({
            "event_id": f"2023-01-{k+1:02d}-E0-Home-Away",
            "date": pd.Timestamp(f"2023-01-{k+1:02d}"),
            "div": "E0", "season": 2023,
            "home_team": "HomeA", "away_team": "AwayB",
            "fthg": float(hg), "ftag": float(ag),
            "total_goals": float(hg + ag),
            "target_over25": 1.0 if (hg + ag) >= 3 else 0.0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# A. scoreline_matrix sums to 1.0
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam_h,lam_a,rho", [
    (1.3, 1.1, 0.0), (2.5, 0.8, 0.0), (1.0, 1.0, -0.1), (1.5, 1.2, 0.1), (0.5, 3.5, 0.0),
])
def test_matrix_sums_to_one(lam_h, lam_a, rho):
    P = scoreline_matrix(lam_h, lam_a, rho=rho)
    assert P.shape == (_MAX_GOALS_DEFAULT + 1, _MAX_GOALS_DEFAULT + 1)
    assert abs(P.sum() - 1.0) < 1e-10, f"P.sum()={P.sum():.12f}"


# ---------------------------------------------------------------------------
# B. rho=0 engine over2.5 == closed-form baseline within 1e-6
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam_h,lam_a", [
    (1.3, 1.1), (2.0, 0.8), (0.9, 2.1), (1.5, 1.5), (0.3, 0.4),
    # High lambda needs larger max_goals to keep tail truncation < 1e-6
    (3.8, 0.2),
])
def test_rho0_engine_matches_closed_form(lam_h, lam_a):
    """At rho=0, engine over2.5 == closed-form P(Pois(lam_t)>=3) within 1e-6.
    Use max_goals=25 for high-lambda cases where the default 13x13 matrix truncates.
    """
    p_engine = engine_over25(lam_h, lam_a, rho=0.0, max_goals=25)
    p_closed = _closed_form_over25(lam_h, lam_a)
    diff = abs(p_engine - p_closed)
    assert diff < 1e-6, f"Engine {p_engine:.9f} != closed-form {p_closed:.9f} (diff={diff:.2e})"


# ---------------------------------------------------------------------------
# C. DC tau shifts individual low-score cells; sum preserved
# ---------------------------------------------------------------------------

def test_dc_tau_shifts_low_scores_preserves_sum():
    """rho != 0 shifts individual cells (0-0, 1-1) vs independence; both sums = 1.0."""
    lam_h, lam_a = 1.5, 1.2
    P_ind = scoreline_matrix(lam_h, lam_a, rho=0.0)
    P_dc  = scoreline_matrix(lam_h, lam_a, rho=-0.1)

    assert abs(P_ind.sum() - 1.0) < 1e-10
    assert abs(P_dc.sum() - 1.0) < 1e-10

    # rho<0 => tau_00 = 1 - lam_h*lam_a*rho > 1 (inflates 0-0)
    assert P_dc[0, 0] > P_ind[0, 0], "rho<0 should inflate the 0-0 cell"
    # rho<0 => tau_11 = 1 - rho > 1 (inflates 1-1)
    assert P_dc[1, 1] > P_ind[1, 1], "rho<0 should inflate the 1-1 cell"

    # tau_00 != tau_11 in general, so the 0-0/1-1 ratio changes
    ratio_ind = P_ind[0, 0] / P_ind[1, 1]
    ratio_dc  = P_dc[0, 0]  / P_dc[1, 1]
    # tau_00=1.18, tau_11=1.1 => ratio scales by 1.18/1.1 != 1
    assert abs(ratio_dc - ratio_ind) > 1e-6, "DC ratio should differ from independent"


def test_dc_tau_rho_zero_is_independent_poisson():
    """rho=0 => DC is no-op; matrix == renormalised outer product."""
    lam_h, lam_a = 1.4, 1.0
    P = scoreline_matrix(lam_h, lam_a, rho=0.0)
    n = _MAX_GOALS_DEFAULT + 1
    goals = np.arange(n, dtype=float)
    log_fact = np.array([sum(math.log(k) for k in range(1, i+1)) for i in range(n)], dtype=float)
    ph = np.exp(-lam_h + goals * math.log(lam_h) - log_fact)
    pa = np.exp(-lam_a + goals * math.log(lam_a) - log_fact)
    P_exp = np.outer(ph, pa)
    P_exp /= P_exp.sum()
    assert np.allclose(P, P_exp, atol=1e-12)


# ---------------------------------------------------------------------------
# D. 1X2 sums to 1.0; BTTS yes+no=1.0; O/U pairs complement
# ---------------------------------------------------------------------------

def test_markets_1x2_sums_to_one():
    m = markets_from_matrix(scoreline_matrix(1.4, 1.1, rho=0.0))
    assert abs(m["1X2_home"] + m["1X2_draw"] + m["1X2_away"] - 1.0) < 1e-10


def test_markets_btts_sums_to_one():
    m = markets_from_matrix(scoreline_matrix(1.6, 1.0, rho=-0.05))
    assert abs(m["btts_yes"] + m["btts_no"] - 1.0) < 1e-10


def test_markets_over_under_complementary():
    m = markets_from_matrix(scoreline_matrix(1.4, 1.1, rho=0.0))
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        assert abs(m[f"over_{line:g}"] + m[f"under_{line:g}"] - 1.0) < 1e-10


# ---------------------------------------------------------------------------
# E. markets_from_matrix has all expected keys
# ---------------------------------------------------------------------------

def test_markets_all_expected_keys():
    m = markets_from_matrix(scoreline_matrix(1.3, 1.2, rho=0.0))
    required = {"1X2_home", "1X2_draw", "1X2_away", "btts_yes", "btts_no"}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        required |= {f"over_{line:g}", f"under_{line:g}"}
    missing = required - set(m.keys())
    assert not missing, f"Missing: {missing}"
    assert any(k.startswith("cs_") for k in m), "No correct-score keys"


def test_markets_all_probs_in_unit_interval():
    m = markets_from_matrix(scoreline_matrix(1.8, 0.9, rho=-0.08))
    for k, v in m.items():
        if isinstance(v, float):
            assert -1e-10 <= v <= 1.0 + 1e-10, f"{k}={v:.6f} out of [0,1]"


# ---------------------------------------------------------------------------
# F. build_engine_forecast dict shape (patched corpus — no file I/O)
# ---------------------------------------------------------------------------

def test_build_engine_forecast_synthetic():
    synthetic = _make_synthetic_matches()
    with patch("pandas.read_parquet", return_value=synthetic):
        result = build_engine_forecast(rho=0.0, matches_path="fake/path.parquet")

    assert result["n"] > 0
    for forecaster in ("baseline", "engine"):
        for metric in ("brier", "ece", "log_loss"):
            assert metric in result[forecaster]
    assert "dBrier" in result and "dECE" in result and "note" in result
    # At rho=0, engine == baseline numerically
    assert abs(result["dBrier"]) < 1e-5, f"dBrier={result['dBrier']:.8f} should be ~0 at rho=0"
    # sample_surface has the key markets
    sf = result["sample_surface"]
    assert sf is not None and "1X2_home" in sf and "btts_yes" in sf
    assert any(k.startswith("over_") for k in sf)


# ---------------------------------------------------------------------------
# G. Edge cases + sanity checks
# ---------------------------------------------------------------------------

def test_matrix_rejects_non_positive_lambda():
    with pytest.raises(ValueError, match="positive"):
        scoreline_matrix(0.0, 1.0)
    with pytest.raises(ValueError, match="positive"):
        scoreline_matrix(1.0, -0.5)


def test_high_scoring_btts_sanity():
    m = markets_from_matrix(scoreline_matrix(2.5, 2.0, rho=0.0))
    assert m["btts_yes"] > 0.6, f"Expected high BTTS for high lambdas; got {m['btts_yes']:.3f}"


def test_low_scoring_over25_sanity():
    p = engine_over25(0.6, 0.5, rho=0.0)
    assert p < 0.15, f"Expected low over2.5 for defensive match; got {p:.3f}"
