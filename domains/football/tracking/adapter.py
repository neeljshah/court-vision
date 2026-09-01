"""American-football broadcast adapter for field geometry and pre-snap rows.

This intentionally does not claim full-play TV tracking. Broadcast cuts, camera
pans and zooms, heavy occlusion at the line, and a frequently invisible ball
make player identity and continuous full-play trajectories unreliable without
multi-view calibration and play-specific validation. The adapter therefore
emits only low-motion, pre-snap formation frames; ball rows are a named stub.

Yard-line coordinates are offset-relative until an OCR integration identifies
the painted yard number: the first ordered detected five-yard line is x=0 and
each following line is x=15 feet, held fixed for a segment. That ordinal
labelling is only true when the family really is consecutive equally spaced
lines, so field_gates.pencil_is_uniform tests it with a fit-free cross-ratio
before the fit runs. y=0 and y=160 are the two DETECTED cross-field boundary
lines; frames without them are dropped.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from domains.football.tracking.field_gates import (MIN_FIELD_VIEW_GREEN,
                                                   field_view_fraction,
                                                   pencil_is_uniform)


SCHEMA = ("frame", "track_id", "cls", "x", "y")
FIELD_WIDTH_FT = 160.0
FIELD_LENGTH_FT = 360.0
YARD_LINE_SPACING_FT = 15.0
# Numerical-blowup guard only. It is deliberately FAR wider than the harness
# football bounds (0..360, 0..160): a rejection window equal to those bounds
# would define oob_pct to zero and make the harness check tautological, so a
# genuinely out-of-field projection must still be emitted and counted.
SANITY_LIMIT_FT = 5.0 * FIELD_LENGTH_FT
# A five-yard line every 15 ft leaves at most this many on a 360 ft field; more
# clusters than that means the family is contaminated (hash marks, numbers,
# logos) and the ordinal-times-15-feet labelling below is false.
MAX_YARD_LINES = int(FIELD_LENGTH_FT / YARD_LINE_SPACING_FT) + 1
# Four correspondences determine a homography exactly, so their reprojection
# residual is zero whatever they mean. The fit must be over-determined before
# MAX_FIT_RMSE_FT can discriminate at all. Six points (three yard lines) is far
# too close to that minimum: the only frame accepted in a measured 600-frame run
# of a real SEC broadcast had exactly six, reported rmse 0.572 ft, and was a
# false positive whose three "yard lines" differed by about 60 degrees. Four
# yard lines, eight points, is also the minimum the cross-ratio gate can test.
MIN_CORRESPONDENCES = 8
MIN_YARD_LINES = 4
MIN_INLIER_FRACTION = 0.8
MAX_FIT_RMSE_FT = 3.0
# The sideline pair carries the whole 160 ft cross-field scale. Below this a
# one-pixel line-fit error already moves a player more than MAX_FT_PER_PIXEL.
MAX_FT_PER_PIXEL = 2.0
GRID_AGREEMENT_FT = 2.0
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write normalized tracking rows."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, SCHEMA].to_csv(path, index=False)


class FootballAdapter:
    """Estimate an offset-relative field plane and pre-snap player formations."""

    def __init__(self, detector: Optional[Detector] = None, motion_threshold: float = 3.0,
                 scene_cut_threshold: float = 0.55) -> None:
        self.detector = detector
        self.motion_threshold = motion_threshold
        self.scene_cut_threshold = scene_cut_threshold
        self._homography: Optional[np.ndarray] = None
        self.last_fit_stats: dict = {}
        self._centroids: dict[int, np.ndarray] = {}
        self._next_track_id = 1
        self.scene_cuts_detected = 0
        self.last_output = pd.DataFrame(columns=SCHEMA)

    def _reset_segment(self) -> None:
        """Forget geometry and identities at a discontinuous camera cut."""
        self._homography = None
        self._centroids.clear()

    @staticmethod
    def scene_cut_score(previous: np.ndarray, current: np.ndarray) -> float:
        """Return histogram distance between consecutive camera views."""
        def histogram(frame: np.ndarray) -> np.ndarray:
            hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
            value = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
            return cv2.normalize(value, value).flatten()
        return float(cv2.compareHist(histogram(previous), histogram(current),
                                     cv2.HISTCMP_BHATTACHARYYA))

    def is_scene_cut(self, previous: np.ndarray, current: np.ndarray) -> bool:
        """True when a view change invalidates carried homography and identity."""
        return self.scene_cut_score(previous, current) >= self.scene_cut_threshold

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("FootballAdapter requires ultralytics or a test detector.") from exc
        model = YOLO("yolov8n.pt")

        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            return [] if result.boxes is None else result.boxes.xyxy.cpu().numpy().tolist()
        return detect

    def _detect(self, frame: np.ndarray) -> Sequence[Sequence[float]]:
        if self.detector is None:
            self.detector = self._load_yolo_detector()
        return self.detector(frame)

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
        return FootballAdapter._line_coefficients(np.array((x0 - 9999 * vx, y0 - 9999 * vy, x0 + 9999 * vx, y0 + 9999 * vy)))

    @staticmethod
    def _white_field_mask(frame: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        white = cv2.inRange(hsv, np.array((0, 0, 150)), np.array((180, 100, 255)))
        return cv2.bitwise_and(white, cv2.dilate(green, np.ones((5, 5), np.uint8)))

    def _line_groups(self, frame: np.ndarray) -> list[list[np.ndarray]]:
        mask = self._white_field_mask(frame)
        raw = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=35, minLineLength=max(30, frame.shape[1] // 12), maxLineGap=18)
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

    def _sideline_pair(self, frame: np.ndarray,
                       yard_lines: list) -> Optional[tuple[np.ndarray, np.ndarray]]:
        """Return the two detected cross-field boundary lines, or None.

        There is deliberately no green-bounding-box fallback: the top and bottom
        of the visible grass are not sidelines, and calling them 160 ft apart
        fabricates the only cross-field correspondence the fit has.
        """
        yard_angle = np.arctan2(-yard_lines[0][0], yard_lines[0][1]) % np.pi
        candidates = [group for group in self._line_groups(frame)
                      if abs(((np.arctan2(group[0][3] - group[0][1], group[0][2] - group[0][0]) % np.pi
                               - yard_angle + np.pi / 2) % np.pi) - np.pi / 2) > np.deg2rad(35)]
        if not candidates:
            return None
        side_lines = [self._fit_line([line]) for line in max(candidates, key=len)]
        anchor = yard_lines[len(yard_lines) // 2]
        side_lines.sort(key=lambda line: self._intersection(anchor, line)[1]
                        if self._intersection(anchor, line) is not None else float("inf"))
        return side_lines[0], side_lines[-1]

    def homography_from_yard_lines(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Fit pixel-to-feet H, or None when this frame's geometry is unverified.

        Nothing here proves the detected white-line family really is consecutive
        five-yard lines, so every gate below rejects a frame the fit cannot back
        up. The failed gate is recorded in last_fit_stats for measurement.
        """
        stats = self.last_fit_stats = {"reject": None}

        def fail(reason: str) -> None:
            stats["reject"] = reason
            return None

        stats["green_frac"] = green = field_view_fraction(frame)
        if green < MIN_FIELD_VIEW_GREEN:
            return fail("not_field_view")
        yard_lines = self.detect_yard_line_family(frame)
        stats["n_yard"] = len(yard_lines)
        if not MIN_YARD_LINES <= len(yard_lines) <= MAX_YARD_LINES:
            return fail("family_size")
        if not pencil_is_uniform(yard_lines, frame.shape):
            return fail("family_not_uniform")
        bounds = self._sideline_pair(frame, yard_lines)
        if bounds is None:
            return fail("no_sidelines")
        anchor = yard_lines[len(yard_lines) // 2]
        span = [self._intersection(anchor, side) for side in bounds]
        if any(point is None for point in span):
            return fail("no_sideline_span")
        stats["side_sep_px"] = separation = float(np.linalg.norm(span[0] - span[1]))
        if separation <= 0.0 or FIELD_WIDTH_FT / separation > MAX_FT_PER_PIXEL:
            return fail("sideline_degenerate")
        pixels: list[np.ndarray] = []
        field: list[tuple[float, float]] = []
        for index, yard in enumerate(yard_lines):
            for side_index, side in enumerate(bounds):
                point = self._intersection(yard, side)
                if point is not None:
                    pixels.append(point)
                    field.append((index * YARD_LINE_SPACING_FT, side_index * FIELD_WIDTH_FT))
        if len(pixels) < MIN_CORRESPONDENCES:
            return fail("few_points")
        image_points, plane_points = np.float32(pixels), np.float32(field)
        homography, mask = cv2.findHomography(image_points, plane_points, cv2.RANSAC, 3.0)
        if (homography is None or abs(float(homography[2, 2])) < 1e-8
                or not np.isfinite(homography).all()):
            return fail("no_homography")
        homography = homography / homography[2, 2]
        projected = cv2.perspectiveTransform(image_points.reshape(-1, 1, 2), homography)[:, 0, :]
        stats["inlier_frac"] = float(mask.mean())
        # ALL points, never the inliers alone: a degenerate minimal subset always
        # reprojects onto itself, so an inlier RMSE cannot discriminate.
        stats["rmse_all_ft"] = float(np.sqrt(float(
            (np.linalg.norm(projected - plane_points, axis=1) ** 2).mean())))
        if stats["inlier_frac"] < MIN_INLIER_FRACTION or stats["rmse_all_ft"] > MAX_FIT_RMSE_FT:
            return fail("fit_quality")
        return homography

    def _stable_homography(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """Hold one homography per still segment and use it only while confirmed.

        x is segment-relative: estimate_absolute_yardline_stub reads no painted
        numeral, so the origin is whichever five-yard line anchored the segment.
        Re-solving per frame re-indexes that origin by multiples of 15 ft and
        slides the whole coordinate frame, so a fresh fit only CONFIRMS the held
        one; disagreement starts a new segment with new track ids instead of
        moving the origin underneath old ones.
        """
        candidate = self.homography_from_yard_lines(frame)
        if candidate is None:
            self._reset_segment()
            return None
        if self._homography is None:
            self._homography = candidate
            return None
        height, width = frame.shape[:2]
        grid = np.float32([[[x * width, y * height]]
                           for y in (0.55, 0.7, 0.85) for x in (0.2, 0.5, 0.8)])
        held = cv2.perspectiveTransform(grid, self._homography)[:, 0, :]
        fresh = cv2.perspectiveTransform(grid, candidate)[:, 0, :]
        if not (np.isfinite(held).all() and np.isfinite(fresh).all()
                and float(np.median(np.linalg.norm(held - fresh, axis=1))) <= GRID_AGREEMENT_FT):
            self._reset_segment()
            self._homography = candidate
            return None
        return self._homography

    @staticmethod
    def motion_magnitude(previous: np.ndarray, current: np.ndarray) -> float:
        """Return median gray-frame difference for a conservative stillness test."""
        first = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        second = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
        return float(np.median(cv2.absdiff(first, second)))

    def is_pre_snap(self, previous: np.ndarray, current: np.ndarray, detections: Optional[Sequence[Sequence[float]]] = None) -> bool:
        """Classify a low-motion frame with at least 14 people as pre-snap."""
        boxes = self._detect(current) if detections is None else detections
        return self.motion_magnitude(previous, current) <= self.motion_threshold and len(boxes) >= 14

    def _track_players(self, boxes: Sequence[Sequence[float]], homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        result: list[tuple[int, np.ndarray]] = []
        unused = set(self._centroids)
        for box in boxes:
            x1, y1, x2, y2 = map(float, box[:4])
            center = np.array(((x1 + x2) / 2, (y1 + y2) / 2))
            foot = cv2.perspectiveTransform(np.float32([[[center[0], y2]]]), homography)[0, 0]
            # Numerical-blowup guard only, never the harness field bounds --
            # see SANITY_LIMIT_FT: a real out-of-field projection must survive to
            # be counted in oob_pct instead of being defined away here.
            if not (np.isfinite(foot).all() and abs(float(foot[0])) <= SANITY_LIMIT_FT
                    and abs(float(foot[1])) <= SANITY_LIMIT_FT):
                continue
            choices = [(np.linalg.norm(center - self._centroids[item]), item) for item in unused]
            track_id = min(choices)[1] if choices else self._next_track_id
            if not choices:
                self._next_track_id += 1
            unused.discard(track_id)
            self._centroids[track_id] = center
            result.append((track_id, foot))
        return result

    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1) -> pd.DataFrame:
        """Process headless video and emit only pre-snap player rows."""
        if stride < 1:
            raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        self.scene_cuts_detected = 0
        previous: Optional[np.ndarray] = None
        frame_index = processed = 0
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % stride == 0:
                    if previous is not None and self.is_scene_cut(previous, frame):
                        self._reset_segment()
                        self.scene_cuts_detected += 1
                        previous = None
                    homography, boxes = self._stable_homography(frame), self._detect(frame)
                    if previous is not None and homography is not None and self.is_pre_snap(previous, frame, boxes):
                        players = self._track_players(boxes, homography)
                        for track_id, point in players if len(players) >= 14 else ():
                            rows.append({"frame": frame_index, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                    previous = frame
                    processed += 1
                frame_index += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the latest adapter output in the normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
