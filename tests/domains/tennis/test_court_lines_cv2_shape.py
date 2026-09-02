"""Regression coverage for OpenCV 4 and 5 Hough line-array layouts."""
from __future__ import annotations

import cv2
import numpy as np

from domains.tennis.tracking import court_lines


def _parse_hough_layout(monkeypatch, layout: np.ndarray) -> list[np.ndarray]:
    monkeypatch.setattr(court_lines.cv2, "HoughLinesP", lambda *args, **kwargs: layout.copy())
    frame = np.zeros((72, 96, 3), dtype=np.uint8)
    return court_lines.court_line_segments(frame, min_length=8)


def test_court_line_segments_accepts_legacy_and_flat_hough_layouts(monkeypatch) -> None:
    """Both OpenCV Hough layouts must parse to the same ordered segments."""
    mask = np.zeros((128, 128), dtype=np.uint8)
    cv2.line(mask, (10, 10), (118, 10), 255, 1)
    installed = cv2.HoughLinesP(mask, 1, np.pi / 180.0, 10, minLineLength=5, maxLineGap=1)
    assert installed is not None
    assert installed.ndim in (2, 3)

    flat = np.asarray(((3, 4, 50, 4), (7, 8, 7, 60), (12, 15, 40, 42)), dtype=np.int32)
    legacy_segments = _parse_hough_layout(monkeypatch, flat.reshape(-1, 1, 4))
    flat_segments = _parse_hough_layout(monkeypatch, flat)

    assert len(legacy_segments) == len(flat_segments) == len(flat)
    np.testing.assert_array_equal(np.asarray(legacy_segments), np.asarray(flat_segments))
    np.testing.assert_array_equal(np.asarray(flat_segments), flat.astype(float))
