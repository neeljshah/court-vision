"""tests/platform/test_negbinom_engine.py

Unit tests for domains.mlb.negbinom_engine.
All tests: accuracy/calibration only. NO edge claims.

Run: python -m pytest tests/platform/test_negbinom_engine.py -q
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from domains.mlb.negbinom_engine import (
    _negbinom_pmf,
    _poisson_pmf,
    _tail_coverage,
    brier_score,
    fit_dispersion_first_half,
    fit_r_mom,
    markets_from_matrix_nb,
    run_validation,
    runs_matrix_nb,
    runs_matrix_poisson,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GAMES_PATH = _REPO_ROOT / "data" / "domains" / "mlb" / "games.parquet"
_SKIP_DATA = not _GAMES_PATH.exists()


# ---------------------------------------------------------------------------
# 1. NegBinom PMF sums to 1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("lam,r", [
    (4.0, 4.0), (4.5, 3.5), (0.5, 1.0), (10.0, 2.0),
])
def test_negbinom_pmf_sums_to_one(lam, r):
    pmf = _negbinom_pmf(lam, r, max_k=50)
    # After renormalization the truncated sum must be exactly 1
    assert abs(pmf.sum() - 1.0) < 1e-9, f"PMF sum={pmf.sum():.8f} for lam={lam}, r={r}"


# ---------------------------------------------------------------------------
# 2. Joint matrix sums to 1
# ---------------------------------------------------------------------------

def test_runs_matrix_nb_sums_to_one():
    P = runs_matrix_nb(4.0, 4.5, 4.0, 3.5)
    assert abs(P.sum() - 1.0) < 1e-9


def test_runs_matrix_poisson_sums_to_one():
    P = runs_matrix_poisson(4.0, 4.5)
    assert abs(P.sum() - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 3. Same mean as Poisson — large r → NegBinom ≈ Poisson
# ---------------------------------------------------------------------------

def test_same_mean_as_poisson():
    """NegBinom with very large r should match Poisson O/U probs closely."""
    lam_h, lam_a = 4.5, 4.2
    r_large = 1e5  # ~Poisson limit

    P_nb = runs_matrix_nb(lam_h, lam_a, r_large, r_large)
    P_po = runs_matrix_poisson(lam_h, lam_a)

    mkts_nb = markets_from_matrix_nb(P_nb)
    mkts_po = markets_from_matrix_nb(P_po)

    for key in ["over_8.5", "over_7.5", "ml_home"]:
        diff = abs(mkts_nb[key] - mkts_po[key])
        assert diff < 0.01, (
            f"{key}: NB(r=1e5)={mkts_nb[key]:.4f}, Poisson={mkts_po[key]:.4f}, diff={diff:.4f}"
        )


# ---------------------------------------------------------------------------
# 4. NegBinom has higher tail probabilities than Poisson (over-dispersion)
# ---------------------------------------------------------------------------

def test_higher_tail_probability_than_poisson():
    """NegBinom with r≈4 must put more mass in the high tail than Poisson."""
    lam_h, lam_a = 4.5, 4.2
    r_realistic = 4.0

    P_nb = runs_matrix_nb(lam_h, lam_a, r_realistic, r_realistic)
    P_po = runs_matrix_poisson(lam_h, lam_a)

    mkts_nb = markets_from_matrix_nb(P_nb)
    mkts_po = markets_from_matrix_nb(P_po)

    # Over 10.5 should be meaningfully higher for NegBinom
    nb_over = mkts_nb["over_10.5"]
    po_over = mkts_po["over_10.5"]
    assert nb_over > po_over, (
        f"NegBinom should have higher P(over 10.5): NB={nb_over:.4f}, Poisson={po_over:.4f}"
    )


def test_higher_variance_than_poisson():
    """NegBinom marginal PMF variance must exceed Poisson variance (same mean)."""
    lam, r = 4.5, 4.0
    pmf_nb = _negbinom_pmf(lam, r, max_k=50)
    pmf_po = _poisson_pmf(lam, 50)

    k = np.arange(51)
    mean_nb = (k * pmf_nb).sum()
    var_nb = (k ** 2 * pmf_nb).sum() - mean_nb ** 2
    mean_po = (k * pmf_po).sum()
    var_po = (k ** 2 * pmf_po).sum() - mean_po ** 2

    assert abs(mean_nb - mean_po) < 0.05, f"Means differ: {mean_nb:.4f} vs {mean_po:.4f}"
    assert var_nb > var_po, f"NB var={var_nb:.4f} should exceed Poisson var={var_po:.4f}"


# ---------------------------------------------------------------------------
# 5. Method of Moments dispersion fitting
# ---------------------------------------------------------------------------

def test_fit_r_mom_basic():
    """MoM r estimate with known over-dispersed data."""
    rng = np.random.default_rng(42)
    from scipy.stats import nbinom
    true_r, true_mu = 4.0, 4.5
    p = true_r / (true_r + true_mu)
    samples = nbinom.rvs(n=true_r, p=p, size=5000, random_state=42)
    r_hat = fit_r_mom(samples)
    # Should be in the ballpark (within 50% of truth for large n)
    assert 2.0 < r_hat < 8.0, f"r_hat={r_hat:.2f} out of expected range [2, 8]"


def test_fit_r_mom_poisson_fallback():
    """When variance≈mean (Poisson data), r_mom returns _MIN_R (doesn't crash)."""
    rng = np.random.default_rng(42)
    from scipy.stats import poisson
    samples = poisson.rvs(mu=4.5, size=1000, random_state=42)
    r = fit_r_mom(samples)
    assert r >= 0.5, f"r should be >= MIN_R but got {r}"


def test_fit_r_mom_small_sample():
    """Fewer than 10 observations returns FALLBACK_R, not a crash."""
    from domains.mlb.negbinom_engine import _FALLBACK_R
    r = fit_r_mom(np.array([3.0, 5.0, 2.0]))
    assert r == _FALLBACK_R


# ---------------------------------------------------------------------------
# 6. No future data leak in dispersion estimate
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP_DATA, reason="games.parquet not found")
def test_no_future_leak():
    """Dispersion is fitted on first 50% — val indices must all be >= n_train."""
    import pandas as pd
    df = pd.read_parquet(_GAMES_PATH).sort_values("date").reset_index(drop=True)
    _, _, n_train = fit_dispersion_first_half(df)
    # n_train must be the midpoint
    assert n_train == len(df) // 2, f"n_train={n_train} != mid={len(df)//2}"
    # Any game at index < n_train was IN the training set → game at n_train is first val game
    val_start = n_train
    assert val_start <= len(df), "val start out of bounds"
    # Verify dates: all train dates must be ≤ first val date
    train_end_date = df["date"].iloc[n_train - 1]
    val_start_date = df["date"].iloc[n_train]
    assert train_end_date <= val_start_date, (
        f"Date leak: train end {train_end_date} > val start {val_start_date}"
    )


