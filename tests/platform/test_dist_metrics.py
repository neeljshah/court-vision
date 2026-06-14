"""tests/platform/test_dist_metrics.py — Tests for scripts/platformkit/dist_metrics.py.

All synthetic, fast (no I/O, no network, no GPU).
"""
from __future__ import annotations
import math
import numpy as np
import pytest
from scripts.platformkit.dist_metrics import (
    coverage_calibration, crps_ensemble, crps_poisson_pmf,
    distribution_scorecard, interval_coverage, pinball_loss,
)


# ---------------------------------------------------------------------------
# pinball_loss
# ---------------------------------------------------------------------------

class TestPinballLoss:
    def test_hand_tau05_underestimate(self):
        # y=10, q=8, tau=0.5 → 0.5*(10-8) = 1.0
        assert pinball_loss(10.0, 8.0, 0.5) == pytest.approx(1.0)

    def test_hand_tau09_overestimate(self):
        # y=8, q=10, tau=0.9 → (1-0.9)*(10-8) = 0.2
        assert pinball_loss(8.0, 10.0, 0.9) == pytest.approx(0.2)

    def test_hand_tau01_underestimate(self):
        # y=10, q=5, tau=0.1 → 0.1*(10-5) = 0.5
        assert pinball_loss(10.0, 5.0, 0.1) == pytest.approx(0.5)

    def test_zero_when_q_equals_y(self):
        for tau in (0.1, 0.5, 0.9):
            assert pinball_loss(7.0, 7.0, tau) == pytest.approx(0.0)

    def test_minimised_at_true_quantile(self):
        """Loss is strictly minimised at the true quantile over a large sample."""
        rng = np.random.default_rng(42)
        y = rng.normal(20.0, 5.0, 10_000)
        tau = 0.75
        true_q = float(np.quantile(y, tau))
        loss_opt = pinball_loss(y, np.full(len(y), true_q), tau)
        for delta in (-3.0, -1.0, 1.0, 3.0):
            assert pinball_loss(y, np.full(len(y), true_q + delta), tau) > loss_opt

    def test_vectorised_mean(self):
        # Both: y-q=2, tau=0.5 → each=1.0, mean=1.0
        assert pinball_loss([10.0, 20.0], [8.0, 18.0], 0.5) == pytest.approx(1.0)

    def test_nan_rows_skipped(self):
        y = np.array([10.0, float("nan"), 10.0])
        q = np.array([8.0, 5.0, 8.0])
        assert pinball_loss(y, q, 0.5) == pytest.approx(1.0)

    def test_all_nan_returns_nan(self):
        assert math.isnan(pinball_loss([float("nan")], [float("nan")], 0.5))

    def test_invalid_quantile_raises(self):
        with pytest.raises(ValueError):
            pinball_loss(5.0, 5.0, 0.0)
        with pytest.raises(ValueError):
            pinball_loss(5.0, 5.0, 1.0)


# ---------------------------------------------------------------------------
# interval_coverage
# ---------------------------------------------------------------------------

class TestIntervalCoverage:
    def test_all_inside(self):
        r = interval_coverage([1.0, 2.0, 3.0], [0.0]*3, [10.0]*3)
        assert r["coverage"] == pytest.approx(1.0) and r["n"] == 3

    def test_none_inside(self):
        r = interval_coverage([15.0, 20.0], [0.0]*2, [1.0]*2)
        assert r["coverage"] == pytest.approx(0.0)

    def test_partial(self):
        r = interval_coverage([0.5, 2.0, 0.5], [0.0]*3, [1.0]*3)
        assert r["coverage"] == pytest.approx(2 / 3)

    def test_boundary_inclusive(self):
        r = interval_coverage([0.0, 1.0], [0.0, 0.0], [1.0, 1.0])
        assert r["coverage"] == pytest.approx(1.0)

    def test_mean_width(self):
        r = interval_coverage([0.5, 1.5], [0.0, 1.0], [2.0, 3.0])
        assert r["mean_width"] == pytest.approx(2.0)

    def test_nan_obs_excluded(self):
        r = interval_coverage([0.5, float("nan")], [0.0, 0.0], [1.0, 1.0])
        assert r["n"] == 1 and r["coverage"] == pytest.approx(1.0)

    def test_all_nan_returns_nan(self):
        r = interval_coverage([float("nan")], [0.0], [1.0])
        assert r["n"] == 0 and math.isnan(r["coverage"])


