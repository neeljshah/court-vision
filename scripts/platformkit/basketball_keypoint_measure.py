"""Measure fail-closed basketball landmark recovery on a real video.

Run on the pod with a copied clip and a bounded sample budget.  This reports
what the provider actually found; it never creates rows or treats a cached
homography as a fresh calibration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from domains.basketball.tracking.keypoints import BasketballKeypointProvider
from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator


def measure(video: Path, max_frames: int) -> dict[str, object]:
    """Return landmark and fresh-solve counts from a bounded real-video scan."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open video: {}".format(video))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    stride = max(1, total // max_frames) if total else 1
    provider = BasketballKeypointProvider()
    calibrator = TemporalCalibrator("basketball", provider=provider)
    sampled = detected = fresh_solves = held_out_possible = 0
    landmark_histogram: dict[str, int] = {}
    frame_index = 0
    while sampled < max_frames:
        ok, frame = capture.read()
        if not ok:
            break
        if frame_index % stride:
            frame_index += 1
            continue
        sampled += 1
        landmarks = provider.detect(frame)
        if landmarks:
            detected += 1
            for name in landmarks:
                landmark_histogram[name] = landmark_histogram.get(name, 0) + 1
        result = calibrator.update(landmarks)
        if result.homography is not None and not result.reused_last_good:
            fresh_solves += 1
        if len(landmarks) >= 5:
            held_out_possible += 1
        frame_index += 1
    capture.release()
    return {
        "video": video.name, "source_frames": total, "sampled_frames": sampled,
        "sample_stride": stride, "frames_with_named_landmarks": detected,
        "fresh_homography_frames": fresh_solves,
        "frames_with_held_out_landmark": held_out_possible,
        "landmark_counts": landmark_histogram,
        "verdict": ("S2 candidate" if fresh_solves and held_out_possible
                    else "not S2: no independently held-out landmark validation"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure basketball keypoint recovery.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-frames", type=int, default=600)
    args = parser.parse_args()
    if args.max_frames < 1:
        raise ValueError("max-frames must be positive")
    print(json.dumps(measure(args.video, args.max_frames), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