# ---------------------------------------------------------------------------
# 7. Run-line probabilities sum to ~1
# ---------------------------------------------------------------------------

def test_run_line_probabilities_sum():
    """P(home wins by 2+) + P(home wins by 1 or tie or away wins by 1) + P(away wins by 2+) = 1."""
    P = runs_matrix_nb(4.5, 4.2, 4.0, 3.5)
    n = P.shape[0]
    ri, ci = np.arange(n)[:, None], np.arange(n)[None, :]
    p_home_rl = float(P[ri >= ci + 2].sum())   # home covers -1.5
    p_away_rl = float(P[ci >= ri + 2].sum())   # away covers -1.5
    p_middle = 1.0 - p_home_rl - p_away_rl

    mkts = markets_from_matrix_nb(P)
    assert abs(mkts["rl_home_minus15"] - p_home_rl) < 1e-9
    assert abs(mkts["rl_away_plus15"] - (1.0 - p_home_rl)) < 1e-9
    total = p_home_rl + p_middle + p_away_rl
    assert abs(total - 1.0) < 1e-9, f"RL probs sum={total:.8f}"


# ---------------------------------------------------------------------------
# 8. Real data loads with required columns
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP_DATA, reason="games.parquet not found")
def test_real_data_loads():
    import pandas as pd
    df = pd.read_parquet(_GAMES_PATH)
    required = {"home_runs", "away_runs", "date", "home_team", "away_team", "season"}
    missing = required - set(df.columns)
    assert not missing, f"Missing columns: {missing}"
    assert len(df) > 1000, f"Too few rows: {len(df)}"
    assert df["home_runs"].min() >= 0
    assert df["away_runs"].min() >= 0


# ---------------------------------------------------------------------------
# 9. End-to-end validation returns finite Brier scores
# ---------------------------------------------------------------------------

@pytest.mark.skipif(_SKIP_DATA, reason="games.parquet not found")
def test_brier_scores_finite():
    result = run_validation(str(_GAMES_PATH))
    assert result["n_val"] > 100, f"Too few validation games: {result['n_val']}"
    assert math.isfinite(result["r_home"]), "r_home is not finite"
    assert math.isfinite(result["r_away"]), "r_away is not finite"
    for line_key, metrics in result["ou_brier"].items():
        for brier_key in ("brier_negbinom", "brier_poisson"):
            val = metrics[brier_key]
            assert math.isfinite(val), f"{line_key}.{brier_key} = {val}"
            assert 0.0 <= val <= 0.5, f"{line_key}.{brier_key} = {val} out of [0, 0.5]"
    for brier_key in ("brier_negbinom", "brier_poisson"):
        val = result["run_line"][brier_key]
        assert math.isfinite(val), f"run_line.{brier_key} = {val}"


# ---------------------------------------------------------------------------
# 10. Brier score utility
# ---------------------------------------------------------------------------

def test_brier_score_known():
    """Perfect predictions → Brier = 0; always-0.5 → Brier = 0.25."""
    assert brier_score([1.0, 1.0, 0.0, 0.0], [1, 1, 0, 0]) == 0.0
    assert abs(brier_score([0.5] * 100, [1] * 50 + [0] * 50) - 0.25) < 1e-9


def test_tail_coverage_structure():
    probs = np.array([0.05, 0.06, 0.08, 0.92, 0.95, 0.97, 0.5, 0.5])
    acts = np.array([0.0, 0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 1.0])
    tc = _tail_coverage(probs, acts)
    assert "tail_low_n" in tc and "tail_high_n" in tc
    assert tc["tail_low_n"] == 3
    assert tc["tail_high_n"] == 3
