"""Learned-keypoint camera calibration shared by court and pitch sports.

Homographies returned here map image pixels to canonical sport coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import cv2
import numpy as np
from scipy.signal import savgol_filter

Point = Tuple[float, float]
Detection = Tuple[float, float, float]
Landmarks = Dict[str, Point]


CANONICAL_LANDMARKS: Dict[str, Landmarks] = {
    "basketball": {
        "court_bl": (0.0, 0.0), "court_br": (94.0, 0.0),
        "court_tr": (94.0, 50.0), "court_tl": (0.0, 50.0),
        "left_paint_bl": (0.0, 17.0), "left_paint_br": (19.0, 17.0),
        "left_paint_tr": (19.0, 33.0), "left_paint_tl": (0.0, 33.0),
        "right_paint_bl": (75.0, 17.0), "right_paint_br": (94.0, 17.0),
        "right_paint_tr": (94.0, 33.0), "right_paint_tl": (75.0, 33.0),
        "center_circle": (47.0, 25.0),
        "left_ft_circle": (19.0, 25.0), "right_ft_circle": (75.0, 25.0),
    },
    "tennis": {
        "doubles_bl": (0.0, 0.0), "doubles_br": (78.0, 0.0),
        "doubles_tr": (78.0, 36.0), "doubles_tl": (0.0, 36.0),
        "singles_bl": (0.0, 4.5), "singles_br": (78.0, 4.5),
        "singles_tr": (78.0, 31.5), "singles_tl": (0.0, 31.5),
        "net_post_bottom": (39.0, 0.0), "net_post_top": (39.0, 36.0),
        "left_service_t": (21.0, 18.0), "right_service_t": (57.0, 18.0),
    },
    "soccer": {
        "pitch_bl": (0.0, 0.0), "pitch_br": (105.0, 0.0),
        "pitch_tr": (105.0, 68.0), "pitch_tl": (0.0, 68.0),
        "left_box_bl": (0.0, 13.84), "left_box_br": (16.5, 13.84),
        "left_box_tr": (16.5, 54.16), "left_box_tl": (0.0, 54.16),
        "right_box_bl": (88.5, 13.84), "right_box_br": (105.0, 13.84),
        "right_box_tr": (105.0, 54.16), "right_box_tl": (88.5, 54.16),
        "center_circle": (52.5, 34.0),
        "center_circle_top": (52.5, 24.85),
        "center_circle_bottom": (52.5, 43.15),
    },
}


class KeypointProvider(Protocol):
    """Supplies named pixel keypoints for one video frame."""

    def detect(self, frame: Any) -> Dict[str, Detection]:
        """Return landmark name to (pixel_x, pixel_y, confidence)."""


def _correspondences(
    detections: Dict[str, Detection], sport: str, min_conf: float,
) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Collect valid named pixel-to-court correspondences."""
    if sport not in CANONICAL_LANDMARKS:
        raise ValueError(f"Unsupported sport: {sport!r}")
    pixels: List[Point] = []
    court: List[Point] = []
    names: List[str] = []
    for name, point in CANONICAL_LANDMARKS[sport].items():
        detection = detections.get(name)
        if detection is None or len(detection) != 3:
            continue
        px, py, confidence = detection
        if confidence < min_conf or not np.isfinite((px, py, confidence)).all():
            continue
        pixels.append((float(px), float(py)))
        court.append(point)
        names.append(name)
    return np.asarray(pixels, dtype=np.float32), np.asarray(court, dtype=np.float32), names


def _find_homography(
    detections: Dict[str, Detection], sport: str, min_conf: float, min_points: int,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], List[str]]:
    pixels, court, names = _correspondences(detections, sport, min_conf)
    if len(names) < min_points:
        return None, None, names
    homography, mask = cv2.findHomography(pixels, court, cv2.RANSAC, 3.0)
    if homography is None or mask is None or int(mask.ravel().sum()) < min_points:
        return None, None, names
    if not np.isfinite(homography).all() or abs(homography[2, 2]) < 1e-12:
        return None, None, names
    return homography / homography[2, 2], mask.ravel().astype(bool), names


