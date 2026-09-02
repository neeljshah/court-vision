"""Drift-checked homography reuse for cut-bounded tennis camera locks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional

import cv2
import numpy as np

from domains.tennis.tracking.court_lines import court_line_segments


LOCK_MIN_FRESH_SOLVES = 3
DRIFT_CEILING_720P_PX = 5.0
MIN_DRIFT_INTERSECTIONS = 2

# Each label is a surveyed court intersection and the two court lines that meet
# there.  These are only used to locate *current-frame* image evidence.
_INTERSECTION_LINES = {
    "near_left": ((0.0, 0.0), ((0.0, 0.0), (0.0, 36.0)), ((0.0, 0.0), (78.0, 0.0))),
    "near_right": ((0.0, 36.0), ((0.0, 0.0), (0.0, 36.0)), ((0.0, 36.0), (78.0, 36.0))),
    "far_left": ((78.0, 0.0), ((78.0, 0.0), (78.0, 36.0)), ((0.0, 0.0), (78.0, 0.0))),
    "far_right": ((78.0, 36.0), ((78.0, 0.0), (78.0, 36.0)), ((0.0, 36.0), (78.0, 36.0))),
    "service_t_near": ((18.0, 18.0), ((18.0, 4.5), (18.0, 31.5)), ((18.0, 18.0), (60.0, 18.0))),
    "service_t_far": ((60.0, 18.0), ((60.0, 4.5), (60.0, 31.5)), ((18.0, 18.0), (60.0, 18.0))),
}


@dataclass(frozen=True)
class DriftCheck:
    """Current-frame evidence result for a candidate lock homography."""

    residual_px: Optional[float]
    evidence_count: int

    @property
    def measured(self) -> bool:
        return self.residual_px is not None


def _normalise_homography(homography: np.ndarray) -> np.ndarray:
    value = np.asarray(homography, dtype=float).reshape(3, 3)
    if not np.isfinite(value).all() or abs(value[2, 2]) < 1e-12:
        raise ValueError("homography must be finite with non-zero scale")
    return value / value[2, 2]


def geometric_median_homography(homographies: list[np.ndarray]) -> np.ndarray:
    """Return the Weiszfeld geometric median of scale-normalized matrices."""
    if len(homographies) < LOCK_MIN_FRESH_SOLVES:
        raise ValueError("camera lock requires at least three fresh solves")
    points = np.stack([_normalise_homography(item).reshape(-1) for item in homographies])
    estimate = np.median(points, axis=0)
    for _ in range(100):
        distances = np.linalg.norm(points - estimate, axis=1)
        if np.any(distances < 1e-10):
            estimate = points[np.argmin(distances)]
            break
        weights = 1.0 / np.maximum(distances, 1e-10)
        updated = np.average(points, axis=0, weights=weights)
        if np.linalg.norm(updated - estimate) < 1e-9:
            estimate = updated
            break
        estimate = updated
    result = _normalise_homography(estimate.reshape(3, 3))
    if abs(np.linalg.det(result)) < 1e-12:
        raise ValueError("geometric median produced a singular homography")
    return result


def _project(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(np.asarray(points, dtype=np.float32).reshape(1, -1, 2), homography)[0]


def drift_from_corners(homography: np.ndarray, corners: np.ndarray) -> DriftCheck:
    """Measure lock reprojection against a fresh full-gate corner observation."""
    observed = np.asarray(corners, dtype=np.float32).reshape(-1, 2)
    if len(observed) != 4:
        return DriftCheck(None, 0)
    court = np.float32(((0, 0), (0, 36), (78, 0), (78, 36)))
    expected = _project(court, np.linalg.inv(_normalise_homography(homography)))
    return DriftCheck(float(np.median(np.linalg.norm(expected - observed, axis=1))), len(observed))


def _line_distance(point: np.ndarray, line: np.ndarray) -> float:
    start, end = line[:2], line[2:]
    direction = end - start
    length = float(np.linalg.norm(direction))
    if length < 1e-6:
        return float("inf")
    return float(abs(np.cross(direction, point - start)) / length)


def _closest_line(expected: np.ndarray, raw_lines: list[np.ndarray], max_distance: float) -> Optional[np.ndarray]:
    direction = expected[2:] - expected[:2]
    length = float(np.linalg.norm(direction))
    if length < 1e-6:
        return None
    unit = direction / length
    candidates: list[tuple[float, np.ndarray]] = []
    for raw in raw_lines:
        raw_direction = raw[2:] - raw[:2]
        raw_length = float(np.linalg.norm(raw_direction))
        if raw_length < 1e-6 or abs(float(np.dot(unit, raw_direction / raw_length))) < 0.985:
            continue
        distance = (_line_distance(raw[:2], expected) + _line_distance(raw[2:], expected)) / 2.0
        if distance <= max_distance:
            candidates.append((distance, raw))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def detected_intersections(frame: np.ndarray, homography: np.ndarray) -> Mapping[str, np.ndarray]:
    """Return presently visible, line-derived court intersections for a lock."""
    height, width = frame.shape[:2]
    scale = height / 720.0
    raw_lines = court_line_segments(frame, threshold=30, min_length=max(30, width // 18), max_gap=18)
    if not raw_lines:
        return {}
    to_image = np.linalg.inv(_normalise_homography(homography))
    result: dict[str, np.ndarray] = {}
    for name, (court_point, first, second) in _INTERSECTION_LINES.items():
        expected_first = _project(np.float32(first), to_image).reshape(-1)
        expected_second = _project(np.float32(second), to_image).reshape(-1)
        observed_first = _closest_line(expected_first, raw_lines, 20.0 * scale)
        observed_second = _closest_line(expected_second, raw_lines, 20.0 * scale)
        if observed_first is None or observed_second is None:
            continue
        first_h = np.cross(np.append(observed_first[:2], 1.0), np.append(observed_first[2:], 1.0))
        second_h = np.cross(np.append(observed_second[:2], 1.0), np.append(observed_second[2:], 1.0))
        point_h = np.cross(first_h, second_h)
        if abs(point_h[2]) < 1e-8:
            continue
        point = (point_h[:2] / point_h[2]).astype(np.float32)
        expected = _project(np.float32((court_point,)), to_image)[0]
        if np.linalg.norm(point - expected) <= 30.0 * scale:
            result[name] = point
    return result


def drift_from_frame(homography: np.ndarray, frame: np.ndarray) -> DriftCheck:
    """Measure a lock against current-frame line intersections, or fail closed."""
    observed = detected_intersections(frame, homography)
    if len(observed) < MIN_DRIFT_INTERSECTIONS:
        return DriftCheck(None, len(observed))
    to_image = np.linalg.inv(_normalise_homography(homography))
    distances = []
    for name, point in observed.items():
        expected = _project(np.float32((_INTERSECTION_LINES[name][0],)), to_image)[0]
        distances.append(float(np.linalg.norm(point - expected)))
    return DriftCheck(float(np.median(distances)), len(distances))


class CameraLock:
    """A cut-bounded robust homography accumulator and drift checker."""

    def __init__(self) -> None:
        self.lock_id = 0
        self._fresh: list[np.ndarray] = []
        self.homography: Optional[np.ndarray] = None

    @property
    def fresh_solve_count(self) -> int:
        return len(self._fresh)

    @property
    def ready(self) -> bool:
        return self.homography is not None

    def reset(self) -> None:
        self.lock_id += 1
        self._fresh = []
        self.homography = None

    def add_fresh_solve(self, homography: np.ndarray) -> None:
        self._fresh.append(_normalise_homography(homography))
        if len(self._fresh) >= LOCK_MIN_FRESH_SOLVES:
            self.homography = geometric_median_homography(self._fresh)

    def accepts(self, check: DriftCheck, frame_height: int) -> bool:
        ceiling = DRIFT_CEILING_720P_PX * frame_height / 720.0
        return check.measured and bool(check.residual_px <= ceiling)

    def resolve(self, frame: np.ndarray, fresh: Optional[np.ndarray],
                corners: Optional[np.ndarray]) -> tuple[Optional[np.ndarray], str, str, float, int]:
        """Select a fresh solve or evidence-checked reuse for one frame."""
        if fresh is not None:
            self.add_fresh_solve(fresh)
        if self.ready:
            check = (drift_from_corners(self.homography, corners) if corners is not None
                     else drift_from_frame(self.homography, frame))
            drift = float(check.residual_px) if check.residual_px is not None else float("nan")
            if self.accepts(check, frame.shape[0]):
                return (fresh if fresh is not None else self.homography,
                        "solved" if fresh is not None else "camera_lock_drift_checked",
                        "ready", drift, check.evidence_count)
            self.reset()
            if fresh is not None:
                self.add_fresh_solve(fresh)
                return fresh, "solved", "ready", drift, check.evidence_count
            return None, "unavailable", "unsolved_drift", drift, check.evidence_count
        if fresh is not None:
            check = drift_from_corners(fresh, corners)
            drift = float(check.residual_px) if check.residual_px is not None else float("nan")
            return fresh, "solved", "ready", drift, check.evidence_count
        return None, "unavailable", "calibration_unavailable", float("nan"), 0
