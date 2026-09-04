"""Focused numerical tests for the isolated G253 correspondence solver."""

from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking.g253_line_conic_calibration import (
    LineCorrespondence,
    circle_conic,
    fit_line_conic,
    fit_lines,
    homogeneous_line,
)


def _project_line(endpoints: np.ndarray, homography: np.ndarray) -> np.ndarray:
    projected = cv2.perspectiveTransform(endpoints.reshape(1, -1, 2).astype(np.float32), np.linalg.inv(homography))[0]
    return projected.astype(float)


def test_g253_line_fit_recovers_synthetic_image_to_court_map() -> None:
    truth = np.array(((0.032, -0.004, -10.0), (0.006, 0.052, -18.0), (0.00001, 0.0002, 1.0)))
    court_lines = [
        np.array(((0.0, 0.0), (50.0, 0.0))), np.array(((17.0, 0.0), (17.0, 19.0))),
        np.array(((33.0, 0.0), (33.0, 19.0))), np.array(((17.0, 19.0), (33.0, 19.0))),
    ]
    correspondences = [LineCorrespondence(str(index), _project_line(points, truth), points) for index, points in enumerate(court_lines)]
    estimated, condition, _singular = fit_lines(correspondences)
    probes = np.array(((2.0, 3.0), (25.0, 10.0), (48.0, 80.0)), dtype=np.float32)
    estimated_image = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(estimated))[0]
    truth_image = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(truth))[0]
    assert np.allclose(estimated_image, truth_image, atol=1e-3)
    assert np.isfinite(condition)


def test_g253_homogeneous_line_rejects_coincident_endpoints() -> None:
    try:
        homogeneous_line(np.array(((10.0, 10.0), (10.0, 10.0))))
    except ValueError as error:
        assert "distinct" in str(error)
    else:
        raise AssertionError("coincident endpoints must fail")


def test_g253_two_lines_and_circle_recover_synthetic_map() -> None:
    truth = np.array(((0.032, -0.004, -10.0), (0.006, 0.052, -18.0), (0.00001, 0.0002, 1.0)))
    court_lines = [np.array(((0.0, 47.0), (50.0, 47.0))), np.array(((0.0, 0.0), (50.0, 0.0)))]
    lines = [LineCorrespondence(str(index), _project_line(points, truth), points) for index, points in enumerate(court_lines)]
    court_circle = circle_conic((25.0, 47.0), 6.0)
    estimated, residual, condition = fit_line_conic(lines, truth.T @ court_circle @ truth, court_circle, starts=16)
    probes = np.array(((2.0, 3.0), (25.0, 47.0), (48.0, 80.0)), dtype=np.float32)
    estimated_image = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(estimated))[0]
    truth_image = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(truth))[0]
    assert np.allclose(estimated_image, truth_image, atol=1e-2)
    assert residual < 1e-6
    assert np.isfinite(condition)