def solve_homography(
    detections: Dict[str, Detection], sport: str, min_conf: float = 0.3,
    min_points: int = 4,
) -> Optional[np.ndarray]:
    """Fit an image-pixel to canonical-court homography with RANSAC."""
    homography, _, _ = _find_homography(detections, sport, min_conf, min_points)
    return homography


def project_points(homography: np.ndarray, points: Sequence[Point]) -> np.ndarray:
    """Project pixel points through a 3x3 homography."""
    matrix = np.asarray(homography, dtype=float)
    if matrix.shape != (3, 3):
        raise ValueError("homography must have shape (3, 3)")
    xy = np.asarray(points, dtype=float)
    if xy.size == 0:
        return np.empty((0, 2), dtype=float)
    xy = xy.reshape(-1, 2)
    homogeneous = np.column_stack((xy, np.ones(len(xy))))
    projected = homogeneous @ matrix.T
    return projected[:, :2] / projected[:, 2:3]


@dataclass
class CalibrationResult:
    """One temporal calibration update."""

    homography: Optional[np.ndarray]
    mean_reprojection_error: Optional[float]
    recompute: bool
    reused_last_good: bool

    @property
    def H(self) -> Optional[np.ndarray]:
        """Short alias for consumers that conventionally name homography H."""
        return self.homography


class TemporalCalibrator:
    """Smooth valid frame homographies and safely bridge failed detections."""

    def __init__(
        self, sport: str, provider: Optional[KeypointProvider] = None,
        min_conf: float = 0.3, min_points: int = 4, drift_threshold: float = 1.5,
    ) -> None:
        if sport not in CANONICAL_LANDMARKS:
            raise ValueError(f"Unsupported sport: {sport!r}")
        self.sport = sport
        self.provider = provider
        self.min_conf = min_conf
        self.min_points = min_points
        self.drift_threshold = drift_threshold
        self._params: List[np.ndarray] = []
        self.last_good_homography: Optional[np.ndarray] = None

    @staticmethod
    def _parameters(homography: np.ndarray) -> np.ndarray:
        h = homography / homography[2, 2]
        return np.array([h[0, 0], h[0, 1], h[0, 2], h[1, 0], h[1, 1], h[1, 2],
                         h[2, 0], h[2, 1]], dtype=float)

    @staticmethod
    def _from_parameters(params: np.ndarray) -> np.ndarray:
        return np.array([[params[0], params[1], params[2]],
                         [params[3], params[4], params[5]],
                         [params[6], params[7], 1.0]], dtype=float)

    def _smoothed(self) -> np.ndarray:
        if len(self._params) < 9:
            return self._from_parameters(self._params[-1])
        values = np.vstack(self._params[-9:])
        return self._from_parameters(savgol_filter(values, 9, 2, axis=0, mode="interp")[-1])

    def update(self, detections: Dict[str, Detection]) -> CalibrationResult:
        """Calibrate one detection dictionary, reusing the latest good result on failure."""
        raw_h, inliers, names = _find_homography(
            detections, self.sport, self.min_conf, self.min_points,
        )
        if raw_h is None or inliers is None:
            return CalibrationResult(self.last_good_homography, None, False,
                                     self.last_good_homography is not None)
        self._params.append(self._parameters(raw_h))
        smoothed_h = self._smoothed()
        inlier_pixels = np.asarray(
            [(detections[name][0], detections[name][1]) for name, keep in zip(names, inliers) if keep],
            dtype=float,
        )
        inlier_court = np.asarray(
            [CANONICAL_LANDMARKS[self.sport][name] for name, keep in zip(names, inliers) if keep],
            dtype=float,
        )
        error = float(np.mean(np.linalg.norm(project_points(smoothed_h, inlier_pixels) - inlier_court, axis=1)))
        self.last_good_homography = smoothed_h
        return CalibrationResult(smoothed_h, error, error > self.drift_threshold, False)

    def calibrate(self, detections: Dict[str, Detection]) -> CalibrationResult:
        """Alias for update, retained for a direct calibration API."""
        return self.update(detections)

    def calibrate_frame(self, frame: Any) -> CalibrationResult:
        """Detect and calibrate a frame using the configured keypoint provider."""
        if self.provider is None:
            raise ValueError("A KeypointProvider is required for calibrate_frame")
        return self.update(self.provider.detect(frame))
