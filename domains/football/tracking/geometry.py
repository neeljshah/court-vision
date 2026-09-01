"""Fresh football calibration from named painted-yard and hash line correspondences."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from domains.football.tracking.absolute_anchor import PaintedYardAnchorProvider
from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction, pencil_is_uniform

FIELD_WIDTH_FT = 160.0
FIELD_LENGTH_FT = 360.0
# NFL Rule 1, Field Markings 10: professional inbounds hashes are 70 ft 9 in
# from each sideline; on the 160-ft field that leaves 18 ft 6 in between rows.
# Source: https://operations.nfl.com/rules-officiating/2026-nfl-rulebook
NFL_HASH_ROW_SEPARATION_FT = 18.5
NCAA_HASH_ROW_SEPARATION_FT = 40.0
# NFL Football Operations: yard lines are painted at five-yard intervals.
# Source: https://operations.nfl.com/football-101/terms-glossary/glossary-terms-list/yard-lines/
YARD_LINE_SPACING_FT = 15.0  # 5 yd * 3 ft.
MAX_YARD_LINES = int(FIELD_LENGTH_FT / YARD_LINE_SPACING_FT) + 1
MIN_YARD_LINES = 4
GRID_AGREEMENT_FT = 2.0
HASH_MIN_LENGTH_PX = 8
HASH_MAX_FRACTION = 0.12
HASH_ROW_CLUSTER_PX = 12.0


@dataclass(frozen=True)
class FootballFieldSpec:
    """Rule-set dimensions used only after the caller names a field level."""

    name: str
    hash_row_separation_ft: float


FIELD_SPECS = {
    "nfl": FootballFieldSpec("nfl", NFL_HASH_ROW_SEPARATION_FT),
    "ncaa": FootballFieldSpec("ncaa", NCAA_HASH_ROW_SEPARATION_FT),
}


def field_spec(field_level: str) -> FootballFieldSpec:
    """Return named rule-set dimensions; never infer a league from pixels."""
    try:
        return FIELD_SPECS[field_level.lower()]
    except (AttributeError, KeyError) as exc:
        raise ValueError("field_level must be one of: %s" % ", ".join(FIELD_SPECS)) from exc


class FootballGeometryMixin:
    """Fit an image-to-football-field transform for one freshly observed frame."""

    def __init__(self, field_level: Optional[str] = None) -> None:
        self.absolute_anchor_provider = PaintedYardAnchorProvider()
        self.field_level = field_level.lower() if field_level is not None else None
        if self.field_level is not None:
            field_spec(self.field_level)

    @staticmethod
    def _line_coefficients(line: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = map(float, line)
        result = np.array((y1 - y2, x2 - x1, x1 * y2 - x2 * y1), dtype=float)
        return result / np.hypot(result[0], result[1])

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] +
                            [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return FootballGeometryMixin._line_coefficients(
            np.array((x0 - 9999 * vx, y0 - 9999 * vy, x0 + 9999 * vx, y0 + 9999 * vy)))

    @staticmethod
    def _line_distance(line: np.ndarray, point: tuple[float, float]) -> float:
        return abs(float(line[0] * point[0] + line[1] * point[1] + line[2]))

    @staticmethod
    def _segments(frame: np.ndarray, minimum: float) -> list[np.ndarray]:
        """Detect grayscale LSD segments, deliberately without a brightness mask."""
        found = cv2.createLineSegmentDetector().detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))[0]
        if found is None:
            return []
        return [segment.astype(float) for segment in found[:, 0, :]
                if np.hypot(segment[2] - segment[0], segment[3] - segment[1]) >= minimum]

    def _line_groups(self, frame: np.ndarray) -> list[list[np.ndarray]]:
        groups: list[list[np.ndarray]] = []
        for item in self._segments(frame, max(30.0, frame.shape[1] / 12.0)):
            angle = np.arctan2(item[3] - item[1], item[2] - item[0]) % np.pi
            for group in groups:
                ref = group[0]
                ref_angle = np.arctan2(ref[3] - ref[1], ref[2] - ref[0]) % np.pi
                if abs(((angle - ref_angle + np.pi / 2) % np.pi) - np.pi / 2) < np.deg2rad(8):
                    group.append(item)
                    break
            else:
                groups.append([item])
        return groups

    def family_from_segments(self, segments: list[np.ndarray]) -> list[np.ndarray]:
        """Cluster segments from either detector with identical football logic."""
        groups: list[list[np.ndarray]] = []
        for item in segments:
            angle = np.arctan2(item[3] - item[1], item[2] - item[0]) % np.pi
            for group in groups:
                ref = group[0]
                ref_angle = np.arctan2(ref[3] - ref[1], ref[2] - ref[0]) % np.pi
                if abs(((angle - ref_angle + np.pi / 2) % np.pi) - np.pi / 2) < np.deg2rad(8):
                    group.append(item)
                    break
            else:
                groups.append([item])
        if not groups:
            return []
        group = max(groups, key=len)
        direction = np.mean([np.arctan2(line[3] - line[1], line[2] - line[0]) % np.pi
                             for line in group])
        normal = np.array((-np.sin(direction), np.cos(direction)))
        clusters: list[list[np.ndarray]] = []
        for line in sorted(group, key=lambda value: np.dot((value[:2] + value[2:]) / 2, normal)):
            offset = float(np.dot((line[:2] + line[2:]) / 2, normal))
            if not clusters or abs(offset - np.mean([np.dot((x[:2] + x[2:]) / 2, normal)
                                                      for x in clusters[-1]])) > 8:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        return [self._fit_line(cluster) for cluster in clusters]

    def detect_yard_line_family(self, frame: np.ndarray) -> list[np.ndarray]:
        """Return cross-ratio-testable five-yard field lines from LSD segments."""
        return self.family_from_segments([line for group in self._line_groups(frame) for line in group])

    @staticmethod
    def line_homography(court_lines: list[np.ndarray], image_lines: list[np.ndarray]) -> Optional[np.ndarray]:
        """Solve H from l_c proportional to H^-T l_i, with four-plus named lines."""
        if len(court_lines) != len(image_lines) or len(court_lines) < 4:
            return None
        equations = []
        for court, image in zip(court_lines, image_lines):
            court = np.asarray(court, dtype=float) / np.linalg.norm(court[:2])
            image = np.asarray(image, dtype=float) / np.linalg.norm(image[:2])
            x, y, w = image
            equations.extend(([0, 0, 0, -court[2] * x, -court[2] * y, -court[2] * w,
                               court[1] * x, court[1] * y, court[1] * w],
                              [court[2] * x, court[2] * y, court[2] * w, 0, 0, 0,
                               -court[0] * x, -court[0] * y, -court[0] * w]))
        _, _, vectors = np.linalg.svd(np.asarray(equations, dtype=float))
        homography = vectors[-1].reshape(3, 3).T
        if not np.isfinite(homography).all() or abs(float(homography[2, 2])) < 1e-10:
            return None
        return homography / homography[2, 2]

    def _hash_row_lines(self, frame: np.ndarray, yard_lines: list[np.ndarray]) -> list[np.ndarray]:
        """Fit hash rows from repeated short painted marks, not virtual graphics."""
        if not yard_lines:
            return []
        yard_angle = np.arctan2(-yard_lines[0][0], yard_lines[0][1]) % np.pi
        marks = []
        for segment in self._segments(frame, HASH_MIN_LENGTH_PX):
            length = float(np.hypot(segment[2] - segment[0], segment[3] - segment[1]))
            angle = np.arctan2(segment[3] - segment[1], segment[2] - segment[0]) % np.pi
            delta = abs(((angle - yard_angle + np.pi / 2) % np.pi) - np.pi / 2)
            if length <= frame.shape[1] * HASH_MAX_FRACTION and delta < np.deg2rad(9):
                marks.append(segment)
        if len(marks) < 6:
            return []
        direction = np.array((-yard_lines[0][1], yard_lines[0][0]))
        normal = np.array((-direction[1], direction[0])) / np.linalg.norm(direction)
        clusters: list[list[np.ndarray]] = []
        for mark in sorted(marks, key=lambda value: np.dot((value[:2] + value[2:]) / 2, normal)):
            position = float(np.dot((mark[:2] + mark[2:]) / 2, normal))
            if not clusters or abs(position - np.mean([np.dot((item[:2] + item[2:]) / 2, normal)
                                                       for item in clusters[-1]])) > HASH_ROW_CLUSTER_PX:
                clusters.append([mark])
            else:
                clusters[-1].append(mark)
        rows = [self._fit_line(cluster) for cluster in clusters if len(cluster) >= 3]
        return rows if len(rows) == 2 else []

    def homography_from_yard_lines(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Return a fresh NCAA transform, or fail closed without an independent scale proof."""
        stats = self.last_fit_stats = {"reject": None, "field_level": self.field_level}
        def fail(reason: str) -> None:
            stats["reject"] = reason
            return None
        stats["green_frac"] = field_view_fraction(frame)
        if stats["green_frac"] < MIN_FIELD_VIEW_GREEN:
            return fail("not_field_view")
        if self.field_level is None:
            return fail("field_level_unset")
        anchor = self.absolute_anchor_provider.detect(frame)
        if anchor is None:
            return fail("absolute_anchor_unavailable")
        yards = self.detect_yard_line_family(frame)
        stats["n_yard"] = len(yards)
        if not MIN_YARD_LINES <= len(yards) <= MAX_YARD_LINES:
            return fail("family_size")
        if not pencil_is_uniform(yards, frame.shape):
            return fail("family_not_uniform")
        hashes = self._hash_row_lines(frame, yards)
        stats["hash_rows"] = len(hashes)
        if len(hashes) != 2:
            return fail("independent_scale_unavailable")
        # Two image hash rows establish neither their physical separation nor
        # their near/far identity. Naming them (60, 100) here would simply
        # assume NCAA scale, the coordinate laundering this adapter must avoid.
        # Keep the generic line solver above available for a frame that has an
        # independently measured ratio, but emit nothing until that evidence is
        # supplied by a real high-resolution calibration sample.
        return fail("independent_scale_unavailable")

    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        candidate = self.homography_from_yard_lines(frame)
        if candidate is None:
            self._reset_segment()
            return None
        if self._homography is None:
            self._homography = candidate
            return None
        height, width = frame.shape[:2]
        grid = np.float32([[[x * width, y * height]] for y in (0.55, 0.7, 0.85)
                           for x in (0.2, 0.5, 0.8)])
        old = cv2.perspectiveTransform(grid, self._homography)[:, 0, :]
        fresh = cv2.perspectiveTransform(grid, candidate)[:, 0, :]
        if not (np.isfinite(old).all() and np.isfinite(fresh).all() and
                float(np.median(np.linalg.norm(old - fresh, axis=1))) <= GRID_AGREEMENT_FT):
            self._reset_segment()
            self._homography = candidate
            return None
        self._homography = candidate
        return candidate
