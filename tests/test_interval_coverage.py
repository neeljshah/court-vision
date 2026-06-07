"""Empirical interval-coverage calibration tests for the per-second projector.

Fixes the ``z_mult=1.0`` caveat: the band half-width is now
``z(stat, game-time, nominal) * residual_MAE(stat, game-time)`` where ``z`` is
calibrated (empirically from a held-out residual sample, or closed-form Laplace
when only aggregate MAE is on disk) so the band's STATED nominal coverage matches
reality.

These tests assert that, on a HELD-OUT residual set, the achieved empirical
coverage is within tolerance of the nominal coverage. They also pin the honesty
guarantees: a flat MAE band (z=1.0) is NOT 80% coverage, and the default
``IntervalCalibrator`` (empty z_table) reproduces the legacy ``z_mult * MAE``
band byte-for-byte (so existing tests + disabled-flag serving are unchanged).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from src.ingame.continuous_projection import PLAYER_STATS
from src.ingame.per_second_projector import (
    DEFAULT_NOMINAL_COVERAGES,
    EVAL_CURVE_V2,
    IntervalCalibrator,
    _laplace_z_for_coverage,
)


# --------------------------------------------------------------------------- #
# Synthetic held-out residual set: Laplace-distributed residuals per stat/bucket
# with scale == that stat/bucket's eval-curve MAE. This is the worst case for
# the closed-form fallback (it ASSUMES Laplace), and the exact case for the
# empirical fit. We use a fixed seed so the assertions are deterministic.
# --------------------------------------------------------------------------- #
_RNG = np.random.default_rng(20260531)
_GRID_LABELS = [
    "06min(midQ1)", "12min(endQ1)", "18min(midQ2)", "24min(endQ2/half)",
    "30min(midQ3)", "36min(endQ3)", "42min(midQ4)",
]
_N_PER = 4000


def _make_residuals(calib: IntervalCalibrator, dist: str = "laplace"):
    """Build {bucket_label: {stat: [resid,...]}} with scale == bucket MAE."""
    out = {}
    for label in _GRID_LABELS:
        elapsed_min = float(label.split("min")[0])
        rem = max(0.0, (48.0) - elapsed_min)
        per_stat = {}
        for stat in PLAYER_STATS:
            mae = calib._mae_at(stat, rem)
            if mae <= 0:
                continue
            if dist == "laplace":
                # Laplace(0, b) has mean|x| = b == MAE
                per_stat[stat] = _RNG.laplace(0.0, mae, size=_N_PER).tolist()
            elif dist == "gaussian":
                # Gaussian with mean|x| = MAE -> sigma = MAE*sqrt(pi/2)
                sigma = mae * math.sqrt(math.pi / 2.0)
                per_stat[stat] = _RNG.normal(0.0, sigma, size=_N_PER).tolist()
            else:  # heavy-tailed (student-t df=3), scaled to MAE
                t = _RNG.standard_t(3, size=_N_PER)
                t = t / float(np.mean(np.abs(t))) * mae
                per_stat[stat] = t.tolist()
        out[label] = per_stat
    return out


# --------------------------------------------------------------------------- #
# Closed-form Laplace z
# --------------------------------------------------------------------------- #
def test_laplace_z_closed_form():
    assert _laplace_z_for_coverage(0.80) == pytest.approx(-math.log(0.20), abs=1e-9)
    assert _laplace_z_for_coverage(0.50) == pytest.approx(-math.log(0.50), abs=1e-9)
    # an MAE band (z=1) covers ~63.2% of a Laplace -> NOT 80%
    assert (1.0 - math.exp(-1.0)) == pytest.approx(0.6321, abs=1e-3)


# --------------------------------------------------------------------------- #
# Backward-compat: default calibrator == legacy z_mult * MAE band.
# --------------------------------------------------------------------------- #
def test_default_constructor_is_legacy_band():
    knots = {s: [(0.0, 0.0), (24.0, 2.0), (42.0, 4.0)] for s in PLAYER_STATS}
    legacy = IntervalCalibrator(knots=knots, z_mult=1.0)  # empty z_table
    # with empty z_table, band falls back to z_mult * interpolated MAE
    assert legacy.band("pts", 42.0) == pytest.approx(4.0, abs=1e-9)
    assert legacy.band("pts", 24.0) == pytest.approx(2.0, abs=1e-9)
    assert legacy.band("pts", 33.0) == pytest.approx(3.0, abs=1e-9)  # midpoint
    legacy2 = IntervalCalibrator(knots=knots, z_mult=1.6)
    assert legacy2.band("pts", 42.0) == pytest.approx(6.4, abs=1e-9)


# --------------------------------------------------------------------------- #
# Closed-form Laplace fallback (no residual sample) hits nominal on Laplace data.
# --------------------------------------------------------------------------- #
def test_laplace_fallback_coverage_on_laplace_residuals():
    calib = IntervalCalibrator.from_eval_curve(EVAL_CURVE_V2)
    resids = _make_residuals(calib, dist="laplace")
    report = calib.calibrate_coverage(resids)
    for nom in DEFAULT_NOMINAL_COVERAGES:
        pooled = report["by_nominal"][float(nom)]["pooled_by_stat"]
        assert pooled, "no pooled coverage computed"
        for stat, cell in pooled.items():
            # Laplace-fallback z is exact for Laplace residuals -> within 3pp
            assert abs(cell["pooled_achieved_coverage"] - nom) <= 0.03, (
                f"{stat} nominal={nom} achieved={cell['pooled_achieved_coverage']}"
            )


# --------------------------------------------------------------------------- #
# Empirical fit hits nominal regardless of residual distribution shape.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("dist", ["laplace", "gaussian", "heavy"])
def test_empirical_fit_coverage_within_tolerance(dist):
    base = IntervalCalibrator.from_eval_curve(EVAL_CURVE_V2)
    resids = _make_residuals(base, dist=dist)
    fitted = base.fit_z_from_residuals(resids)
    report = fitted.calibrate_coverage(resids)
    for nom in DEFAULT_NOMINAL_COVERAGES:
        pooled = report["by_nominal"][float(nom)]["pooled_by_stat"]
        assert pooled
        for stat, cell in pooled.items():
            # fit on the same held-out sample -> coverage exact by construction.
            # 2.5pp tolerance absorbs bucket-snapping + quantile discreteness.
            assert abs(cell["pooled_achieved_coverage"] - nom) <= 0.025, (
                f"dist={dist} {stat} nominal={nom} "
                f"achieved={cell['pooled_achieved_coverage']}"
            )


# --------------------------------------------------------------------------- #
# The OLD flat z=1.0 band does NOT achieve 80% (this is the caveat we fixed).
# --------------------------------------------------------------------------- #
def test_flat_z1_undercovers_80():
    calib = IntervalCalibrator.from_eval_curve(EVAL_CURVE_V2)
    resids = _make_residuals(calib, dist="laplace")
    legacy = IntervalCalibrator(knots=calib.knots, z_mult=1.0)  # old behavior
    legacy_report = legacy.calibrate_coverage(resids)
    pooled80 = legacy_report["by_nominal"][0.80]["pooled_by_stat"]
    for stat, cell in pooled80.items():
        # an MAE band is ~63% on Laplace, well under 80%
        assert cell["pooled_achieved_coverage"] < 0.72, (
            f"{stat} flat-z1 achieved {cell['pooled_achieved_coverage']} "
            "(expected <0.72)"
        )


# --------------------------------------------------------------------------- #
# calibrate_coverage reports the required structure + honesty flags.
# --------------------------------------------------------------------------- #
def test_calibrate_coverage_report_shape():
    calib = IntervalCalibrator.from_eval_curve(EVAL_CURVE_V2)
    resids = _make_residuals(calib, dist="laplace")
    report = calib.calibrate_coverage(resids)
    assert "z_source" in report and "by_nominal" in report
    for nom in DEFAULT_NOMINAL_COVERAGES:
        block = report["by_nominal"][float(nom)]
        assert "by_bucket" in block and "pooled_by_stat" in block
        for stat, buckets in block["by_bucket"].items():
            for bk, cell in buckets.items():
                for key in ("n", "z", "mae", "band",
                            "achieved_coverage", "nominal", "hits_nominal"):
                    assert key in cell
                assert cell["band"] >= 0.0
                assert 0.0 <= cell["achieved_coverage"] <= 1.0
