"""Focused tests for G257's non-fitting blind render construction."""

from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.tracking import g257_eye_gate_discrimination as subject


def test_g257_translation_moves_each_projected_court_probe_by_stated_pixels() -> None:
    candidate = np.array(((0.04, -0.003, -18.0), (0.006, 0.052, -24.0), (0.00002, 0.0002, 1.0)))
    probes = np.float32(((2.0, 3.0), (25.0, 10.0), (48.0, 80.0)))
    original = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(candidate))[0]
    shifted = cv2.perspectiveTransform(probes.reshape(1, -1, 2), np.linalg.inv(subject.translated_image_to_court(candidate, 20.0)))[0]
    assert np.allclose(shifted - original, np.array((20.0, 0.0)), atol=1e-4)


def test_g257_board_preserves_native_main_panel_width_and_adds_insets() -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    candidate = np.array(((0.04, -0.003, -18.0), (0.006, 0.052, -24.0), (0.00002, 0.0002, 1.0)))
    board = subject.render_board(image, candidate, 1)
    assert board.shape[:2] == (1110, 1280)


def test_g257_ladder_spans_the_required_fixed_magnitudes() -> None:
    assert subject.LADDER_PX == (5, 10, 20, 40, 100)
