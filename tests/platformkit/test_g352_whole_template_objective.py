"""G352 synthetic gates for the whole-template calibration objective."""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from scripts.platformkit.tracking import g334_court_line_calibration as g334
from scripts.platformkit.tracking import g334_court_template as template
from scripts.platformkit.tracking.g352_whole_template_objective import (
    fit_from_groups, fit_whole_template, validity_reason, whole_template_loss,
)

SHAPE = (680, 1280)
COURT_QUAD = np.float32([(0.0, 0.0), (0.0, template.HALF_Y_FT),
                         (template.COURT_WIDTH_FT, 0.0),
                         (template.COURT_WIDTH_FT, template.HALF_Y_FT)])
IMAGE_QUAD = np.float32([(100.0, 600.0), (1100.0, 600.0),
                         (100.0, 200.0), (1100.0, 200.0)])


class Stub:
    """Minimal physical support group for the exhaustive G334 enumerator."""

    def __init__(self, line):
        self.line = line


def truth_matrix() -> np.ndarray:
    return cv2.getPerspectiveTransform(COURT_QUAD, IMAGE_QUAD)


def render(matrix: np.ndarray) -> np.ndarray:
    image = np.full((SHAPE[0], SHAPE[1], 3), 70, dtype=np.uint8)
    for line in template.template_polylines():
        cv2.polylines(image, [np.round(template.project(matrix, line)).astype(np.int32)],
                      False, (245, 245, 245), 1, cv2.LINE_AA)
    return image


def image_line(matrix: np.ndarray, court_line) -> np.ndarray:
    line = np.linalg.inv(matrix).T @ np.asarray(court_line, dtype=float)
    return line / float(np.hypot(line[0], line[1]))


def projection_gap(first: np.ndarray, second: np.ndarray) -> float:
    left = template.project(first, template.TEMPLATE_POINTS)
    right = template.project(second, template.TEMPLATE_POINTS)
    inside = ((left[:, 0] >= 0) & (left[:, 0] < SHAPE[1])
              & (left[:, 1] >= 0) & (left[:, 1] < SHAPE[0]))
    return float(np.linalg.norm(left[inside] - right[inside], axis=1).max())


def exact_groups(matrix: np.ndarray) -> tuple[list, list]:
    width = [Stub(image_line(matrix, (0.0, 1.0, -value))) for value in (0.0, 47.0)]
    length = [Stub(image_line(matrix, (1.0, 0.0, -value))) for value in (0.0, 50.0)]
    return width, length


def test_whole_template_score_ranks_truth_over_out_of_frame_fold():
    truth = truth_matrix()
    image = render(truth)
    segments = g334.detect_segments(image, g334.ARM_A)
    field = template.distance_transform(image.shape, segments)
    shifted = np.array([[1.0, 0.0, 600.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ truth
    truth_loss, truth_in = whole_template_loss(truth, field, segments)
    shifted_loss, shifted_in = whole_template_loss(shifted, field, segments)
    assert truth_in == len(template.TEMPLATE_POINTS)
    assert shifted_in < truth_in
    assert truth_loss < shifted_loss


def test_in_search_gate_rejects_a_reflected_mapping():
    reflected = np.array([[-1.0, 0.0, SHAPE[1]], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]) @ truth_matrix()
    reason, _n_in = validity_reason(reflected, SHAPE, 2)
    assert reason == "folded"


def test_exact_lines_reproduce_truth_below_one_millionth_pixel():
    truth = truth_matrix()
    image = render(truth)
    supports = g334.detect_segments(image, g334.ARM_A)
    field = template.distance_transform(image.shape, supports)
    width, length = exact_groups(truth)
    fit = fit_from_groups(image.shape, width, length, field, supports)
    assert fit.reason == "valid"
    assert projection_gap(fit.image, truth) < 1e-6


def test_detected_line_path_recovers_rendered_known_h_within_one_pixel():
    raster_truth = truth_matrix()
    image = render(raster_truth)
    fit = fit_whole_template(image, g334.detect_segments(image, g334.ARM_A))
    # The detector reports its own line-coordinate convention rather than the
    # raster painter's cell origin. This fixed one-pixel conversion is applied
    # before comparing the detector-path fit to its known rendered H.
    detector_truth = np.array([[1.0, 0.0, -1.0], [0.0, 1.0, 1.0], [0.0, 0.0, 1.0]]) @ raster_truth
    assert fit.reason == "valid"
    assert projection_gap(fit.image, detector_truth) <= 1.0
