"""Compare AGPL YOLOv8n with an explicitly supplied YOLOX ONNX model.

This is an offline measurement tool.  It neither writes tracking rows nor
loads a sport adapter's default detector; the adapter receives each measured
box list directly so its real geometry/selection filter is exercised.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

if __package__:
    from scripts.platformkit.detection.shim import YoloxOnnxBackend, detector_profile, get_box_detector
else:  # Supports running a copied measurement script on the pod.
    from shim import YoloxOnnxBackend, detector_profile, get_box_detector


BoxDetector = Callable[[np.ndarray], list[list[float]]]
_VIDEO_SPORT = {
    "baseball": "mlb__mlb_7T-rpI5l0ro.mp4",
    "football": "football__football_20pezoC5jRQ.mp4",
    "soccer": "soccer__soccer_AgspyOj5BPk.mp4",
    "tennis": "tennis__tennis_3x3eEWCZmWQ.mp4",
}


@dataclass
class Summary:
    frames: int = 0
    boxes: int = 0
    areas: list[float] = field(default_factory=list)
    filter_frames: int = 0
    filtered: int = 0
    filter_errors: dict[str, int] = field(default_factory=dict)

    def add(self, boxes: list[list[float]], accepted: int | None, filter_error: str | None) -> None:
        self.frames += 1
        self.boxes += len(boxes)
        self.areas.extend((box[2] - box[0]) * (box[3] - box[1]) for box in boxes)
        if accepted is not None:
            self.filter_frames += 1
            self.filtered += accepted
        if filter_error is not None:
            self.filter_errors[filter_error] = self.filter_errors.get(filter_error, 0) + 1

    def as_dict(self) -> dict[str, float | int | None]:
        quantiles = np.percentile(self.areas, (50, 90)).tolist() if self.areas else [None, None]
        return {
            "frames": self.frames,
            "detections": self.boxes,
            "detections_per_frame": round(self.boxes / self.frames, 3) if self.frames else None,
            "box_area_px2_p50": None if quantiles[0] is None else round(quantiles[0], 1),
            "box_area_px2_p90": None if quantiles[1] is None else round(quantiles[1], 1),
            "filter_solved_frames": self.filter_frames,
            "surviving_detections": self.filtered,
            "survivors_per_solved_frame": round(self.filtered / self.filter_frames, 3) if self.filter_frames else None,
            "survival_rate": round(self.filtered / self.boxes, 4) if self.boxes else None,
            "filter_errors": self.filter_errors,
        }


def _ultralytics_detector(weights: Path) -> BoxDetector:
    from ultralytics import YOLO

    model = YOLO(str(weights))

    def detect(frame: np.ndarray) -> list[list[float]]:
        result = model(frame, classes=[0], imgsz=640, conf=0.25, verbose=False)[0]
        if result.boxes is None:
            return []
        return [box + [float(score)] for box, score in zip(
            result.boxes.xyxy.cpu().numpy().tolist(), result.boxes.conf.cpu().numpy().tolist()
        )]

    return detect


def _yolox_detector(weights: Path, sport: str, conf: float | None) -> BoxDetector:
    if conf is None:
        return get_box_detector("yolox", weights, sport)
    profile = detector_profile(sport)
    backend = YoloxOnnxBackend(weights, profile.imgsz, conf, profile.class_ids)

    def detect(frame: np.ndarray) -> list[list[float]]:
        return [[item.x1, item.y1, item.x2, item.y2, item.conf] for item in backend.detect(frame)]

    return detect


def _sport_filter(sport: str, detector: BoxDetector, frame: np.ndarray) -> int | None:
    """Return count retained by the sport's present geometry/selection path."""
    if sport == "baseball":
        from domains.baseball.tracking.adapter import BaseballAdapter

        adapter = BaseballAdapter(detector)
        geometry = adapter.detect_pitch_geometry(frame)
        return None if geometry is None else adapter.count_players(frame, geometry)
    if sport == "football":
        from domains.football.tracking.adapter import FootballAdapter

        adapter = FootballAdapter(detector)
        homography = adapter._stable_homography(frame)
        return None if homography is None else len(adapter._track_players(detector(frame), homography))
    if sport == "soccer":
        from domains.soccer.tracking.adapter import SoccerAdapter

        adapter = SoccerAdapter(detector)
        homography = adapter._stable_homography(frame)
        return None if homography is None else len(adapter.detect_players(frame, homography))
    if sport == "tennis":
        from domains.tennis.tracking.adapter import TennisAdapter

        adapter = TennisAdapter(detector, tracker_conf=0.0)
        homography = adapter._stable_homography(frame)
        return None if homography is None else len(adapter.detect_players(frame, homography))
    raise ValueError(f"unsupported sport {sport!r}")


def measure(sport: str, video: Path, yolov8: BoxDetector, yolox: BoxDetector, frames: int) -> dict[str, object]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    summaries = {"yolov8n": Summary(), "yolox_s": Summary()}
    try:
        for _ in range(frames):
            ok, frame = capture.read()
            if not ok:
                break
            for name, detector in (("yolov8n", yolov8), ("yolox_s", yolox)):
                boxes = detector(frame)
                try:
                    accepted, filter_error = _sport_filter(sport, lambda _: boxes, frame), None
                except Exception as error:  # The report must preserve a broken producer honestly.
                    accepted, filter_error = None, type(error).__name__
                summaries[name].add(boxes, accepted, filter_error)
    finally:
        capture.release()
    return {"sport": sport, "video": video.name, "models": {name: item.as_dict() for name, item in summaries.items()}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video-dir", type=Path, required=True)
    parser.add_argument("--yolov8-weights", type=Path, required=True)
    parser.add_argument("--yolox-onnx", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--yolox-conf", type=float, default=None)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.frames < 1:
        raise ValueError("frames must be positive")
    yolov8 = _ultralytics_detector(arguments.yolov8_weights)
    results = []
    for sport, filename in _VIDEO_SPORT.items():
        yolox = _yolox_detector(arguments.yolox_onnx, sport, arguments.yolox_conf)
        results.append(measure(sport, arguments.video_dir / filename, yolov8, yolox, arguments.frames))
    arguments.output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote measured detector delta to {arguments.output}")


if __name__ == "__main__":
    main()
