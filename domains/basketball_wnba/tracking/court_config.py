"""Court-specific image helpers for WNBA broadcast tracking."""

from __future__ import annotations

from typing import Any, Sequence

import cv2
import numpy as np


WNBA_COURT = {
    "length_ft": 94.0,
    "width_ft": 50.0,
    "three_pt_radius_ft": 22.146,
}


def _center_region(frame: np.ndarray) -> np.ndarray:
    """Return the central court area, excluding broadcast overlays and stands."""
    height, width = frame.shape[:2]
    return frame[height // 4 : height * 3 // 4, width // 4 : width * 3 // 4]


def sample_court_palette(frames: Sequence[np.ndarray]) -> dict[str, Any]:
    """Sample court and line brightness from representative BGR frames."""
    if not frames:
        raise ValueError("frames must contain at least one image")

    regions = []
    for frame in frames:
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("each frame must be a BGR image with shape (H, W, 3)")
        if frame.shape[0] < 4 or frame.shape[1] < 4:
            raise ValueError("frames must be at least 4 by 4 pixels")
        regions.append(_center_region(frame).reshape(-1, 3))

    pixels = np.concatenate(regions, axis=0)
    luminance = cv2.cvtColor(pixels.reshape(-1, 1, 3), cv2.COLOR_BGR2GRAY).reshape(-1)
    median_bgr = np.median(pixels, axis=0).astype(np.uint8)
    median_luminance = float(np.median(luminance))
    return {
        "court_bgr_median": tuple(int(value) for value in median_bgr),
        "line_luminance_p95": float(np.percentile(luminance, 95)),
        "is_dark_court": median_luminance < 96.0,
    }


def line_mask(frame: np.ndarray, palette: dict[str, Any]) -> np.ndarray:
    """Return a binary court-line mask suited to light or custom dark courts."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("frame must be a BGR image with shape (H, W, 3)")
    if "is_dark_court" not in palette or "line_luminance_p95" not in palette:
        raise ValueError("palette must come from sample_court_palette")

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if palette["is_dark_court"]:
        court_luminance = float(cv2.cvtColor(
            np.uint8([[palette["court_bgr_median"]]]), cv2.COLOR_BGR2GRAY
        )[0, 0])
        sampled_line = float(palette["line_luminance_p95"])
        threshold = int(np.clip(court_luminance + 0.60 * (sampled_line - court_luminance), 16, 245))
        return cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)[1]

    return cv2.inRange(frame, np.array((200, 200, 200), dtype=np.uint8), np.array((255, 255, 255), dtype=np.uint8))


def scorebug_exclude(frame_shape: Sequence[int], region: str = "auto") -> np.ndarray:
    """Return a mask excluding common lower-corner broadcast scorebug areas."""
    if len(frame_shape) < 2:
        raise ValueError("frame_shape must provide height and width")
    height, width = int(frame_shape[0]), int(frame_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("frame_shape height and width must be positive")
    if region not in {"auto", "lower_left", "lower_right", "both"}:
        raise ValueError("region must be auto, lower_left, lower_right, or both")

    mask = np.full((height, width), 255, dtype=np.uint8)
    y_start = int(height * 0.76)
    box_width = int(width * 0.38)
    if region in {"auto", "lower_left", "both"}:
        mask[y_start:, :box_width] = 0
    if region in {"auto", "lower_right", "both"}:
        mask[y_start:, width - box_width :] = 0
    return mask
