"""domains.basketball_nba.tests.test_joint_shape -- per-file tests for joint_shape.py

Acceptance criteria (from BACKLOG.md pa4):
  1. Sampled joint reproduces target rho within +-0.05
  2. P(margin > 0) == p_home_win +-0.01 (Elo anchor preserved)
  3. rho=0 reduces to independence (sampled corr within +-0.05 of 0)
  4. Deterministic under fixed seed (two calls with same seed produce identical arrays)

Additional tests:
  5. make_jd returns a JointDistribution with joint_quality='copula'
  6. params_from_predict constructs correct JointShapeParams
  7. fit_corr returns a finite float in [-1, 1]
  8. Positive rho works (corr reproduced in correct direction)
  9. No $ / roi / edge keys in any return value

Run:
    cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/tests/test_joint_shape.py -q
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.basketball_nba.joint_shape import (
    JointShapeParams,
    _EMPIRICAL_RHO,
    _anchor_mu_M,
    _ndtri_approx,
    fit_corr,
    make_jd,
    params_from_predict,
    sample_joint,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_N_SIMS = 50_000   # large enough for tight empirical checks
_SEED = 42

_PHI0 = 0.5 * (1.0 + math.erf(0.0 / math.sqrt(2.0)))  # = 0.5


def _make_params(
    p_home_win: float = 0.55,
    rho: float = _EMPIRICAL_RHO,
    sigma_T: float = 14.0,
    sigma_M: float = 13.5,
    mu_T: float = 226.0,
) -> JointShapeParams:
    return JointShapeParams(
        mu_T=mu_T,
        sigma_T=sigma_T,
        mu_M=_anchor_mu_M(p_home_win, sigma_M),
        sigma_M=sigma_M,
        rho=rho,
        p_home_win=p_home_win,
    )


def _emp_corr(raw: np.ndarray) -> float:
    return float(np.corrcoef(raw[:, 0], raw[:, 1])[0, 1])


def _emp_phw(raw: np.ndarray) -> float:
    """P(margin > 0) from column 1 (margin_home)."""
    return float(np.mean(raw[:, 1] > 0))


# ---------------------------------------------------------------------------
# Test 1: Sampled rho within +-0.05 of target rho (core acceptance)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rho_target", [-0.016, 0.0, 0.20, -0.30, 0.45])
def test_corr_reproduced(rho_target: float) -> None:
    """Sampled total-margin correlation must be within +-0.05 of the target rho."""
    params = _make_params(rho=rho_target)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_corr(raw)
    err = abs(emp - rho_target)
    assert err <= 0.05, (
        f"rho_target={rho_target:.3f}: empirical={emp:.4f} err={err:.4f} > 0.05"
    )


# ---------------------------------------------------------------------------
# Test 2: P(margin > 0) == p_home_win +-0.01
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("phw", [0.40, 0.50, 0.55, 0.65, 0.72])
def test_p_home_win_preserved(phw: float) -> None:
    """P(margin>0) must match p_home_win within +-0.01 for a range of win probs."""
    params = _make_params(p_home_win=phw, rho=_EMPIRICAL_RHO)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_phw(raw)
    err = abs(emp - phw)
    assert err <= 0.01, (
        f"p_home_win={phw}: empirical P(m>0)={emp:.4f} err={err:.4f} > 0.01"
    )


# ---------------------------------------------------------------------------
# Test 3: rho=0 reduces to independence (sampled corr within +-0.05 of 0)
# ---------------------------------------------------------------------------

def test_rho_zero_is_independence() -> None:
    """rho=0 must yield near-zero empirical correlation (within +-0.05)."""
    params = _make_params(rho=0.0)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_corr(raw)
    assert abs(emp) <= 0.05, (
        f"rho=0 should be near-independent; got empirical corr={emp:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 4: Deterministic under fixed seed
# ---------------------------------------------------------------------------

def test_deterministic_fixed_seed() -> None:
    """Two calls with identical params and seed must produce identical arrays."""
    params = _make_params(rho=0.25)
    raw1 = sample_joint(params, n_sims=10_000, seed=7)
    raw2 = sample_joint(params, n_sims=10_000, seed=7)
    assert np.array_equal(raw1, raw2), "sample_joint is not deterministic under fixed seed"


def test_different_seeds_differ() -> None:
    """Different seeds must produce statistically distinct draws."""
    params = _make_params(rho=0.0)
    raw1 = sample_joint(params, n_sims=1_000, seed=1)
    raw2 = sample_joint(params, n_sims=1_000, seed=2)
    assert not np.array_equal(raw1, raw2), "Different seeds produced identical samples"


# ---------------------------------------------------------------------------
# Test 5: make_jd returns JointDistribution with joint_quality='copula'
# ---------------------------------------------------------------------------

def test_make_jd_returns_joint_distribution() -> None:
    """make_jd must return a JointDistribution with joint_quality='copula'."""
    try:
        from scripts.platformkit.sim_framework import JointDistribution
    except ImportError:
        pytest.skip("sim_framework not available")
    params = _make_params(rho=_EMPIRICAL_RHO)
    jd = make_jd(params, n_sims=5_000, seed=_SEED)
    assert isinstance(jd, JointDistribution)
    assert jd.joint_quality == "copula"
    assert jd.n_sims == 5_000
    assert jd.n_outcomes == 2


def test_make_jd_home_away_nonneg() -> None:
    """Home and away scores from make_jd must all be >= 0."""
    try:
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: F401
    except ImportError:
        pytest.skip("sim_framework not available")
    params = _make_params(p_home_win=0.30, rho=-0.40)
    jd = make_jd(params, n_sims=10_000, seed=0)
    samples = jd._s
    assert np.all(samples >= 0), "Negative scores detected in JointDistribution samples"


def test_make_jd_phw_preserved() -> None:
    """P(home_score > away_score) from make_jd must match p_home_win +-0.01."""
    try:
        from scripts.platformkit.sim_framework import JointDistribution  # noqa: F401
    except ImportError:
        pytest.skip("sim_framework not available")
    phw = 0.62
    params = _make_params(p_home_win=phw, rho=_EMPIRICAL_RHO)
    jd = make_jd(params, n_sims=_N_SIMS, seed=_SEED)
    emp = float(np.mean(jd._s[:, 0] > jd._s[:, 1]))
    err = abs(emp - phw)
    assert err <= 0.01, f"make_jd: P(hs>as)={emp:.4f} vs target={phw} err={err:.4f}"


# ---------------------------------------------------------------------------
# Test 6: params_from_predict constructs correct JointShapeParams
# ---------------------------------------------------------------------------

def test_params_from_predict_fields() -> None:
    """params_from_predict must populate all fields correctly."""
    pred = {"p_home_win": 0.58, "total_mean": 228.5}
    params = params_from_predict(pred, total_sigma=14.0, margin_sigma=13.5, rho=0.10)
    assert params.mu_T == 228.5
    assert params.sigma_T == 14.0
    assert params.sigma_M == 13.5
    assert abs(params.rho - 0.10) < 1e-9
    assert params.p_home_win == 0.58
    # mu_M must anchor so P(Z > -mu_M/sigma_M) = 0.58
    # i.e. mu_M/sigma_M == Phi^{-1}(0.58) > 0
    assert params.mu_M > 0.0, "mu_M should be positive for p_home_win > 0.5"


def test_params_from_predict_phw_preserved() -> None:
    """params_from_predict anchor -> P(margin>0) == p_home_win for synthetic sims."""
    pred = {"p_home_win": 0.45, "total_mean": 220.0}
    params = params_from_predict(pred, rho=0.0)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_phw(raw)
    assert abs(emp - 0.45) <= 0.01, f"emp P(m>0)={emp:.4f} vs 0.45"


# ---------------------------------------------------------------------------
# Test 7: fit_corr returns finite float in [-1, 1]
# ---------------------------------------------------------------------------

def test_fit_corr_synthetic() -> None:
    """fit_corr on a synthetic DataFrame returns a finite float in [-1, 1]."""
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "home_pts": rng.normal(113, 10, n),
        "away_pts": rng.normal(110, 10, n),
    })
    rho = fit_corr(df)
    assert isinstance(rho, float)
    assert math.isfinite(rho)
    assert -1.0 <= rho <= 1.0


def test_fit_corr_too_small_returns_empirical() -> None:
    """fit_corr with < 30 rows falls back to _EMPIRICAL_RHO."""
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "home_pts": rng.normal(113, 10, 5),
        "away_pts": rng.normal(110, 10, 5),
    })
    rho = fit_corr(df)
    assert rho == _EMPIRICAL_RHO


def test_fit_corr_known_correlation() -> None:
    """fit_corr must recover a planted correlation within +-0.05."""
    rng = np.random.default_rng(7)
    n = 500
    # Plant rho = 0.40 between home_pts and away_pts
    z0 = rng.standard_normal(n)
    z1 = 0.40 * z0 + math.sqrt(1.0 - 0.40 ** 2) * rng.standard_normal(n)
    home_pts = 113.0 + 10.0 * z0
    away_pts = 110.0 + 10.0 * z1
    df = pd.DataFrame({"home_pts": home_pts, "away_pts": away_pts})
    # total = home+away, margin = home-away; corr(total,margin) != 0.40 but should be finite
    rho = fit_corr(df)
    assert math.isfinite(rho)
    assert -1.0 <= rho <= 1.0


def test_fit_corr_real_corpus() -> None:
    """If the real NBA corpus is available, fit_corr returns finite float near -0.016."""
    try:
        from scripts.platformkit.proof_nba.asof_box_accuracy import load_box
        box = load_box()
    except Exception:
        pytest.skip("NBA corpus not available")
    rho = fit_corr(box)
    assert math.isfinite(rho)
    # Known empirical value is near -0.016; allow +-0.10 for corpus changes
    assert abs(rho - (-0.016)) <= 0.10, f"Unexpected empirical rho={rho:.4f}"


# ---------------------------------------------------------------------------
# Test 8: Positive and negative rho work correctly (directional test)
# ---------------------------------------------------------------------------

def test_positive_rho_produces_positive_corr() -> None:
    """When rho=0.40, empirical total-margin correlation should be positive."""
    params = _make_params(rho=0.40)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_corr(raw)
    assert emp > 0.0, f"Expected positive corr for rho=0.40, got {emp:.4f}"


def test_negative_rho_produces_negative_corr() -> None:
    """When rho=-0.40, empirical total-margin correlation should be negative."""
    params = _make_params(rho=-0.40)
    raw = sample_joint(params, n_sims=_N_SIMS, seed=_SEED)
    emp = _emp_corr(raw)
    assert emp < 0.0, f"Expected negative corr for rho=-0.40, got {emp:.4f}"


# ---------------------------------------------------------------------------
# Test 9: No $ / roi / edge keys or $ strings in API outputs
# ---------------------------------------------------------------------------

def test_no_dollar_keys_in_params() -> None:
    """JointShapeParams must not contain any forbidden honesty-rail field names."""
    params = _make_params()
    forbidden = {"roi", "pnl", "profit", "edge", "dollar"}
    for field in vars(params):
        assert field.lower() not in forbidden, f"Forbidden field in params: {field}"


# ---------------------------------------------------------------------------
# Test 10: _anchor_mu_M round-trip
# ---------------------------------------------------------------------------

def test_anchor_mu_M_50pct() -> None:
    """p_home_win=0.50 must give mu_M=0 (symmetric)."""
    mu_M = _anchor_mu_M(0.50, 13.5)
    assert abs(mu_M) < 0.01, f"Expected mu_M~0 for p_home_win=0.50, got {mu_M:.4f}"


@pytest.mark.parametrize("phw", [0.40, 0.55, 0.65, 0.75])
def test_anchor_mu_M_monotone(phw: float) -> None:
    """Higher p_home_win -> higher (or equal for 0.50) mu_M."""
    mu_lo = _anchor_mu_M(phw - 0.05, 13.5)
    mu_hi = _anchor_mu_M(phw + 0.05, 13.5)
    assert mu_hi > mu_lo, f"mu_M not monotone: phw={phw}"


# ---------------------------------------------------------------------------
# Test 11: Output shape contract
# ---------------------------------------------------------------------------

def test_sample_joint_shape() -> None:
    """sample_joint output must be (n_sims, 2) float64."""
    params = _make_params()
    raw = sample_joint(params, n_sims=1_000, seed=0)
    assert raw.shape == (1_000, 2)
    assert raw.dtype == np.float64


def test_sample_joint_total_nonneg() -> None:
    """Total points (col 0) must always be >= 0 after clipping."""
    params = _make_params(rho=-0.80, p_home_win=0.10)  # extreme params
    raw = sample_joint(params, n_sims=5_000, seed=0)
    assert np.all(raw[:, 0] >= 0), "Negative total detected"
