"""Focused analytic tests for continuous proper scoring and uncertainty."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.continuous_scoring import (
    conformal_intervals,
    coverage_report,
    crps_gaussian,
    crps_sample,
    score_model,
)


def _numeric_normal_crps(mu: float, sigma: float, observed: float) -> float:
    """Numerically integrate the CRPS CDF identity over a wide normal grid."""
    grid = np.linspace(mu - 10.0 * sigma, mu + 10.0 * sigma, 1_000_001)
    cdf = 0.5 * (1.0 + np.vectorize(__import__("math").erf)((grid - mu) / (sigma * np.sqrt(2.0))))
    step = (grid >= observed).astype(float)
    return float(np.trapz((cdf - step) ** 2, grid))


def test_gaussian_crps_matches_numeric_integration() -> None:
    expected = _numeric_normal_crps(mu=1.2, sigma=1.7, observed=-0.4)
    assert abs(crps_gaussian(1.2, 1.7, -0.4) - expected) < 1e-4


def test_sample_crps_uses_the_empirical_energy_form() -> None:
    # E|X-y| = 1 and E|X-X'| = 1 for samples [0, 2] and y=1.
    assert np.isclose(crps_sample([0.0, 2.0], 1.0), 0.5)


def test_perfectly_calibrated_synthetic_intervals_pass() -> None:
    rng = np.random.default_rng(7)
    observed = rng.normal(size=20_000)
    intervals = (np.full(observed.size, -1.6448536269514722), np.full(observed.size, 1.6448536269514722))
    report = coverage_report(intervals, observed)
    assert abs(report["coverage"] - 0.9) < 0.01
    assert report["verdict"] == "PASS"


def test_deliberately_narrow_intervals_are_undercover() -> None:
    observed = np.linspace(-3.0, 3.0, 1_001)
    report = coverage_report((np.full(observed.size, -0.1), np.full(observed.size, 0.1)), observed)
    assert report["verdict"] == "UNDERCOVER"
    assert report["coverage"] < 0.1


def test_conformal_finite_sample_quantile_correction_is_exact() -> None:
    # n=4, alpha=0.4: ceil((4 + 1) * 0.6) = 3, so radius is 3.0.
    lower, upper = conformal_intervals([1.0, -2.0, 3.0, -4.0], [10.0, 20.0], alpha=0.4)
    np.testing.assert_allclose(lower, [7.0, 17.0])
    np.testing.assert_allclose(upper, [13.0, 23.0])


def test_score_model_ties_scoring_and_coverage_together() -> None:
    report = score_model([0.0, 1.0], [1.0, 1.0], [0.2, 0.8], [0.5, 0.7, 1.0])
    assert report["crps_gaussian"] > 0.0
    assert np.isclose(report["mae_legacy"], 0.2)
    assert report["coverage"]["nominal_coverage"] == 0.9
