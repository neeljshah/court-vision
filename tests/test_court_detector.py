"""
test_court_detector.py — Tests for detect_court_homography().

All tests use synthetic images only — no real video, no yt-dlp, no run_clip.py.
The synthetic court images mimic hardwood floor colour + white court lines so the
full detection algorithm (floor mask -> Hough lines -> intersections -> corners) can
be exercised end-to-end without NBA footage.
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# -- Helpers -------------------------------------------------------------------

def _make_hardwood_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """
    Create a BGR frame resembling an NBA hardwood court.

    - Background: orange-brown (hardwood HSV H=20, S=100, V=180)
    - 3 horizontal white lines spaced evenly
    - 3 vertical white lines spaced evenly

    This gives 9 intersections, well above the 4-corner minimum.
    """
    # Convert hardwood HSV to BGR
    hsv_pixel = np.uint8([[[20, 100, 180]]])
    bgr_pixel = cv2.cvtColor(hsv_pixel, cv2.COLOR_HSV2BGR)[0, 0]
    frame = np.full((height, width, 3), bgr_pixel.tolist(), dtype=np.uint8)

    # Draw 3 horizontal white lines
    for frac in [0.2, 0.5, 0.8]:
        y = int(height * frac)
        cv2.line(frame, (0, y), (width, y), (255, 255, 255), thickness=4)

    # Draw 3 vertical white lines
    for frac in [0.2, 0.5, 0.8]:
        x = int(width * frac)
        cv2.line(frame, (x, 0), (x, height), (255, 255, 255), thickness=4)

    return frame


def _make_blank_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Create a uniform dark frame with no court features."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _make_uniform_grey_frame(width: int = 640, height: int = 480) -> np.ndarray:
    """Create a uniform grey frame -- no hardwood colour, no lines."""
    return np.full((height, width, 3), 128, dtype=np.uint8)


# -- Import test ---------------------------------------------------------------

def test_detect_court_homography_importable():
    """detect_court_homography must be importable from court_detector."""
    from src.tracking.court_detector import detect_court_homography
    assert callable(detect_court_homography)


# -- None-return cases ---------------------------------------------------------

def test_empty_list_returns_none():
    """Empty frame list must return None without raising."""
    from src.tracking.court_detector import detect_court_homography
    result = detect_court_homography([])
    assert result is None, f"Expected None for empty input, got {result}"


def test_single_blank_frame_returns_none():
    """Single blank frame has no floor/lines -- must return None."""
    from src.tracking.court_detector import detect_court_homography
    result = detect_court_homography([_make_blank_frame()])
    assert result is None, "Blank frame must return None"


def test_uniform_grey_frames_return_none():
    """Uniform grey frames have no hardwood colour -- must return None."""
    from src.tracking.court_detector import detect_court_homography
    frames = [_make_uniform_grey_frame() for _ in range(5)]
    result = detect_court_homography(frames)
    assert result is None, "Uniform grey frames must return None"


# -- Detection cases -----------------------------------------------------------

def test_synthetic_court_returns_matrix():
    """
    Synthetic hardwood+lines frame must produce a non-None (3,3) float64 matrix.

    Shape and dtype are asserted here — NOT in separate skip-able tests.
    If detect_court_homography returns None on this synthetic image it means the
    floor mask or Hough thresholds did not fire, which is a real bug.
    Check HSV ranges (H:10-30, S:40-160, V:100-230) and HoughLinesP settings
    in court_detector.py.
    """
    from src.tracking.court_detector import detect_court_homography
    frames = [_make_hardwood_frame() for _ in range(10)]
    result = detect_court_homography(frames)
    assert result is not None, (
        "Synthetic court with hardwood + white lines must return a matrix. "
        "Check HSV floor mask range (H:10-30, S:40-160, V:100-230) and "
        "HoughLinesP threshold settings in court_detector.py."
    )
    assert result.shape == (3, 3), (
        f"Matrix shape must be (3, 3), got {result.shape}"
    )
    assert result.dtype == np.float64, (
        f"Matrix dtype must be float64, got {result.dtype}"
    )


def test_single_hardwood_frame_accepted():
    """Function accepts a single-element list without crashing."""
    from src.tracking.court_detector import detect_court_homography
    frame = _make_hardwood_frame()
    # May return None or matrix -- just must not raise
    try:
        detect_court_homography([frame])
    except Exception as exc:
        pytest.fail(f"Single-frame list raised: {exc}")


def test_large_frame_list_subsampled():
    """
    60-frame list must be handled without crash (subsampling to 10 internally).
    """
    from src.tracking.court_detector import detect_court_homography
    frames = [_make_hardwood_frame() for _ in range(60)]
    try:
        detect_court_homography(frames)
    except Exception as exc:
        pytest.fail(f"60-frame list raised: {exc}")
