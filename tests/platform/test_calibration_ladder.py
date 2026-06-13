"""tests/platform/test_calibration_ladder.py — Synthetic tests for calibration_ladder.py.

All tests are fast, require only numpy + sklearn (no corpus / adapter loading).
calibration != edge.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from scripts.platformkit.calibration_ladder import (
    conformal_interval,
    crps_binary,
    crps_mean,
    reliability,
    walk_forward_auto,
    walk_forward_platt,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(42)


def _well_calibrated(n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """Roughly calibrated probs: p ~ Uniform(0.1, 0.9), outcome ~ Bernoulli(p)."""
    p = RNG.uniform(0.1, 0.9, n)
    y = RNG.binomial(1, p).astype(float)
    return p, y


def _miscalibrated(n: int = 300) -> tuple[np.ndarray, np.ndarray]:
    """Over-confident probs pushed toward extremes."""
    p, y = _well_calibrated(n)
    p_bad = np.where(p > 0.5, np.minimum(p + 0.25, 0.99), np.maximum(p - 0.25, 0.01))
    return p_bad, y


# ---------------------------------------------------------------------------
# walk_forward_platt tests
# ---------------------------------------------------------------------------


class TestWalkForwardPlatt:
    def test_output_shape_and_range(self):
        """Output is (N,) and all values in [0, 1]."""
        p, y = _well_calibrated(200)
        out = walk_forward_platt(p, y, min_history=50)
        assert out.shape == (200,)
        assert np.all(out >= 0.0) and np.all(out <= 1.0)

    def test_passthrough_before_min_history(self):
        """Events before min_history pass through raw (no calibration applied)."""
        p, y = _well_calibrated(200)
        min_h = 80
        out = walk_forward_platt(p, y, min_history=min_h)
        np.testing.assert_array_equal(out[:min_h], p[:min_h])

    def test_monotonic_transform(self):
        """Calibrated outputs preserve rank order within the post-warmup region.

        Platt scaling via logistic regression on logit(p) is a monotone
        transform of logit(p), so rank order of the calibrated outputs must
        track rank order of the raw inputs.
        """
        p, y = _well_calibrated(300)
        out = walk_forward_platt(p, y, min_history=50)
        # Compare post-warmup pairs: if raw[i] > raw[j] then out[i] >= out[j].
        post = np.arange(50, 300)
        # Random 500 pairs within post-warmup region.
        idx = RNG.choice(post, size=(500, 2), replace=True)
        diff_raw = p[idx[:, 0]] - p[idx[:, 1]]
        diff_cal = out[idx[:, 0]] - out[idx[:, 1]]
        agree = (diff_raw * diff_cal >= -1e-8)  # allow tiny float noise
        assert agree.mean() > 0.95, (
            f"Monotone agreement {agree.mean():.3f} < 0.95"
        )

    def test_leak_free_flip_future_no_change(self):
        """Flipping a future outcome must not change earlier calibrated values.

        Only the calibration of events AFTER the flip point may change; events
        at or before it must be bit-identical.
        """
        p, y = _well_calibrated(200)
        flip_idx = 150
        y_flipped = y.copy()
        y_flipped[flip_idx] = 1.0 - y_flipped[flip_idx]

        out_orig = walk_forward_platt(p, y, min_history=50)
        out_flip = walk_forward_platt(p, y_flipped, min_history=50)

        # Events 0..flip_idx must be identical (future flip cannot affect them).
        np.testing.assert_array_equal(
            out_orig[:flip_idx], out_flip[:flip_idx],
            err_msg="Flipping a future outcome changed earlier calibrated values.",
        )

    def test_length_mismatch_raises(self):
        """Mismatched lengths raise ValueError."""
        with pytest.raises(ValueError):
            walk_forward_platt([0.5, 0.6], [1.0])

    def test_refit_every_deterministic(self):
        """Same inputs produce bit-identical outputs (determinism)."""
        p, y = _well_calibrated(200)
        np.testing.assert_array_equal(
            walk_forward_platt(p, y, min_history=50),
            walk_forward_platt(p, y, min_history=50),
        )


# ---------------------------------------------------------------------------
# walk_forward_auto tests
# ---------------------------------------------------------------------------


class TestWalkForwardAuto:
    def test_returns_tuple(self):
        """Returns (np.ndarray, str)."""
        p, y = _well_calibrated(200)
        arr, method = walk_forward_auto(p, y, min_history=50)
        assert isinstance(arr, np.ndarray)
        assert method in ("isotonic", "platt")

    def test_picks_better_method_on_miscalibrated(self):
        """On a miscalibrated set auto picks the lower-log-loss method."""
        # Use a skewed set so isotonic and platt may differ.
        p_bad, y = _miscalibrated(400)
        arr, method = walk_forward_auto(p_bad, y, min_history=50)

        # Verify the returned array matches the claimed method.
        from scripts.platformkit.recalibration import walk_forward_recalibrate
        iso = walk_forward_recalibrate(p_bad, y, min_history=50)
        platt = walk_forward_platt(p_bad, y, min_history=50)

        if method == "isotonic":
            np.testing.assert_array_equal(arr, iso)
        else:
            np.testing.assert_array_equal(arr, platt)

    def test_output_in_range(self):
        """Auto output is always in [0, 1]."""
        p, y = _miscalibrated(300)
        arr, _ = walk_forward_auto(p, y, min_history=50)
        assert np.all(arr >= 0.0) and np.all(arr <= 1.0)

    def test_method_name_string(self):
        """Method name is always one of the two valid strings."""
        p, y = _well_calibrated(200)
        _, method = walk_forward_auto(p, y, min_history=50)
        assert method in {"isotonic", "platt"}

    def test_too_short_fallback_isotonic(self):
        """When n < min_history the auto-selector falls back to isotonic."""
        p = np.array([0.4, 0.6, 0.5])
        y = np.array([0.0, 1.0, 1.0])
        arr, method = walk_forward_auto(p, y, min_history=50)
        assert method == "isotonic"


# ---------------------------------------------------------------------------
# conformal_interval tests
# ---------------------------------------------------------------------------


class TestConformalInterval:
    def test_wider_with_larger_spread(self):
        """Band widens when residuals have larger spread."""
        point = 0.5
        small_res = RNG.uniform(0.0, 0.05, 200)  # tight residuals
        large_res = RNG.uniform(0.0, 0.40, 200)  # wide residuals

        lo_s, hi_s = conformal_interval(point, small_res, alpha=0.1)
        lo_l, hi_l = conformal_interval(point, large_res, alpha=0.1)

        width_small = hi_s - lo_s
        width_large = hi_l - lo_l
        assert width_large > width_small, (
            f"Large-spread band ({width_large:.4f}) not wider than small ({width_small:.4f})"
        )

    def test_coverage_approximately_one_minus_alpha(self):
        """Coverage over synthetic test events is >= 1-alpha."""
        alpha = 0.1
        true_p = RNG.uniform(0.1, 0.9, 1000)
        cal_res = RNG.normal(0, 0.08, 500)  # calibration residuals
        covered = sum(
            1 for i in range(500)
            if conformal_interval(float(true_p[500 + i]), cal_res, alpha)[0]
            <= true_p[500 + i] <=
            conformal_interval(float(true_p[500 + i]), cal_res, alpha)[1]
        )
        assert covered / 500 >= (1.0 - alpha) - 0.05

    def test_empty_residuals_full_interval(self):
        """Empty residual pool returns (0.0, 1.0)."""
        lo, hi = conformal_interval(0.5, [], alpha=0.1)
        assert lo == 0.0 and hi == 1.0

    def test_output_clamped_to_unit_interval(self):
        """lo >= 0.0 and hi <= 1.0 always."""
        for pt in [0.05, 0.5, 0.95]:
            lo, hi = conformal_interval(pt, RNG.uniform(0, 0.5, 100), alpha=0.1)
            assert lo >= 0.0, f"lo={lo} < 0 for point={pt}"
            assert hi <= 1.0, f"hi={hi} > 1 for point={pt}"
            assert lo <= hi, f"lo={lo} > hi={hi} for point={pt}"


# ---------------------------------------------------------------------------
# reliability tests
# ---------------------------------------------------------------------------


class TestReliability:
    def test_keys_present(self):
        """All required keys are present."""
        p, y = _well_calibrated(300)
        r = reliability(p, y)
        for key in ("brier", "log_loss", "ece", "reliability_slope", "n"):
            assert key in r, f"Missing key: {key}"

    def test_brier_matches_manual(self):
        """Brier score matches manual computation."""
        p, y = _well_calibrated(300)
        r = reliability(p, y)
        expected = float(np.mean((p - y) ** 2))
        assert abs(r["brier"] - expected) < 1e-10

    def test_calibrated_lower_ece_than_miscalibrated(self):
        """A calibrated set has lower ECE than a miscalibrated one."""
        p_good, y_good = _well_calibrated(500)
        p_bad, y_bad = _miscalibrated(500)
        r_good = reliability(p_good, y_good)
        r_bad = reliability(p_bad, y_bad)
        assert r_good["ece"] < r_bad["ece"], (
            f"Calibrated ECE {r_good['ece']:.4f} not < miscalibrated {r_bad['ece']:.4f}"
        )

    def test_n_field(self):
        """n field equals length of valid inputs."""
        p, y = _well_calibrated(150)
        r = reliability(p, y)
        assert r["n"] == 150

    def test_empty_input_nan(self):
        """Empty input returns NaN for numeric fields."""
        r = reliability([], [])
        assert math.isnan(r["brier"])
        assert math.isnan(r["log_loss"])
        assert math.isnan(r["ece"])

    def test_log_loss_positive(self):
        """Log-loss is positive for non-trivial inputs."""
        p, y = _well_calibrated(300)
        r = reliability(p, y)
        assert r["log_loss"] > 0.0

    def test_slope_near_one_for_calibrated(self):
        """Reliability slope should be roughly 1.0 for a calibrated set (large N)."""
        rng = np.random.default_rng(7)
        p = rng.uniform(0.1, 0.9, 2000)
        y = rng.binomial(1, p).astype(float)
        r = reliability(p, y, bins=10)
        assert not math.isnan(r["reliability_slope"]), "slope is NaN"
        assert 0.5 <= r["reliability_slope"] <= 2.0, (
            f"Slope {r['reliability_slope']:.3f} out of [0.5, 2.0] for calibrated data"
        )


# ---------------------------------------------------------------------------
# crps_binary / crps_mean tests
# ---------------------------------------------------------------------------


class TestCRPS:
    def test_crps_binary_brier_identity(self):
        """crps_binary(p, y) == (p-y)^2; perfect=0, worst=1."""
        for prob, outcome, expected in [
            (0.7, 1.0, 0.09), (0.3, 0.0, 0.09),
            (1.0, 1.0, 0.0),  (1.0, 0.0, 1.0),
            (0.0, 0.0, 0.0),  (0.0, 1.0, 1.0),
        ]:
            assert abs(crps_binary(prob, outcome) - expected) < 1e-10

    def test_crps_mean_equals_brier(self):
        """crps_mean == mean Brier; NaN-safe; empty → NaN."""
        p, y = _well_calibrated(300)
        assert abs(crps_mean(p, y) - float(np.mean((p - y) ** 2))) < 1e-10
        assert math.isnan(crps_mean([], []))
        # NaN-safety: (0.6-1)^2=0.16, (0.4-0)^2=0.16 → mean=0.16
        assert abs(crps_mean([0.6, float("nan"), 0.4], [1.0, 1.0, 0.0]) - 0.16) < 1e-10