# ---------------------------------------------------------------------------
# coverage_calibration
# ---------------------------------------------------------------------------

class TestCoverageCal:
    def test_too_tight_flagged(self):
        """Interval covering ~20% but claiming 90% → not calibrated, gap < 0."""
        rng = np.random.default_rng(0)
        y = rng.uniform(0, 10, 500)
        lo, hi = np.full(500, 4.0), np.full(500, 6.0)
        r = coverage_calibration(y, lo, hi, nominal=0.90)
        assert not r["calibrated"] and r["gap"] < 0

    def test_well_calibrated_passes(self):
        n, inside = 1000, 900
        y = np.array([0.5] * inside + [10.0] * (n - inside), dtype=float)
        r = coverage_calibration(y, np.zeros(n), np.ones(n), nominal=0.90, tol=0.06)
        assert r["calibrated"]

    def test_gap_positive_when_too_wide(self):
        r = coverage_calibration([0.5, 0.5, 0.5], [0.0]*3, [1.0]*3, nominal=0.80)
        assert r["gap"] > 0


# ---------------------------------------------------------------------------
# crps_ensemble
# ---------------------------------------------------------------------------

class TestCrpsEnsemble:
    def test_degenerate_1sample_equals_abs_error(self):
        y = np.array([10.0, 20.0, 15.0])
        preds = np.array([8.0, 22.0, 15.0])
        result = crps_ensemble(y, preds[:, np.newaxis])
        assert result == pytest.approx(float(np.mean(np.abs(preds - y))), abs=1e-9)

    def test_single_obs_1d_samples_degenerate(self):
        assert crps_ensemble(10.0, np.array([10.0])) == pytest.approx(0.0, abs=1e-9)

    def test_concentrating_ensemble_decreases_crps(self):
        rng = np.random.default_rng(7)
        y = np.full(500, 20.0)
        assert (crps_ensemble(y, rng.normal(20.0, 1.0, (500, 200))) <
                crps_ensemble(y, rng.normal(20.0, 10.0, (500, 200))))

    def test_centred_beats_offset(self):
        rng = np.random.default_rng(13)
        y = np.full(200, 20.0)
        assert (crps_ensemble(y, rng.normal(20.0, 1.0, (200, 100))) <
                crps_ensemble(y, rng.normal(25.0, 1.0, (200, 100))))

    def test_nan_obs_excluded(self):
        y = np.array([10.0, float("nan"), 10.0])
        s = np.full((3, 1), 10.0)
        assert crps_ensemble(y, s) == pytest.approx(0.0, abs=1e-9)

    def test_all_nan_returns_nan(self):
        assert math.isnan(crps_ensemble([float("nan")], [[5.0, 6.0]]))

    def test_nan_members_skipped(self):
        # 1 valid member at truth → CRPS = 0
        assert crps_ensemble(np.array([10.0]), np.array([[10.0, float("nan")]])) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# crps_poisson_pmf
# ---------------------------------------------------------------------------

