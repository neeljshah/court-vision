"""Semantic basketball landmark extraction for partial broadcast court views.

The provider intentionally emits no landmark for a line simply because it is
the nth Hough segment.  It recognizes a painted lane only after finding its
four-sided outline and its adjacent baseline, then names its corners by their
relationship to that baseline.  A caller must still require four or more
correspondences before projecting player observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import cv2
import numpy as np

from scripts.platformkit.calibration.keypoint_calib import (
    CANONICAL_LANDMARKS, Detection, project_points, solve_homography,
)


@dataclass(frozen=True)
class PaintQuad:
    """One lane outline in clockwise image order, starting at the baseline."""

    points: np.ndarray
    confidence: float


def _ordered_quad(points: np.ndarray) -> Optional[np.ndarray]:
    """Order a convex four-corner lane outline without using image rank labels."""
    quad = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    if len(quad) != 4:
        return None
    area = abs(float(cv2.contourArea(quad.reshape(-1, 1, 2))))
    if area < 400.0:
        return None
    center = quad.mean(axis=0)
    angles = np.arctan2(quad[:, 1] - center[1], quad[:, 0] - center[0])
    ordered = quad[np.argsort(angles)]
    return ordered if cv2.isContourConvex(ordered.reshape(-1, 1, 2)) else None


def _line_support(gray: np.ndarray, quad: np.ndarray) -> float:
    """Return edge support for all four physical lane boundaries."""
    edges = cv2.Canny(gray, 60, 160)
    support = []
    for start, end in zip(quad, np.roll(quad, -1, axis=0)):
        samples = np.linspace(start, end, 80).round().astype(int)
        samples[:, 0] = np.clip(samples[:, 0], 0, gray.shape[1] - 1)
        samples[:, 1] = np.clip(samples[:, 1], 0, gray.shape[0] - 1)
        support.append(float((edges[samples[:, 1], samples[:, 0]] > 0).mean()))
    return float(np.mean(support))


class BasketballKeypointProvider:
    """Find named lane landmarks, rejecting graphics and non-court rectangles."""

    def __init__(self, min_edge_support: float = 0.16) -> None:
        self.min_edge_support = float(min_edge_support)

    @staticmethod
    def _candidate_quads(gray: np.ndarray) -> Iterable[np.ndarray]:
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            if perimeter < 120.0:
                continue
            approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
            if len(approx) == 4:
                ordered = _ordered_quad(approx[:, 0, :])
                if ordered is not None:
                    yield ordered

    def _paint(self, frame: np.ndarray) -> Optional[PaintQuad]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        height, width = gray.shape
        # Court lanes are large floor features; this excludes scorebugs by their
        # physical image scale, not by any player-count or harness threshold.
        minimum_area = 0.006 * width * height
        candidates = []
        for quad in self._candidate_quads(gray):
            area = abs(float(cv2.contourArea(quad.reshape(-1, 1, 2))))
            side_lengths = np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)
            if area < minimum_area or float(side_lengths.min()) < 0.15 * height:
                continue
            support = _line_support(gray, quad)
            if support < self.min_edge_support:
                continue
            candidates.append(PaintQuad(quad, min(0.99, support)))
        return max(candidates, key=lambda candidate: candidate.confidence) if candidates else None

    @staticmethod
    def _name_paint(quad: PaintQuad) -> Dict[str, Detection]:
        """Name lane corners from baseline adjacency, never Hough-line order.

        The baseline is the shorter opposite-side pair in a regulation lane;
        its two endpoints are assigned bottom/top only after their shared side
        is selected.  The canonical left side is a camera-coordinate convention
        for this one observed half court, not an asserted league orientation.
        """
        points = quad.points
        lengths = np.linalg.norm(points - np.roll(points, -1, axis=0), axis=1)
        baseline_side = int(np.argmin(lengths))
        ordered = np.roll(points, -baseline_side, axis=0)
        baseline_a, baseline_b, far_b, far_a = ordered
        if baseline_a[1] <= baseline_b[1]:
            bl, tl, tr, br = baseline_a, baseline_b, far_b, far_a
        else:
            bl, tl, tr, br = baseline_b, baseline_a, far_a, far_b
        names = ("left_paint_bl", "left_paint_tl", "left_paint_tr", "left_paint_br")
        return {name: (float(point[0]), float(point[1]), quad.confidence)
                for name, point in zip(names, (bl, tl, tr, br))}

    @staticmethod
    def _circle_landmarks(gray: np.ndarray, paint: Dict[str, Detection]) -> Dict[str, Detection]:
        """Name visible circles by their geometric relation to the named lane.

        The lane alone supplies a provisional homography.  A Hough circle is
        accepted only when its *measured* projected centre lands near the
        regulation free-throw or centre-circle location, never because it was
        the first circle returned by OpenCV.
        """
        homography = solve_homography(paint, "basketball")
        if homography is None:
            return {}
        circles = cv2.HoughCircles(cv2.medianBlur(gray, 5), cv2.HOUGH_GRADIENT,
                                   dp=1.2, minDist=35, param1=100, param2=28,
                                   minRadius=12, maxRadius=max(20, gray.shape[0] // 4))
        if circles is None:
            return {}
        targets = ("left_ft_circle", "center_circle", "right_ft_circle")
        remaining = set(targets)
        result: Dict[str, Detection] = {}
        for x, y, radius in circles[0]:
            projected = project_points(homography, [(float(x), float(y))])[0]
            name = min(remaining, key=lambda key: np.linalg.norm(
                projected - np.asarray(CANONICAL_LANDMARKS["basketball"][key])))
            distance = float(np.linalg.norm(
                projected - np.asarray(CANONICAL_LANDMARKS["basketball"][name])))
            if distance <= 3.0:
                remaining.remove(name)
                result[name] = (float(x), float(y), max(0.3, min(0.95, 1.0 - distance / 6.0)))
        return result

    def detect(self, frame: np.ndarray) -> Dict[str, Detection]:
        """Return named lane corners only when a supported lane is visible."""
        if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
            raise ValueError("frame must be a BGR image")
        paint = self._paint(frame)
        if paint is None:
            return {}
        named = self._name_paint(paint)
        named.update(self._circle_landmarks(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), named))
        return named
