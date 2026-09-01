"""Measure whether baseball broadcast frames can support a ground-plane homography.

Two independent passes over one clip:

* ``landmark_census`` needs no detector.  It measures the pitcher's-mound
  horizontal chord, which is an exactly known 18-foot ground distance, and
  converts it into the lateral world width the frame actually covers.  A
  four-point infield homography needs first and third base in frame; those sit
  63.64 feet either side of the plate-mound line, so the census answers
  "is that even geometrically possible" by measurement rather than assumption.
* ``harness_metrics`` runs the real adapter and the real tracking harness so
  before/after coordinate quality is read from the shipping gate, never from a
  bespoke bound.

Run: python scripts/platformkit/baseball_calib_probe.py <video> [start] [frames] [stride]
"""
from __future__ import annotations

import json
import sys

import cv2
import numpy as np

from domains.baseball.tracking.adapter import BaseballAdapter

BASE_LATERAL_OFFSET_FEET = 63.64
# A 63.64-foot half-width needs a mound chord of only 18/127.28 of the frame, so
# the census floor is set well below that: the measurement must be able to
# report a wide-enough framing if one exists, instead of excluding it by fiat.
# The rest of the pitch-view gate still applies.  Relaxing the floor alone was
# measured to admit cheerleaders' dirt-coloured uniforms on grass; the
# infield-band test is what rejects those, so the census keeps it.
CENSUS_MIN_CHORD_FRACTION = 0.08


def landmark_census(path: str, start: int = 0, frames: int = 400,
                    stride: int = 3) -> dict:
    """Measure lateral world coverage and mound visibility over sampled frames."""
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % path)
    if start:
        capture.set(cv2.CAP_PROP_POS_FRAMES, start)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1
    gate = BaseballAdapter(detector=lambda frame: [])
    chords: list[float] = []
    bounded = occluded = sampled = 0
    try:
        for _ in range(frames):
            for _ in range(stride):
                ok, frame = capture.read()
                if not ok:
                    break
            if not ok:
                break
            sampled += 1
            geometry = gate.detect_pitch_geometry(frame, CENSUS_MIN_CHORD_FRACTION)
            if geometry is None:
                continue
            bounded += 1
            chords.append(geometry.mound_chord_px)
            occluded += int(geometry.near_edge_occluded)
    finally:
        capture.release()
    if not chords:
        return {"sampled": sampled, "pitch_view_frames": 0,
                "note": "no frame passed the pitch-view gate"}
    array = np.array(chords)
    px_per_foot = array / 18.0
    fov = width / px_per_foot
    return {
        "sampled": sampled,
        "pitch_view_frames": bounded,
        "mound_chord_px_p05": round(float(np.percentile(array, 5)), 2),
        "mound_chord_px_p50": round(float(np.median(array)), 2),
        "census_min_chord_fraction": CENSUS_MIN_CHORD_FRACTION,
        "lateral_px_per_foot_p50": round(float(np.median(px_per_foot)), 2),
        "lateral_fov_feet_p50": round(float(np.median(fov)), 2),
        "lateral_fov_feet_p95": round(float(np.percentile(fov, 95)), 2),
        "base_lateral_offset_feet": BASE_LATERAL_OFFSET_FEET,
        # A four-point infield homography needs 1B and 3B in frame.
        "frames_that_could_contain_1b_and_3b": int(
            (fov / 2.0 >= BASE_LATERAL_OFFSET_FEET).sum()),
        "mound_near_edge_occluded_frac": round(occluded / bounded, 4),
    }


def harness_metrics(path: str, start: int = 0, frames: int = 400,
                    stride: int = 3) -> dict:
    """Run the real adapter and the real tracking harness on one clip."""
    from domains.baseball.tracking.adapter import BaseballAdapter
    from scripts.platformkit.tracking_harness import evaluate

    adapter = BaseballAdapter()
    if start:
        rows, metadata = _run_from(adapter, path, start, frames, stride)
    else:
        result = adapter.process_video(path, max_frames=frames, stride=stride,
                                       player_only=True, compute_command=True)
        rows, metadata = result
    report = json.loads(evaluate(rows, "baseball").to_json())
    keep = ("n_frames", "coverage_pct", "oob_pct", "jump_p95",
            "median_step_distance", "ball_valid_pct", "passed", "failures")
    out = {"rows": int(len(rows))}
    out.update({key: report[key] for key in keep})
    for key in ("pitch_view_frames", "pitch_segments", "coordinate_calibration",
                "players_detected_but_unplaced", "mound_near_edge_occluded_frames",
                "coordinate_calibration_reason"):
        if key in metadata:
            out[key] = metadata[key]
    return out


def _run_from(adapter, path, start, frames, stride):
    """Process a clip from a frame offset, seeking before the adapter reads."""
    original = cv2.VideoCapture

    class _Offset(original):  # ponytail: adapter opens its own reader; seek inside it
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.set(cv2.CAP_PROP_POS_FRAMES, start)

    cv2.VideoCapture = _Offset
    try:
        return adapter.process_video(path, max_frames=frames, stride=stride,
                                     player_only=True, compute_command=True)
    finally:
        cv2.VideoCapture = original


def main(argv: list[str]) -> int:
    path = argv[0]
    start = int(argv[1]) if len(argv) > 1 else 0
    frames = int(argv[2]) if len(argv) > 2 else 400
    stride = int(argv[3]) if len(argv) > 3 else 3
    out = {
        "video": path, "start": start, "sampled_frames": frames, "stride": stride,
        "landmark_census": landmark_census(path, start, frames, stride),
        "harness": harness_metrics(path, start, frames, stride),
    }
    sys.stdout.write(json.dumps(out, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
