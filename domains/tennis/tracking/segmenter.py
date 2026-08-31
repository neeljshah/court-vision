"""Broadcast scene-cut detection for tennis tracking calibration."""
from __future__ import annotations

import cv2
import numpy as np


SMALL_FRAME_SIZE = (64, 36)
CUT_CORRELATION_THRESHOLD = 0.6


def small_gray(frame: np.ndarray) -> np.ndarray:
    """Convert a broadcast frame to the fixed-size grayscale cut signal."""
    if frame.ndim == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(frame, SMALL_FRAME_SIZE, interpolation=cv2.INTER_AREA)


def detect_cut(prev_gray_small: np.ndarray, cur_gray_small: np.ndarray) -> bool:
    """Return whether two 64 by 36 grayscale frames are a scene cut."""
    previous = np.asarray(prev_gray_small, dtype=np.uint8)
    current = np.asarray(cur_gray_small, dtype=np.uint8)
    if previous.shape != SMALL_FRAME_SIZE[::-1] or current.shape != SMALL_FRAME_SIZE[::-1]:
        raise ValueError("Cut detection requires 64 by 36 grayscale frames")
    previous_hist = cv2.calcHist([previous], [0], None, [256], [0, 256])
    current_hist = cv2.calcHist([current], [0], None, [256], [0, 256])
    correlation = cv2.compareHist(previous_hist, current_hist, cv2.HISTCMP_CORREL)
    return bool(correlation < CUT_CORRELATION_THRESHOLD)
