"""Measure tennis temporal-calibration warm-up on a real bounded clip."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_diagnostics import held_out_service_t_error


def measure(video: Path, max_frames: int) -> dict[str, object]:
    """Return raw-corner accepts and the first frame a stable solve permits."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    adapter = TennisAdapter(detector=lambda _: ())
    raw_accepts = 0
    first_stable = None
    held_out_errors: list[float] = []
    try:
        for frame_number in range(max_frames):
            ok, frame = capture.read()
            if not ok:
                break
            corners = adapter.detect_court_corners(frame)
            raw_accepts += int(corners is not None)
            error = held_out_service_t_error(frame)
            if error is not None:
                held_out_errors.append(error)
            if adapter._stable_homography(frame) is not None and first_stable is None:
                first_stable = frame_number
    finally:
        capture.release()
    return {"video": video.name, "frames": max_frames, "raw_corner_accepts": raw_accepts,
            "first_stable_frame": first_stable, "calibration_updates": adapter._calibration_updates,
            "held_out_right_service_t_count": len(held_out_errors),
            "held_out_right_service_t_error_ft": {
                "median": round(float(np.median(held_out_errors)), 3) if held_out_errors else None,
                "p95": round(float(np.percentile(held_out_errors, 95)), 3) if held_out_errors else None,
            }}


def main() -> int:
    """Print one warm-up measurement as JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-frames", type=int, default=600)
    args = parser.parse_args()
    print(json.dumps(measure(args.video, args.max_frames), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
