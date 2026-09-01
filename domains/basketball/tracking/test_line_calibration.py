"""Tests for line-correspondence basketball calibration."""
from __future__ import annotations

import numpy as np

from domains.basketball.tracking.line_calibration import (
    COURT_LINE_SETS, line_residual, solve_from_lines,
)


def _image_lines(homography: np.ndarray, court_lines: list[np.ndarray]) -> list[np.ndarray]:
    inverse_transpose = np.linalg.inv(homography).T
    result = []
    for line in court_lines:
        projected = inverse_transpose @ line
        result.append(projected / np.hypot(projected[0], projected[1]))
    return result


def test_line_correspondences_recover_synthetic_homography() -> None:
    court = [np.asarray(line) for line in COURT_LINE_SETS["nba_wnba"].values()]
    expected = np.array(((9.2, 0.7, 210.0), (0.3, 8.4, 120.0),
                         (0.0012, 0.0008, 1.0)))
    observed = _image_lines(expected, court)
    recovered = solve_from_lines(court, observed)
    assert recovered is not None
    expected_inverse = np.linalg.inv(expected)
    assert np.allclose(recovered, expected_inverse / expected_inverse[2, 2], atol=1e-6)
    assert max(line_residual(recovered, image, court_line)
               for image, court_line in zip(observed, court)) < 5e-5


def test_line_solver_rejects_fewer_than_four_correspondences() -> None:
    court = [np.asarray(line) for line in COURT_LINE_SETS["nba_wnba"].values()]
    assert solve_from_lines(court[:3], court[:3]) is None
