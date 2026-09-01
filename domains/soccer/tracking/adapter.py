"""Broadcast soccer tracking projected onto a 105 by 68 metre pitch."""
from __future__ import annotations
from pathlib import Path
from typing import Callable, Optional, Sequence, Union
import cv2
import numpy as np
import pandas as pd
from domains.soccer.tracking.geometry import SoccerGeometryMixin
from domains.soccer.tracking.pressing import aggregate_pressing, pressure_index
from domains.soccer.tracking.segmenter import is_pitch_view
from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator
from scripts.platformkit.coordinate_provenance import output_columns, stamp_image_space_rows

SCHEMA = ("frame", "track_id", "cls", "x", "y")
PITCH_ACCEPT = (-5.0, 110.0, -5.0, 73.0)
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]

class BallTrackingUnavailableError(RuntimeError):
    """Raised when a caller requests unsupported soccer ball tracking."""

def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write tracking rows in the shared platform schema."""
    columns = output_columns(SCHEMA, rows)
    missing = [column for column in columns if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, columns].to_csv(path, index=False)

class SoccerAdapter(SoccerGeometryMixin):
    """Track broadcast-view players only when the current pitch is calibrated."""
    def __init__(self, detector: Optional[Detector] = None, retirement_frames: int = 30) -> None:
        self.detector = detector if detector is not None else self._load_yolo_detector()
        self.retirement_frames, self._tracks, self._next_track_id = retirement_frames, {}, 1
        self._homography: Optional[np.ndarray] = None
        self._calibrator = TemporalCalibrator("soccer", drift_threshold=8.0)
        self._calibration_updates = 0
        self.last_output = pd.DataFrame(columns=SCHEMA)
        self.last_metadata: dict[str, object] = {}

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError("SoccerAdapter requires ultralytics or a test detector.") from exc
        model = YOLO("yolov8n.pt")
        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            return [] if result.boxes is None else result.boxes.xyxy.cpu().numpy().tolist()
        return detect

    def _assign_tracks(self, centers: list[np.ndarray]) -> list[int]:
        available, ids = set(self._tracks), []
        for center in centers:
            nearest = min(available, key=lambda track_id: np.linalg.norm(center - self._tracks[track_id][0]), default=None)
            if nearest is None:
                nearest, self._next_track_id = self._next_track_id, self._next_track_id + 1
            else:
                available.remove(nearest)
            self._tracks[nearest] = (center, 0); ids.append(nearest)
        for track_id in list(available):
            center, lost = self._tracks[track_id]; self._tracks[track_id] = (center, lost + 1)
            if lost + 1 >= self.retirement_frames: del self._tracks[track_id]
        return ids

    def mark_frame_lost(self) -> None:
        """Age tracks for a frame that cannot safely be projected."""
        self._assign_tracks([])

    def detect_players(self, frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Project person detections and retain nearest-centroid identities."""
        candidates = []
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 > x1 and y2 > y1:
                point = self._project(((x1 + x2) / 2, y2), homography)
                if PITCH_ACCEPT[0] <= point[0] <= PITCH_ACCEPT[1] and PITCH_ACCEPT[2] <= point[1] <= PITCH_ACCEPT[3]: candidates.append((np.array(((x1 + x2) / 2, (y1 + y2) / 2)), point))
        ids = self._assign_tracks([candidate[0] for candidate in candidates])
        return list(zip(ids, [candidate[1] for candidate in candidates]))

    def detect_players_image_space(self, frame: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return every person detection as bottom-centre source pixels."""
        candidates = [(np.array(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)), np.array(((box[0] + box[2]) / 2, box[3]))) for box in (list(map(float, raw[:4])) for raw in self.detector(frame)) if box[2] > box[0] and box[3] > box[1]]
        ids = self._assign_tracks([candidate[0] for candidate in candidates])
        return list(zip(ids, [candidate[1] for candidate in candidates]))

    def process_video(self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1, skip_non_pitch: bool = True, compute_pressing: bool = True, player_only: bool = False, image_space: bool = False) -> pd.DataFrame:
        """Process a headless stream, emitting rows only for validated pitch frames."""
        if stride < 1: raise ValueError("stride must be at least 1")
        if not player_only: raise BallTrackingUnavailableError("Soccer ball tracking is unavailable: this adapter runs YOLO person class 0 only and has no validated ball detector. Use player_only=True for player-only output.")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened(): raise FileNotFoundError("Could not open video: %s" % path)
        rows, source_frame, processed, pitch_frames, accepted_homography_frames = [], 0, 0, [], []
        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok: break
                if source_frame % stride == 0:
                    pitch_view = is_pitch_view(frame)
                    if skip_non_pitch and not pitch_view:
                        self.mark_frame_lost(); processed += 1; source_frame += 1; continue
                    if pitch_view: pitch_frames.append(source_frame)
                    if image_space:
                        for track_id, point in self.detect_players_image_space(frame): rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                        processed += 1; source_frame += 1; continue
                    homography = self._stable_homography(self._landmark_detections(frame), frame.shape[:2])
                    if homography is None: self.mark_frame_lost()
                    else:
                        accepted_homography_frames.append(source_frame)
                        for track_id, point in self.detect_players(frame, homography): rows.append({"frame": source_frame, "track_id": track_id, "cls": "player", "x": float(point[0]), "y": float(point[1])})
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        self.last_output = pd.DataFrame(rows, columns=SCHEMA)
        if image_space: self.last_output = stamp_image_space_rows(self.last_output)
        self.last_metadata = {"processed_frames": processed, "pitch_view_frames": pitch_frames, "accepted_homography_frames": accepted_homography_frames}
        if image_space: self.last_metadata.update({"coordinate_space": "image_px", "roi": "full_frame"})
        if compute_pressing and not image_space:
            index = pressure_index(self.last_output, ball_proxy=True)
            self.last_metadata["pressing_proxy"] = {"per_frame": index, "windows": aggregate_pressing(self.last_output, ball_proxy=True), "frame_ids": index["frame"].astype(int).tolist()}
        return self.last_output

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
