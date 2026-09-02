"""Occlusion-tolerant basketball lane line calibration diagnostics.

This module intentionally does not produce tracking rows.  It detects observed
LSD line fragments and fits an image-to-court homography from declared line
correspondences only after a caller has identified all four physical lines.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Literal, Sequence

import cv2
import numpy as np


ImageLine = np.ndarray


COURT_LINE_SETS = {
    "nba_wnba": {
        "baseline": (1.0, 0.0, 0.0),
        "free_throw": (1.0, 0.0, -19.0),
        "lane_low": (0.0, 1.0, -17.0),
        "lane_high": (0.0, 1.0, -33.0),
    },
    "ncaa_legacy": {
        "baseline": (1.0, 0.0, 0.0),
        "free_throw": (1.0, 0.0, -19.0),
        "lane_low": (0.0, 1.0, -19.0),
        "lane_high": (0.0, 1.0, -31.0),
    },
}


@dataclass(frozen=True)
class ObservedSegment:
    """One observed line fragment, represented by its two image endpoints."""

    endpoints: tuple[float, float, float, float]

    @property
    def length(self) -> float:
        x1, y1, x2, y2 = self.endpoints
        return float(np.hypot(x2 - x1, y2 - y1))

    def line(self) -> ImageLine:
        x1, y1, x2, y2 = self.endpoints
        value = np.cross((x1, y1, 1.0), (x2, y2, 1.0)).astype(float)
        norm = float(np.hypot(value[0], value[1]))
        if norm == 0.0:
            raise ValueError("zero-length segment")
        return value / norm


@dataclass(frozen=True)
class CandidateLineGroup:
    """A fitted line plus its observed extent; still image-only evidence."""

    line: ImageLine
    segments: tuple[ObservedSegment, ...]
    anchor: tuple[float, float]
    direction: tuple[float, float]
    extent: tuple[float, float]

    @property
    def length(self) -> float:
        """Return observed support length along the fitted line."""
        return self.extent[1] - self.extent[0]


LaneLowImageSide = Literal["left", "right"]


def detect_lsd_segments(frame: np.ndarray, min_length: float = 60.0) -> list[ObservedSegment]:
    """Return observed grayscale LSD fragments; no brightness-mask tuning."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detected = cv2.createLineSegmentDetector().detect(gray)[0]
    if detected is None:
        return []
    segments = []
    for values in detected.reshape(-1, detected.shape[-1]):
        segment = ObservedSegment(tuple(float(value) for value in values))
        if segment.length >= min_length:
            segments.append(segment)
    return segments


def solve_from_lines(court_lines: Sequence[ImageLine], image_lines: Sequence[ImageLine]) -> np.ndarray | None:
    """Fit image-to-court H from matching homogeneous line correspondences."""
    if len(court_lines) != len(image_lines) or len(court_lines) < 4:
        return None
    image_points, court_points = [], []
    for first in range(len(court_lines)):
        for second in range(first + 1, len(court_lines)):
            image_point = np.cross(image_lines[first], image_lines[second])
            court_point = np.cross(court_lines[first], court_lines[second])
            if abs(image_point[2]) < 1e-9 or abs(court_point[2]) < 1e-9:
                continue
            image_points.append(image_point[:2] / image_point[2])
            court_points.append(court_point[:2] / court_point[2])
    if len(image_points) < 4:
        return None
    result, mask = cv2.findHomography(np.asarray(image_points, dtype=np.float32),
                                      np.asarray(court_points, dtype=np.float32), 0)
    if result is None or mask is None:
        return None
    if not np.isfinite(result).all() or abs(result[2, 2]) < 1e-12:
        return None
    return result / result[2, 2]


def line_residual(homography: np.ndarray, image_line: ImageLine, court_line: ImageLine) -> float:
    """Return angular/algebraic mismatch of one observed line after solving."""
    predicted = np.asarray(homography, dtype=float).T @ np.asarray(court_line, dtype=float)
    predicted /= np.linalg.norm(predicted[:2])
    observed = np.asarray(image_line, dtype=float) / np.linalg.norm(image_line[:2])
    return float(min(np.linalg.norm(predicted - observed), np.linalg.norm(predicted + observed)))


def candidate_line_groups(segments: Iterable[ObservedSegment], angle_deg: float = 5.0,
                          offset_px: float = 18.0) -> list[ImageLine]:
    """Merge collinear fragments into physical-image line candidates.

    Grouping joins fragments by their observed geometry, never by their list
    position. It is diagnostic-only until independent landmark validation.
    """
    return [group.line for group in candidate_line_group_details(segments, angle_deg, offset_px)]


