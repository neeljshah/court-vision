"""Evaluate zero-shot TrackNetV3 ball candidates on cut-free tennis frames."""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import cv2

from domains.tennis.tracking.segmenter import detect_cut, small_gray


def read_in_play_segment(video: Path, start: int, count: int) -> list:
    """Read a contiguous segment and reject it when segmenter sees a scene cut."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    capture.set(cv2.CAP_PROP_POS_FRAMES, start)
    frames = []
    previous = None
    try:
        for _ in range(count):
            ok, frame = capture.read()
            if not ok:
                raise ValueError("Video ended before requested segment")
            current = small_gray(frame)
            if previous is not None and detect_cut(previous, current):
                raise ValueError("Segmenter found a scene cut in requested segment")
            previous = current
            frames.append(frame)
    finally:
        capture.release()
    return frames


def render_overlays(frames: list, points: list, output: Path, limit: int) -> list[str]:
    """Render up to limit source-frame overlays and return their paths."""
    output.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for index, (frame, point) in enumerate(zip(frames, points)):
        if len(paths) == limit:
            break
        if point is None:
            continue
        rendered = frame.copy()
        x, y, confidence = point
        cv2.drawMarker(rendered, (round(x), round(y)), (0, 0, 255),
                       markerType=cv2.MARKER_CROSS, markerSize=22, thickness=2)
        label = "TrackNetV3 %.3f" % confidence
        cv2.putText(rendered, "%04d %s" % (index, label), (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
        path = output / ("frame_%03d.png" % index)
        if not cv2.imwrite(str(path), rendered):
            raise OSError("Could not write overlay: %s" % path)
        paths.append(str(path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--ball-module", required=True, type=Path)
    parser.add_argument("--start", required=True, type=int)
    parser.add_argument("--count", default=40, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--overlay-limit", default=10, type=int)
    args = parser.parse_args()

    spec = importlib.util.spec_from_file_location("tracknetv3_ball", args.ball_module)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load ball module: %s" % args.ball_module)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    frames = read_in_play_segment(args.video, args.start, args.count)
    points = module.TrackNetV3Detector(args.checkpoint).detect_sequence(frames)
    detected = sum(point is not None for point in points)
    # This is the frozen harness formula with the independently decoded,
    # segmenter-approved frame set as its denominator: unique ball frames / n_frames.
    result = {
        "video": str(args.video), "start_frame": args.start, "n_frames": len(frames),
        "ball_rows": detected, "ball_valid": detected / len(frames),
        "overlay_paths": render_overlays(frames, points, args.output_dir, args.overlay_limit),
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
