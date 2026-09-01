"""Football field-geometry helpers."""
from __future__ import annotations

from typing import Optional

import cv2
import numpy as np

from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction, pencil_is_uniform
from domains.football.tracking.absolute_anchor import PaintedYardAnchorProvider


FIELD_WIDTH_FT = 160.0
FIELD_LENGTH_FT = 360.0
YARD_LINE_SPACING_FT = 15.0
MAX_YARD_LINES = int(FIELD_LENGTH_FT / YARD_LINE_SPACING_FT) + 1
MIN_CORRESPONDENCES = 8
MIN_YARD_LINES = 4
MIN_INLIER_FRACTION = 0.8
MAX_FIT_RMSE_FT = 3.0
MAX_FT_PER_PIXEL = 2.0
GRID_AGREEMENT_FT = 2.0
FIELD_LEVEL_RATIOS = {"ncaa": 40.0 / 15.0, "nfl": 18.5 / 15.0, "high_school": 53.33 / 15.0}
FIELD_LEVEL_RATIO_TOLERANCE = 0.15
HASH_MIN_LENGTH_PX = 8
HASH_MAX_FRACTION = 0.12
HASH_ROW_CLUSTER_FT = 4.0


class FootballGeometryMixin:
    def __init__(self) -> None:
        self.absolute_anchor_provider = PaintedYardAnchorProvider()

    @staticmethod
    def field_level_from_ratio(hash_separation_px: float, yard_spacing_px: float) -> Optional[str]:
        """Select a field level from independent painted-line separations."""
        if yard_spacing_px <= 0.0:
            return None
        ratio = hash_separation_px / yard_spacing_px
        matches = [name for name, expected in FIELD_LEVEL_RATIOS.items()
                   if abs(ratio - expected) <= FIELD_LEVEL_RATIO_TOLERANCE * expected]
        return matches[0] if len(matches) == 1 else None
    @staticmethod
    def _line_coefficients(line: np.ndarray) -> np.ndarray:
        x1, y1, x2, y2 = map(float, line)
        result = np.array((y1 - y2, x2 - x1, x1 * y2 - x2 * y1), dtype=float)
        return result / np.hypot(result[0], result[1])

    @staticmethod
    def _intersection(first: np.ndarray, second: np.ndarray) -> Optional[np.ndarray]:
        point = np.cross(first, second)
        return None if abs(point[2]) < 1e-8 else (point[:2] / point[2]).astype(np.float32)

    @staticmethod
    def _fit_line(lines: list[np.ndarray]) -> np.ndarray:
        points = np.asarray([[line[0], line[1]] for line in lines] + [[line[2], line[3]] for line in lines], dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01).reshape(-1)
        return FootballGeometryMixin._line_coefficients(np.array((x0 - 9999 * vx, y0 - 9999 * vy, x0 + 9999 * vx, y0 + 9999 * vy)))

    @staticmethod
    def _white_field_mask(frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        white = cv2.inRange(hsv, np.array((0, 0, 150)), np.array((180, 100, 255)))
        return cv2.bitwise_and(white, cv2.dilate(green, np.ones((5, 5), np.uint8)))

    def _line_groups(self, frame: np.ndarray) -> list[list[np.ndarray]]:
        raw = cv2.HoughLinesP(self._white_field_mask(frame), 1, np.pi / 180, threshold=35, minLineLength=max(30, frame.shape[1] // 12), maxLineGap=18)
        if raw is None:
            return []
        groups: list[list[np.ndarray]] = []
        for item in raw[:, 0, :].astype(float):
            angle = np.arctan2(item[3] - item[1], item[2] - item[0]) % np.pi
            for group in groups:
                ref = group[0]
                ref_angle = np.arctan2(ref[3] - ref[1], ref[2] - ref[0]) % np.pi
                if abs(((angle - ref_angle + np.pi / 2) % np.pi) - np.pi / 2) < np.deg2rad(10):
                    group.append(item)
                    break
            else:
                groups.append([item])
        return groups

    def detect_yard_line_family(self, frame: np.ndarray) -> list[np.ndarray]:
        """Return fitted, ordered parallel five-yard-line image lines."""
        groups = self._line_groups(frame)
        if not groups:
            return []
        group = max(groups, key=len)
        direction = np.mean([np.arctan2(line[3] - line[1], line[2] - line[0]) % np.pi for line in group])
        normal = np.array((-np.sin(direction), np.cos(direction)))
        clusters: list[list[np.ndarray]] = []
        for line in sorted(group, key=lambda value: np.dot(((value[:2] + value[2:]) / 2), normal)):
            offset = np.dot(((line[:2] + line[2:]) / 2), normal)
            if not clusters or abs(offset - np.mean([np.dot(((x[:2] + x[2:]) / 2), normal) for x in clusters[-1]])) > 8:
                clusters.append([line])
            else:
                clusters[-1].append(line)
        return [self._fit_line(cluster) for cluster in clusters if len(cluster) >= 1]

    def estimate_absolute_yardline_stub(self, frame: np.ndarray) -> Optional[int]:
        """Return no yard number until an OCR model validates a painted numeral."""
        del frame
        return None

    def _sideline_pair(self, frame: np.ndarray, yard_lines: list) -> Optional[tuple[np.ndarray, np.ndarray]]:
        yard_angle = np.arctan2(-yard_lines[0][0], yard_lines[0][1]) % np.pi
        candidates = [group for group in self._line_groups(frame) if abs(((np.arctan2(group[0][3] - group[0][1], group[0][2] - group[0][0]) % np.pi - yard_angle + np.pi / 2) % np.pi) - np.pi / 2) > np.deg2rad(35)]
        if not candidates:
            return None
        side_lines = [self._fit_line([line]) for line in max(candidates, key=len)]
        anchor = yard_lines[len(yard_lines) // 2]
        side_lines.sort(key=lambda line: self._intersection(anchor, line)[1] if self._intersection(anchor, line) is not None else float("inf"))
        return side_lines[0], side_lines[-1]

    def _local_rectification(self, yard_lines: list[np.ndarray], bounds: tuple[np.ndarray, np.ndarray]) -> Optional[np.ndarray]:
        pixels, plane = [], []
        for index, yard in enumerate(yard_lines):
            for side_index, side in enumerate(bounds):
                point = self._intersection(yard, side)
                if point is not None:
                    pixels.append(point)
                    plane.append((index * YARD_LINE_SPACING_FT, side_index * FIELD_WIDTH_FT))
        if len(pixels) < MIN_CORRESPONDENCES:
            return None
        homography, mask = cv2.findHomography(np.float32(pixels), np.float32(plane), cv2.RANSAC, 3.0)
        if homography is None or mask is None or not np.isfinite(homography).all() or abs(float(homography[2, 2])) < 1e-8:
            return None
        return homography / homography[2, 2]

    def _hash_rows_in_rectified_field(self, frame: np.ndarray, local_homography: np.ndarray,
                                      yard_lines: list[np.ndarray]) -> list[float]:
        """Return supported hash-row ordinates after projective rectification.

        The ratio below is never measured in source pixels.  The field-width and
        yard-line constraints create one fresh projective rectification, then
        short hash-mark segments are measured in that plane.
        """
        raw = cv2.HoughLinesP(self._white_field_mask(frame), 1, np.pi / 180,
                               threshold=12, minLineLength=HASH_MIN_LENGTH_PX,
                               maxLineGap=5)
        if raw is None:
            return []
        yard_angle = np.arctan2(-yard_lines[0][0], yard_lines[0][1]) % np.pi
        values = []
        for line in raw[:, 0, :].astype(float):
            length = float(np.hypot(line[2] - line[0], line[3] - line[1]))
            angle = np.arctan2(line[3] - line[1], line[2] - line[0]) % np.pi
            same_direction = abs(((angle - yard_angle + np.pi / 2) % np.pi) - np.pi / 2)
            if not HASH_MIN_LENGTH_PX <= length <= frame.shape[1] * HASH_MAX_FRACTION or same_direction > np.deg2rad(10):
                continue
            midpoint = np.float32([[[float((line[0] + line[2]) / 2), float((line[1] + line[3]) / 2)]]])
            x, y = cv2.perspectiveTransform(midpoint, local_homography)[0, 0]
            if np.isfinite((x, y)).all() and 8.0 <= y <= FIELD_WIDTH_FT - 8.0:
                values.append(float(y))
        clusters: list[list[float]] = []
        for value in sorted(values):
            if not clusters or value - np.mean(clusters[-1]) > HASH_ROW_CLUSTER_FT:
                clusters.append([value])
            else:
                clusters[-1].append(value)
        return [float(np.mean(cluster)) for cluster in clusters if len(cluster) >= 3]

    def _level_from_hash_rows(self, rows: list[float]) -> Optional[str]:
        matches = set()
        for left_index, left in enumerate(rows):
            for right in rows[left_index + 1:]:
                level = self.field_level_from_ratio(abs(right - left), YARD_LINE_SPACING_FT)
                if level is not None:
                    matches.add(level)
        return next(iter(matches)) if len(matches) == 1 else None

    def homography_from_yard_lines(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Fit pixel-to-feet H, or None when this frame's geometry is unverified."""
        stats = self.last_fit_stats = {"reject": None}
        def fail(reason: str) -> None:
            stats["reject"] = reason
            return None
        stats["green_frac"] = green = field_view_fraction(frame)
        if green < MIN_FIELD_VIEW_GREEN:
            return fail("not_field_view")
        # A line pencil has no absolute origin or direction. Do this before any
        # fit so a locally-indexed grid cannot be accidentally promoted to feet.
        anchor = self.absolute_anchor_provider.detect(frame)
        if anchor is None:
            return fail("absolute_anchor_unavailable")
        stats["anchor_yard"] = anchor.yard_from_goal
        stats["anchor_direction"] = anchor.direction
        yard_lines = self.detect_yard_line_family(frame)
        stats["n_yard"] = len(yard_lines)
        if not MIN_YARD_LINES <= len(yard_lines) <= MAX_YARD_LINES:
            return fail("family_size")
        if not pencil_is_uniform(yard_lines, frame.shape):
            return fail("family_not_uniform")
        bounds = self._sideline_pair(frame, yard_lines)
        if bounds is None:
            return fail("no_sidelines")
        local_homography = self._local_rectification(yard_lines, bounds)
        if local_homography is None:
            return fail("local_rectification_unavailable")
        hash_rows = self._hash_rows_in_rectified_field(frame, local_homography, yard_lines)
        stats["hash_rows"] = len(hash_rows)
        level = self._level_from_hash_rows(hash_rows)
        if level is None:
            return fail("independent_scale_unavailable")
        stats["field_level"] = level
        anchor = yard_lines[len(yard_lines) // 2]
        span = [self._intersection(anchor, side) for side in bounds]
        if any(point is None for point in span):
            return fail("no_sideline_span")
        stats["side_sep_px"] = separation = float(np.linalg.norm(span[0] - span[1]))
        if separation <= 0.0 or FIELD_WIDTH_FT / separation > MAX_FT_PER_PIXEL:
            return fail("sideline_degenerate")
        pixels, plane_points = [], []
        for index, yard in enumerate(yard_lines):
            for side_index, side in enumerate(bounds):
                point = self._intersection(yard, side)
                if point is not None:
                    pixels.append(point)
                    plane_points.append((index * YARD_LINE_SPACING_FT, side_index * FIELD_WIDTH_FT))
        image_points = np.float32(pixels)
        homography, mask = cv2.findHomography(image_points, np.float32(plane_points), cv2.RANSAC, 3.0)
        if homography is None or mask is None or abs(float(homography[2, 2])) < 1e-8 or not np.isfinite(homography).all():
            return fail("no_homography")
        homography = homography / homography[2, 2]
        anchor_point = np.float32([[[anchor.pixel[0], anchor.pixel[1]]]])
        local_anchor = cv2.perspectiveTransform(anchor_point, homography)[0, 0]
        target_x = 3.0 * anchor.yard_from_goal
        if anchor.direction < 0:
            target_x = FIELD_LENGTH_FT - target_x
        translation = np.array(((1.0, 0.0, target_x - local_anchor[0]),
                                (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
        homography = translation @ homography
        stats["anchor_x_ft"] = float(target_x)
        projected = cv2.perspectiveTransform(image_points.reshape(-1, 1, 2), homography)[:, 0, :]
        stats["inlier_frac"] = float(mask.mean())
        stats["rmse_all_ft"] = float(np.sqrt(float((np.linalg.norm(projected - plane_points, axis=1) ** 2).mean())))
        if stats["inlier_frac"] < MIN_INLIER_FRACTION or stats["rmse_all_ft"] > MAX_FIT_RMSE_FT:
            return fail("fit_quality")
        return homography

    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        candidate = self.homography_from_yard_lines(frame)
        if candidate is None:
            self._reset_segment()
            return None
        if self._homography is None:
            self._homography = candidate
            return None
        height, width = frame.shape[:2]
        grid = np.float32([[[x * width, y * height]] for y in (0.55, 0.7, 0.85) for x in (0.2, 0.5, 0.8)])
        held = cv2.perspectiveTransform(grid, self._homography)[:, 0, :]
        fresh = cv2.perspectiveTransform(grid, candidate)[:, 0, :]
        if not (np.isfinite(held).all() and np.isfinite(fresh).all() and float(np.median(np.linalg.norm(held - fresh, axis=1))) <= GRID_AGREEMENT_FT):
            self._reset_segment()
            self._homography = candidate
            return None
        return self._homography
