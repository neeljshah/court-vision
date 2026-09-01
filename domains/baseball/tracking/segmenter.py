"""Scene-cut detection used to isolate baseball pitch-camera segments."""
from __future__ import annotations

import cv2
import numpy as np


SMALL_FRAME_SIZE = (64, 36)
CUT_CORRELATION_THRESHOLD = 0.60


def small_gray(frame: np.ndarray) -> np.ndarray:
    """Convert a broadcast frame to the fixed-size cut signal."""
    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(frame, SMALL_FRAME_SIZE, interpolation=cv2.INTER_AREA)


def detect_cut(previous: np.ndarray, current: np.ndarray) -> bool:
    """Return whether two small grayscale frames are separated by a cut."""
    shape = SMALL_FRAME_SIZE[::-1]
    if previous.shape != shape or current.shape != shape:
        raise ValueError("Cut detection requires 64 by 36 grayscale frames")
    previous_hist = cv2.calcHist([previous], [0], None, [256], [0, 256])
    current_hist = cv2.calcHist([current], [0], None, [256], [0, 256])
    correlation = cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_CORREL)
    return bool(correlation < CUT_CORRELATION_THRESHOLD)