class TestCrpsPoissonPmf:
    # PMF=[0.3,0.7], support=[0,1]
    # y=0: CDF=[0.3,1.0], ind=[1,1] → (0.3-1)^2+(1-1)^2 = 0.49
    def test_hand_y0(self):
        assert crps_poisson_pmf(0, [0.3, 0.7], [0, 1]) == pytest.approx(0.49, abs=1e-9)

    # y=1: CDF=[0.3,1.0], ind=[0,1] → (0.3-0)^2+(1-1)^2 = 0.09
    def test_hand_y1(self):
        assert crps_poisson_pmf(1, [0.3, 0.7], [0, 1]) == pytest.approx(0.09, abs=1e-9)

    def test_degenerate_point_mass_on_truth_zero(self):
        pmf = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
        assert crps_poisson_pmf(2, pmf, [0, 1, 2, 3, 4, 5]) == pytest.approx(0.0, abs=1e-9)

    def test_degenerate_wrong_gives_positive(self):
        assert crps_poisson_pmf(3, [1.0, 0.0, 0.0, 0.0], [0, 1, 2, 3]) > 0

    def test_vectorised_multi_obs(self):
        pmf = np.array([[0.3, 0.7], [0.3, 0.7]])
        result = crps_poisson_pmf([0, 1], pmf, [0, 1])
        assert result == pytest.approx((0.49 + 0.09) / 2, abs=1e-9)

    def test_pmf_normalised_internally(self):
        # [0.6, 1.4] has same ratio as [0.3, 0.7]
        assert crps_poisson_pmf(0, [0.6, 1.4], [0, 1]) == pytest.approx(0.49, abs=1e-9)

    def test_nan_obs_excluded_valid_row_scored(self):
        # row0: nan → skipped; row1: y=0, pmf=[0.5,0.5] → (0.5-1)^2+(1-1)^2=0.25
        result = crps_poisson_pmf([float("nan"), 0], [[0.3, 0.7], [0.5, 0.5]], [0, 1])
        assert result == pytest.approx(0.25, abs=1e-9)

    def test_all_nan_returns_nan(self):
        assert math.isnan(crps_poisson_pmf(float("nan"), [0.5, 0.5], [0, 1]))


# ---------------------------------------------------------------------------
# distribution_scorecard
# ---------------------------------------------------------------------------

class TestDistributionScorecard:
    def _data(self, n=100, seed=0):
        rng = np.random.default_rng(seed)
        y = rng.normal(20.0, 5.0, n)
        s = rng.normal(20.0, 5.0, (n, 50))
        lo = np.quantile(s, 0.05, axis=1)
        hi = np.quantile(s, 0.95, axis=1)
        return y, s, lo, hi

    def test_keys_present(self):
        y, s, lo, hi = self._data()
        keys = set(distribution_scorecard(y, s, lo, hi).keys())
        assert keys == {"crps", "pinball_lo", "pinball_hi", "coverage", "mean_width",
                        "nominal_coverage", "coverage_gap", "calibrated", "n"}

    def test_n_matches(self):
        y, s, lo, hi = self._data(n=80)
        assert distribution_scorecard(y, s, lo, hi)["n"] == 80

    def test_crps_positive(self):
        y, s, lo, hi = self._data()
        assert distribution_scorecard(y, s, lo, hi)["crps"] > 0

    def test_nominal_passthrough(self):
        y, s, lo, hi = self._data()
        assert distribution_scorecard(y, s, lo, hi, nominal_coverage=0.80)["nominal_coverage"] == pytest.approx(0.80)

    def test_wide_interval_calibrated(self):
        rng = np.random.default_rng(1)
        n = 200
        y = rng.normal(20.0, 3.0, n)
        s = rng.normal(20.0, 3.0, (n, 50))
        lo, hi = np.full(n, -1000.0), np.full(n, 1000.0)
        # gap = 1.0 - 0.90 = 0.10 < tol=0.5 → calibrated
        assert distribution_scorecard(y, s, lo, hi, nominal_coverage=0.90, tol=0.5)["calibrated"]

    def test_tiny_interval_not_calibrated(self):
        rng = np.random.default_rng(2)
        n = 200
        y = rng.normal(20.0, 5.0, n)
        s = rng.normal(20.0, 5.0, (n, 50))
        lo, hi = np.full(n, 100.0), np.full(n, 101.0)
        assert not distribution_scorecard(y, s, lo, hi, nominal_coverage=0.90)["calibrated"]
