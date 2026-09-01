"""American-football broadcast adapter for field geometry and pre-snap rows."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable, Optional, Sequence, Union
import cv2
import numpy as np
import pandas as pd
from domains.football.tracking.geometry import FIELD_LENGTH_FT, FootballGeometryMixin, YARD_LINE_SPACING_FT
from scripts.platformkit.coordinate_provenance import (HOMOGRAPHY, IMAGE_COORDINATE_SPACE,
    NO_CALIBRATION, OBSERVED, output_columns, stamp_image_space_rows)

SCHEMA = ("frame", "track_id", "cls", "x", "y")
SANITY_LIMIT_FT = 5.0 * FIELD_LENGTH_FT
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]

def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write normalized tracking rows."""
    missing = [column for column in SCHEMA if column not in rows.columns]
    if missing: raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, output_columns(SCHEMA, rows)].to_csv(path, index=False)

class FootballAdapter(FootballGeometryMixin):
    """Estimate an offset-relative field plane and pre-snap player formations."""
    def __init__(self, detector: Optional[Detector] = None, motion_threshold: float = 3.0, scene_cut_threshold: float = 0.55) -> None:
        super().__init__()
        self.detector, self.motion_threshold, self.scene_cut_threshold = detector, motion_threshold, scene_cut_threshold
        self._homography, self.last_fit_stats, self._centroids, self._next_track_id = None, {}, {}, 1
        self.scene_cuts_detected, self.last_output = 0, pd.DataFrame(columns=SCHEMA)
    def _reset_segment(self) -> None:
        """Forget geometry and identities at a discontinuous camera cut."""
        self._homography = None
        self._centroids.clear()
    @staticmethod
    def scene_cut_score(previous: np.ndarray, current: np.ndarray) -> float:
        """Return histogram distance between consecutive camera views."""
        def histogram(frame: np.ndarray) -> np.ndarray:
            hsv = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2HSV)
            return cv2.normalize(cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256]), None).flatten()
        return float(cv2.compareHist(histogram(previous), histogram(current), cv2.HISTCMP_BHATTACHARYYA))
    def is_scene_cut(self, previous: np.ndarray, current: np.ndarray) -> bool: return self.scene_cut_score(previous, current) >= self.scene_cut_threshold
    @staticmethod
    def _load_yolo_detector() -> Detector:
        from scripts.platformkit.detection.shim import get_box_detector
        return get_box_detector(
            model_path=os.environ.get("CV_DETECTOR_MODEL"), sport="football"
        )
    def _detect(self, frame: np.ndarray) -> Sequence[Sequence[float]]:
        if self.detector is None: self.detector = self._load_yolo_detector()
        return self.detector(frame)
    @staticmethod
    def motion_magnitude(previous: np.ndarray, current: np.ndarray) -> float: return float(np.median(cv2.absdiff(cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY), cv2.cvtColor(current, cv2.COLOR_BGR2GRAY))))
    def is_pre_snap(self, previous: np.ndarray, current: np.ndarray, detections: Optional[Sequence[Sequence[float]]] = None) -> bool:
        """Low frame-to-frame motion. A snap is the motion step; that is the evidence.

        The detection count used to be ANDed in here (>= 14) and the harness's
        football min_players is exactly 14, so a frame that could have failed
        coverage was never emitted and therefore never entered the denominator
        -- n_frames comes from the emitted CSV (tracking_harness.py:132). A gate
        whose window sits on the harness bound is the banned tautology class,
        and this was the sixth instance found in this codebase.
        Field-view evidence is still required, independently: the caller emits
        only when _stable_homography solved for the frame.
        """
        del detections  # counting players must never decide whether to measure players
        return self.motion_magnitude(previous, current) <= self.motion_threshold
    def _track_players(self, boxes: Sequence[Sequence[float]], homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        result, unused = [], set(self._centroids)
        for box in boxes:
            x1, y1, x2, y2 = map(float, box[:4])
            center = np.array(((x1 + x2) / 2, (y1 + y2) / 2))
            foot = cv2.perspectiveTransform(np.float32([[[center[0], y2]]]), homography)[0, 0]
            if not (np.isfinite(foot).all() and abs(float(foot[0])) <= SANITY_LIMIT_FT and abs(float(foot[1])) <= SANITY_LIMIT_FT): continue
            choices = [(np.linalg.norm(center - self._centroids[item]), item) for item in unused]
            track_id = min(choices)[1] if choices else self._next_track_id
            if not choices: self._next_track_id += 1
            unused.discard(track_id)
            self._centroids[track_id] = center
            result.append((track_id, foot))
        return result
    def detect_players_image_space(self, frame: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return observed person bottom-centres as source pixels, unprojected."""
        return [(track_id, np.array(((x1 + x2) / 2, y2))) for track_id, raw in enumerate(self._detect(frame), 1) for x1, y1, x2, y2 in [map(float, raw[:4])] if x2 > x1 and y2 > y1]
    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1, image_space: bool = False) -> pd.DataFrame:
        if stride < 1: raise ValueError("stride must be at least 1")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened(): raise FileNotFoundError("Could not open video: %s" % path)
        rows, previous, frame_index, processed = [], None, 0, 0
        self.scene_cuts_detected = 0
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok: break
                if frame_index % stride == 0:
                    if image_space:
                        for track_id, point in self.detect_players_image_space(frame): rows.append({"frame": frame_index, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                        processed += 1
                        frame_index += 1
                        continue
                    if previous is not None and self.is_scene_cut(previous, frame):
                        self._reset_segment()
                        self.scene_cuts_detected += 1
                        previous = None
                    homography, boxes = self._stable_homography(frame), self._detect(frame)
                    if previous is not None and homography is not None and self.is_pre_snap(previous, frame, boxes):
                        players = self._track_players(boxes, homography)
                        # Emit every tracked player, not `players if len(players) >= 14`.
                        # That guard made per-frame track_id count >= min_players by
                        # construction, pinning coverage at exactly 1.0 for football --
                        # unfailable, which is the point of the ban. A pre-snap frame
                        # showing 9 players is a real observation and coverage should
                        # say so.
                        for track_id, point in players:
                            rows.append({"frame": frame_index, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1]), "coordinate_space": "court_feet", "observation": OBSERVED, "calibration": HOMOGRAPHY})
                    # Calibration failures intentionally emit no row in this mode.
                    # The image-space branch above is a separate preserved corpus;
                    # mixing it with court_feet makes the whole file unscorable.
                    previous, processed = frame, processed + 1
                frame_index += 1
        finally: capture.release()
        self.last_output = pd.DataFrame(rows) if rows else pd.DataFrame(columns=SCHEMA)
        if image_space: self.last_output = stamp_image_space_rows(self.last_output)
        return self.last_output
    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None: write_csv(self.last_output if rows is None else rows, path)
