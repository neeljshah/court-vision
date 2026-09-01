"""Baseball pitch-view detection.  Coordinates fail closed: there is no homography.

Measured on 2026-09-01 over two independent 1280x720 MLB broadcast clips, 500
sampled frames each at stride 3, using the pitcher's-mound horizontal chord as
an exactly known 18-foot ground distance:

* lateral scale at the mound row is 30.3-47.7 px/ft, so the frame covers only
  26.9-42.3 feet of lateral world (p95 66.2 ft).  First and third base sit 63.64
  feet either side of the plate-mound line, so seeing both needs 127.28 feet.
  Across every sample measured -- 24 to 244 mound-bearing frames per clip -- no
  frame was wide enough.  A four-point infield homography is not merely hard
  here, it is out of frame.
* the mound circle's near edge is cut by the score bug for whole segments
  (measured 100 percent of 37 consecutive frames in one segment, 4 percent in
  another sample), so its conic is not reliably observable.  A two-conic solve
  has no second conic either: the home-plate dirt merges continuously with the
  base-path band and is split by whoever stands in front of it.
* the camera is panned (mound center x ~510 px, home plate x ~835 px), so a
  one-dimensional depth model does not apply.

That leaves the ground-plane homography under-determined by features that can
actually be detected here, and there is no labelled baseball corpus to validate
a fitted one against -- only the harness's own oob bound, which is exactly the
gate a calibration must not be tuned toward.

The previous scalar ``|mound - plate| / 60.5`` gave 3.5-4.8 px/ft and was applied
to both axes.  Against the measured lateral scale that is wrong by 8-14x, which
is what produced oob 0.66-0.74 on both corpora.  Emitting those numbers as feet
is a fabrication, so no player rows are emitted at all.  See
``scripts/platformkit/baseball_calib_probe.py`` for the measurement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

import cv2
import numpy as np
import pandas as pd

from domains.baseball.tracking.command_meter import MotionStableDetector, command_series, glove_target
from domains.baseball.tracking.field_mask import (
    MIN_CHORD_FRACTION, MOUND_DIAMETER_FEET, infield_band_present, mound_chord,
)
from domains.baseball.tracking.scale_anchor import anchor_calibrations
from domains.baseball.tracking.segmenter import detect_cut, small_gray
from scripts.platformkit.coordinate_provenance import IMAGE_SCHEMA, write_tracking_csv

SCHEMA = ("frame", "track_id", "cls", "x", "y")
MOUND_TO_PLATE_FEET = 60.5
Detector = Callable[[np.ndarray], Sequence[Sequence[float]]]
_CENTER_CROP_FRACTION = 0.70
COORDINATE_CALIBRATION_REASON = (
    "No validated ground-plane homography for baseball. Measured lateral field of "
    "view at the mound row is 26.9-42.3 ft (p95 66.2 ft), but seeing both 1B and "
    "3B needs 127.28 ft, so no sampled frame could carry a four-point infield "
    "solve; the mound near edge is score-bug cut for whole segments and the "
    "home-plate dirt is inseparable from the base-path band, so no conic solve "
    "either. The retired mound-plate scalar was anisotropic by 8-14x and produced "
    "oob 0.66-0.74. See scripts/platformkit/baseball_calib_probe.py."
)


class BallTrackingUnavailableError(RuntimeError):
    """Raised when a caller requests unsupported baseball ball tracking."""


@dataclass(frozen=True)
class PitchGeometry:
    """What one pitch frame actually evidences: the mound, and lateral scale.

    ``pixels_per_foot`` is the LATERAL scale at ``mound``'s image row, taken from
    the mound's known 18-foot chord.  It is not valid along the depth axis and is
    deliberately not used to project anything into feet.
    """
    mound: np.ndarray
    mound_chord_px: float
    pixels_per_foot: float
    near_edge_occluded: bool


def write_csv(rows: pd.DataFrame, path: Union[str, Path]) -> None:
    """Write rows in the normalized platform tracking schema."""
    write_tracking_csv(rows, path, SCHEMA)


class BaseballAdapter:
    """Detect center-field pitch views.  Emit no coordinates: none are calibratable."""

    def __init__(self, detector: Optional[Detector] = None) -> None:
        self.detector = detector if detector is not None else self._load_yolo_detector()
        self._geometry: Optional[PitchGeometry] = None
        self._centroids: dict[int, np.ndarray] = {}
        self._next_track_id = 1
        self.last_output = pd.DataFrame(columns=SCHEMA)

    @staticmethod
    def _load_yolo_detector() -> Detector:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise ImportError(
                "BaseballAdapter requires ultralytics. Install it with "
                "pip install ultralytics, or pass a detector for testing."
            ) from exc
        model = YOLO("yolov8n.pt")

        def detect(frame: np.ndarray) -> Sequence[Sequence[float]]:
            result = model(frame, classes=[0], verbose=False)[0]
            if result.boxes is None:
                return []
            return result.boxes.xyxy.cpu().numpy().tolist()

        return detect

    @staticmethod
    def _center_crop(frame: np.ndarray) -> np.ndarray:
        """Return the central 70 percent of a frame."""
        height, width = frame.shape[:2]
        crop_width = int(width * _CENTER_CROP_FRACTION)
        crop_height = int(height * _CENTER_CROP_FRACTION)
        x0, y0 = (width - crop_width) // 2, (height - crop_height) // 2
        return frame[y0:y0 + crop_height, x0:x0 + crop_width]

    @staticmethod
    def _dominant_green(frame: np.ndarray) -> bool:
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
        return float(np.count_nonzero(green)) / green.size >= 0.35

    def detect_pitch_geometry(
        self, frame: np.ndarray, min_chord_fraction: float = MIN_CHORD_FRACTION,
    ) -> Optional[PitchGeometry]:
        """Identify the mound positively and measure its lateral scale.

        The mound is found by evidence -- the widest dirt run with live grass on
        both sides, under a dirt band that runs off a frame edge -- rather than
        by assuming it sits above or below the plate.  The old gate required the
        mound anchor to be ABOVE the plate anchor, which is backwards on a
        center-field broadcast: the mound images below.

        ``min_chord_fraction`` is exposed so a measurement can relax the size
        floor without relaxing the evidence, and so observe a genuinely wide
        pitch view if one exists.  Dirt-coloured clothing on grass passes the
        chord test alone; the infield-band test is what rejects it.
        """
        if not self._dominant_green(self._center_crop(frame)):
            return None
        chord = mound_chord(frame, min_chord_fraction)
        if chord is None:
            return None
        if not infield_band_present(frame, chord.row):
            return None
        mound = np.array((chord.center_x, float(chord.row)), dtype=np.float32)
        return PitchGeometry(mound, chord.width, chord.pixels_per_foot_lateral,
                             chord.near_edge_occluded)

    def is_pitch_view(self, frame: np.ndarray) -> bool:
        """Return whether the frame shows green field, a bounded mound, and infield dirt."""
        return self.detect_pitch_geometry(frame) is not None

    def calibrate_scale(self, frame: np.ndarray) -> Optional[float]:
        """Return the measured LATERAL pixels per foot at the mound row."""
        geometry = self.detect_pitch_geometry(frame)
        return None if geometry is None else geometry.pixels_per_foot

    def count_players(self, frame: np.ndarray, geometry: PitchGeometry) -> int:
        """Count detected people around the mound row.

        Kept so metadata can evidence that the fail-closed output is a
        calibration limit, not a detection failure.  No feet are computed.
        """
        span = geometry.mound_chord_px
        top, bottom = geometry.mound[1] - 1.2 * span, geometry.mound[1] + 0.3 * span
        seen = 0
        for box in self.detector(frame):
            x1, y1, x2, y2 = map(float, box[:4])
            if x2 <= x1 or y2 <= y1:
                continue
            if top <= y2 <= bottom and abs((x1 + x2) / 2.0 - geometry.mound[0]) <= 1.5 * span:
                seen += 1
        return seen

    def detect_players_image_space(self, frame: np.ndarray) -> list[tuple[int, np.ndarray]]:
        """Return observed person bottom-centres as source pixels, unprojected."""
        result, unused = [], set(self._centroids)
        for raw in self.detector(frame):
            x1, y1, x2, y2 = map(float, raw[:4])
            if x2 <= x1 or y2 <= y1:
                continue
            center = np.array(((x1 + x2) / 2, (y1 + y2) / 2))
            choices = [(np.linalg.norm(center - self._centroids[item]), item) for item in unused]
            track_id = min(choices)[1] if choices else self._next_track_id
            if not choices:
                self._next_track_id += 1
            unused.discard(track_id)
            self._centroids[track_id] = center
            result.append((track_id, np.array((center[0], y2))))
        return result

    def process_video(
        self, path: Union[str, Path], max_frames: Optional[int] = None, stride: int = 1,
        compute_command: bool = False, player_only: bool = False,
        image_space: bool = False,
    ) -> Union[pd.DataFrame, tuple[pd.DataFrame, dict[str, object]]]:
        """Detect pitch views and return calibrated or explicitly pixel-space rows.

        Ball tracking fails closed because there is no ball detector.  Player
        coordinates now fail closed one rung up: there is no validated
        homography, and the retired scalar was measurably wrong by 8-14x.
        ``compute_command`` still returns metadata, which carries the pitch-view
        census and the calibration refusal reason.
        """
        if stride < 1:
            raise ValueError("stride must be at least 1")
        if not player_only:
            raise BallTrackingUnavailableError(
                "Baseball ball tracking is unavailable: this adapter runs YOLO "
                "person class 0 only and has no validated fast-ball detector. "
                "Use player_only=True only for pitcher/batter tracking."
            )
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError("Could not open video: %s" % path)
        rows: list[dict[str, object]] = []
        calibrations: list[dict[str, object]] = []
        command_events: list[dict[str, object]] = []
        pitch_frames: list[np.ndarray] = []
        pitch_scales: list[float] = []
        segment_id = 0
        in_pitch_view = False
        source_frame = processed = players_seen = occluded_frames = 0
        previous_gray: Optional[np.ndarray] = None

        def close_pitch_segment() -> None:
            if not compute_command or not pitch_frames:
                return
            target = glove_target(pitch_frames, MotionStableDetector())
            command_events.append({
                "inning": None,
                "target_px": None if target is None else target[:2],
                # Ball tracking is intentionally not fabricated from plate geometry.
                "crossing_px": None,
                "scale_px_per_ft": float(np.median(pitch_scales)) if pitch_scales else None,
            })

        try:
            while max_frames is None or processed < max_frames:
                ok, frame = capture.read()
                if not ok:
                    break
                if source_frame % stride == 0:
                    current_gray = small_gray(frame)
                    cut = previous_gray is not None and detect_cut(previous_gray, current_gray)
                    previous_gray = current_gray
                    if cut:
                        self._centroids.clear()
                    self._geometry = None if cut else self.detect_pitch_geometry(frame)
                    if self._geometry is not None:
                        if not in_pitch_view:
                            segment_id += 1
                            in_pitch_view = True
                        occluded_frames += int(self._geometry.near_edge_occluded)
                        calibrations.append({
                            "frame": source_frame,
                            "segment_id": segment_id,
                            "pixels_per_foot": self._geometry.pixels_per_foot,
                            "mound_centerline": float(self._geometry.mound[0]),
                        })
                        if compute_command:
                            pitch_frames.append(frame.copy())
                            pitch_scales.append(self._geometry.pixels_per_foot)
                        players = self.detect_players_image_space(frame) if image_space else []
                        players_seen += len(players) if image_space else self.count_players(frame, self._geometry)
                        for track_id, point in players:
                            rows.append({"frame": source_frame, "track_id": track_id,
                                         "cls": "player", "x": float(point[0]),
                                         "y": float(point[1]), "coordinate_space": "image_px",
                                         "observation": "observed", "calibration": "none"})
                    else:
                        if in_pitch_view:
                            close_pitch_segment()
                            pitch_frames.clear()
                            pitch_scales.clear()
                        in_pitch_view = False
                    processed += 1
                source_frame += 1
        finally:
            capture.release()
        if in_pitch_view:
            close_pitch_segment()

        self.last_output = pd.DataFrame(rows, columns=IMAGE_SCHEMA if image_space else SCHEMA)
        if not compute_command:
            return self.last_output
        anchored = anchor_calibrations(calibrations, calibrations)[0] if calibrations else []
        metadata: dict[str, object] = {
            "frames_processed": processed,
            "pitch_view_frames": len(calibrations),
            "pitch_segments": len(command_events),
            "calibrations": anchored,
            "raw_calibrations": calibrations,
            "command_events": command_events,
            "command_series": command_series(command_events),
            "ball_tracking": "unsupported",
            "coordinate_calibration": "unavailable",
            "coordinate_calibration_reason": COORDINATE_CALIBRATION_REASON,
            "players_detected_but_unplaced": players_seen,
            "mound_near_edge_occluded_frames": occluded_frames,
            "mound_diameter_feet": MOUND_DIAMETER_FEET,
        }
        return self.last_output, metadata

    def write_csv(self, path: Union[str, Path], rows: Optional[pd.DataFrame] = None) -> None:
        """Write the most recent output, or supplied rows, in normalized schema."""
        write_csv(self.last_output if rows is None else rows, path)
