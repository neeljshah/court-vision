"""Measure tennis endpoint and intersection anchor errors at a fixed timebase."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import cv2
import numpy as np

PROJECT_ROOT = Path(os.environ["TENNIS_MEASURE_PROJECT_ROOT"]) if "TENNIS_MEASURE_PROJECT_ROOT" in os.environ else Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.tennis.tracking.adapter import CROSS_RATIO, TennisAdapter
from scripts.platformkit.tracking_timebase import sampling_plan


def _court_lines(frame: np.ndarray) -> tuple[list[list[np.ndarray]], list[list[np.ndarray]]] | None:
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    found = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                             minLineLength=max(40, width // 12), maxLineGap=20)
    if found is None:
        return None
    horizontal, vertical = [], []
    for raw in found[:, 0, :]:
        line = raw.astype(float)
        dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
        if dx >= 1.5 * dy:
            horizontal.append(line)
        elif dy > dx:
            vertical.append(line)
    if len(horizontal) < 2 or len(vertical) < 2:
        return None
    adapter = TennisAdapter(detector=lambda _: ())
    h = adapter._cluster_lines(horizontal, True, (height, width))
    v = adapter._cluster_lines(vertical, False, (height, width))
    if len(h) < 4 or len(v) != 5:
        return None
    across = [adapter._line_position(adapter._fit_line(cluster), False, (height, width))
              for cluster in v]
    denominator = (across[2] - across[1]) * (across[4] - across[0])
    if abs(denominator) < 1e-6:
        return None
    ratio = (across[2] - across[0]) * (across[4] - across[1]) / denominator
    return (h, v) if abs(ratio - CROSS_RATIO) <= 0.05 else None


def landmark_error(frame: np.ndarray, variant: str) -> float | None:
    """Return independent right-service-T error; it never enters the fit."""
    clustered = _court_lines(frame)
    if clustered is None:
        return None
    h, v = clustered
    adapter = TennisAdapter(detector=lambda _: ())
    far, opposite_service, near_service, near = [adapter._fit_line(h[index])
                                                  for index in (0, 1, -2, -1)]
    left, right, centre = (adapter._fit_line(v[index]) for index in (0, -1, 2))
    near_left, near_right = adapter._intersection(near, left), adapter._intersection(near, right)
    if variant == "intersection":
        far_left, service_t = adapter._intersection(far, left), adapter._intersection(near_service, centre)
    else:
        far_left = adapter._point_at_row(left, adapter._endpoint_rows(v[0])[0])
        service_t = adapter._point_at_row(centre, adapter._endpoint_rows(v[2])[1])
    opposite_t = (adapter._intersection(opposite_service, centre) if variant == "intersection"
                  else adapter._point_at_row(centre, adapter._endpoint_rows(v[2])[0]))
    if (near_left is None or near_right is None or far_left is None or service_t is None or
            opposite_t is None or not far_left[1] < service_t[1] < near_left[1]):
        return None
    homography, _ = cv2.findHomography(np.float32((near_left, near_right, far_left, service_t)),
                                       np.float32(((0, 0), (0, 36), (78, 0), (18, 18))))
    if homography is None:
        return None
    predicted = adapter._project(opposite_t, homography)
    return float(np.linalg.norm(predicted - np.float32((60.0, 18.0))))


def measure(video: Path, seconds: float, variant: str) -> dict[str, object]:
    """Measure one arm with equal wall-clock duration and 0.1-second samples."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    plan = sampling_plan(fps)
    limit = int(round(seconds * fps))
    errors: list[float] = []
    try:
        for frame_number in range(limit):
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % plan.stride == 0:
                error = landmark_error(frame, variant)
                if error is not None:
                    errors.append(error)
    finally:
        capture.release()
    return {"video": video.name, "variant": variant, "duration_seconds": seconds,
            "source_fps": fps, "stride": plan.stride,
            "sample_interval_seconds": plan.sample_interval_seconds,
            "held_out_right_service_t_count": len(errors),
            "held_out_right_service_t_error_ft": {
                "median": round(float(np.median(errors)), 3) if errors else None,
                "p95": round(float(np.percentile(errors, 95)), 3) if errors else None}}


def main() -> int:
    """Print one measured anchor arm as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--variant", choices=("endpoint", "intersection"), required=True)
    parser.add_argument("--seconds", type=float, default=0.8)
    args = parser.parse_args()
    print(json.dumps(measure(args.video, args.seconds, args.variant), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