def candidate_line_group_details(segments: Iterable[ObservedSegment], angle_deg: float = 5.0,
                                 offset_px: float = 18.0) -> list[CandidateLineGroup]:
    """Group fragments while preserving the endpoint extent needed for roles."""
    groups: list[list[ObservedSegment]] = []
    cosine = float(np.cos(np.deg2rad(angle_deg)))
    for segment in sorted(segments, key=lambda item: item.length, reverse=True):
        line = segment.line()
        for group in groups:
            reference = group[0].line()
            aligned = abs(float(np.dot(line[:2], reference[:2]))) >= cosine
            same_offset = abs(line[2] - reference[2]) <= offset_px
            if aligned and same_offset:
                group.append(segment)
                break
        else:
            groups.append([segment])
    fitted: list[CandidateLineGroup] = []
    for group in groups:
        points = []
        for segment in group:
            x1, y1, x2, y2 = segment.endpoints
            points.extend(((x1, y1), (x2, y2)))
        fit = cv2.fitLine(np.asarray(points, dtype=np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        vx, vy, x0, y0 = (float(value) for value in fit)
        line = np.array((vy, -vx, vx * y0 - vy * x0), dtype=float)
        direction = (vx, vy)
        values = [
            (x - x0) * vx + (y - y0) * vy
            for x, y in points
        ]
        fitted.append(CandidateLineGroup(
            line=line / np.hypot(line[0], line[1]), segments=tuple(group),
            anchor=(x0, y0), direction=direction,
            extent=(min(values), max(values)),
        ))
    return fitted


def assign_paint_roles(
    candidates: Sequence[CandidateLineGroup], league: str,
    lane_low_image_side: LaneLowImageSide,
    endpoint_tolerance_px: float = 45.0,
) -> dict[str, CandidateLineGroup] | None:
    """Assign four paint roles from observed termination structure only.

    ``league`` and the image side that represents ``lane_low`` are both caller
    declarations.  They are never inferred from pixels.  This function does
    not solve, validate, emit coordinates, or retain a homography.
    """
    if league not in COURT_LINE_SETS:
        raise ValueError(f"unsupported caller-declared league: {league}")
    if lane_low_image_side not in ("left", "right"):
        raise ValueError("lane_low_image_side must be 'left' or 'right'")
    if len(candidates) < 4:
        return None
    # LSD can yield many court-adjacent fragments.  Restrict the hypothesis
    # search to the strongest physical-line supports, never an image position.
    candidates = sorted(candidates, key=lambda item: item.length, reverse=True)[:16]

    best: tuple[float, tuple[CandidateLineGroup, ...], tuple[CandidateLineGroup, ...]] | None = None
    for transverse_indices in combinations(range(len(candidates)), 2):
        transverse = tuple(candidates[index] for index in transverse_indices)
        remaining = [index for index in range(len(candidates)) if index not in transverse_indices]
        for lane_indices in combinations(remaining, 2):
            lanes = tuple(candidates[index] for index in lane_indices)
            parallel = _parallel_score(transverse[0], transverse[1]) + _parallel_score(lanes[0], lanes[1])
            orthogonal = _orthogonal_score(transverse[0], lanes[0]) + _orthogonal_score(transverse[1], lanes[0])
            if parallel < 1.8 or orthogonal < 1.6:
                continue
            intersections = [_intersection(a.line, b.line) for a in transverse for b in lanes]
            if any(point is None for point in intersections):
                continue
            points = tuple(point for point in intersections if point is not None)
            termination = sum(_covers(group, point, endpoint_tolerance_px) for group in transverse + lanes for point in points)
            score = parallel + orthogonal + termination / 4.0
            if best is None or score > best[0]:
                best = (score, transverse, lanes)
    if best is None:
        return None

    _, transverse, lanes = best
    # A baseline continues past both lane intersections; the free-throw line ends there.
    baseline, free_throw = sorted(transverse, key=lambda item: item.length, reverse=True)
    lane_low, lane_high = sorted(lanes, key=lambda item: _mean_x(item), reverse=lane_low_image_side == "right")
    return {
        "baseline": baseline,
        "free_throw": free_throw,
        "lane_low": lane_low,
        "lane_high": lane_high,
    }


def _parallel_score(first: CandidateLineGroup, second: CandidateLineGroup) -> float:
    return abs(first.direction[0] * second.direction[0] + first.direction[1] * second.direction[1])


def _orthogonal_score(first: CandidateLineGroup, second: CandidateLineGroup) -> float:
    return 1.0 - _parallel_score(first, second)


def _intersection(first: ImageLine, second: ImageLine) -> tuple[float, float] | None:
    point = np.cross(first, second)
    if abs(point[2]) < 1e-9:
        return None
    return (float(point[0] / point[2]), float(point[1] / point[2]))


def _covers(group: CandidateLineGroup, point: tuple[float, float], tolerance: float) -> bool:
    x0, y0 = group.anchor
    vx, vy = group.direction
    value = (point[0] - x0) * vx + (point[1] - y0) * vy
    return group.extent[0] - tolerance <= value <= group.extent[1] + tolerance


def _mean_x(group: CandidateLineGroup) -> float:
    x0, _ = group.anchor
    vx, _ = group.direction
    return x0 + vx * (group.extent[0] + group.extent[1]) / 2.0
