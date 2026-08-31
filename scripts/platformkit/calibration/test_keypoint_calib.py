"""Synthetic tests for sport-blind learned-keypoint calibration.

Run: python -m pytest scripts/platformkit/calibration/test_keypoint_calib.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from scripts.platformkit.calibration.keypoint_calib import (
    CANONICAL_LANDMARKS,
    TemporalCalibrator,
    project_points,
    solve_homography,
)


COURT_TO_IMAGE = np.array(
    [[11.7, 0.65, 230.0], [0.45, 10.8, 140.0], [0.0011, 0.0007, 1.0]], dtype=float,
)


def _detections(sport: str, rng: np.random.Generator, noise: float = 0.5, drop: bool = True) -> dict:
    """Render canonical landmark pixels through a fixed synthetic camera."""
    names = list(CANONICAL_LANDMARKS[sport])
    pixels = project_points(COURT_TO_IMAGE, [CANONICAL_LANDMARKS[sport][name] for name in names])
    detections = {}
    for index, (name, pixel) in enumerate(zip(names, pixels)):
        if drop and index % 5 == 0:
            continue
        jittered = pixel + rng.normal(0.0, noise, 2)
        detections[name] = (float(jittered[0]), float(jittered[1]), 0.95)
    return detections


@pytest.mark.parametrize("sport", ["basketball", "tennis", "soccer"])
def test_solve_homography_reprojects_noisy_landmarks(sport: str) -> None:
    """Noisy, incomplete detections recover court coordinates within 1.5 units."""
    detections = _detections(sport, np.random.default_rng(17))
    recovered = solve_homography(detections, sport)
    assert recovered is not None
    names = list(detections)
    pixels = [(detections[name][0], detections[name][1]) for name in names]
    expected = np.asarray([CANONICAL_LANDMARKS[sport][name] for name in names])
    error = np.linalg.norm(project_points(recovered, pixels) - expected, axis=1)
    assert float(error.mean()) < 1.5


def test_temporal_smoothing_reduces_homography_jitter() -> None:
    """Savitzky-Golay smoothing reduces frame-to-frame homography variance."""
    rng = np.random.default_rng(23)
    calibrator = TemporalCalibrator("basketball", drift_threshold=20.0)
    raw, smoothed = [], []
    for _ in range(24):
        detections = _detections("basketball", rng, noise=1.8, drop=False)
        frame_h = solve_homography(detections, "basketball")
        result = calibrator.update(detections)
        assert frame_h is not None and result.homography is not None
        raw.append(frame_h.ravel()[:8])
        smoothed.append(result.homography.ravel()[:8])
    raw_delta = np.diff(np.asarray(raw)[8:], axis=0)
    smoothed_delta = np.diff(np.asarray(smoothed)[8:], axis=0)
    assert float(np.var(smoothed_delta)) < float(np.var(raw_delta))


def test_underdetermined_detections_return_none() -> None:
    """Fewer than four named landmarks cannot determine a homography."""
    detections = _detections("soccer", np.random.default_rng(5), drop=False)
    three = dict(list(detections.items())[:3])
    assert solve_homography(three, "soccer") is None
