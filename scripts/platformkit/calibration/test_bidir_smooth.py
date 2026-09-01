"""Focused checks for offline bidirectional calibration smoothing.

Run: python -m pytest scripts/platformkit/calibration/test_bidir_smooth.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.calibration.bidir_smooth import smooth_bidirectional


def _jump_p95(values: np.ndarray) -> float:
    """Return the p95 Euclidean frame-to-frame calibration change."""
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array[:, np.newaxis]
    return float(np.quantile(np.linalg.norm(np.diff(array, axis=0), axis=1), 0.95))


def test_impulses_are_smoothed_within_the_stated_adjustment_limit() -> None:
    """A centered filter removes at least 80 percent of impulse discontinuity."""
    constant = 100.0
    raw = np.full(200, constant)
    raw[np.arange(10, 200, 20)] += 10.0

    smoothed, rejected = smooth_bidirectional(raw, adjustment_limits=2.0, delay=15)

    assert _jump_p95(smoothed) <= _jump_p95(raw) * 0.20
    assert float(np.max(np.abs(smoothed - constant))) <= 2.0
    assert rejected.any()


def test_rejection_is_per_frame_when_any_parameter_exceeds_its_limit() -> None:
    """Parameter-specific limits reject only frames with an excessive update."""
    raw = np.zeros((101, 2))
    raw[50, 0] = 10.0

    smoothed, rejected = smooth_bidirectional(raw, adjustment_limits=[0.1, 1.0], delay=15)

    assert smoothed.shape == raw.shape
    assert rejected.shape == (len(raw),)
    assert rejected.any()
    assert not rejected[0]
    assert not rejected[-1]


@pytest.mark.parametrize("mode", ["causal", "streaming"])
def test_causal_modes_are_rejected(mode: str) -> None:
    """The future window required for smoothing is unavailable in live mode."""
    with pytest.raises(ValueError, match="offline-only"):
        smooth_bidirectional([1.0, 2.0, 3.0], adjustment_limits=1.0, mode=mode)
