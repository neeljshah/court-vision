"""Emit the immutable tennis-calibration JSONL trace from SynthCal outputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .solve import load_model, predict


COURT = {
    "doubles_bl": (0.0, 0.0), "doubles_br": (78.0, 0.0),
    "doubles_tr": (78.0, 36.0), "doubles_tl": (0.0, 36.0),
    "singles_bl": (0.0, 4.5), "singles_br": (78.0, 4.5),
    "singles_tr": (78.0, 31.5), "singles_tl": (0.0, 31.5),
    "left_service_t": (18.0, 18.0), "right_service_t": (60.0, 18.0),
}
MODEL_TO_JUDGE = {
    "corner_0.0_0.0": "doubles_bl", "corner_78.0_0.0": "doubles_br",
    "corner_78.0_36.0": "doubles_tr", "corner_0.0_36.0": "doubles_tl",
    "singles_0.0_4.5": "singles_bl", "singles_78.0_4.5": "singles_br",
    "singles_78.0_31.5": "singles_tr", "singles_0.0_31.5": "singles_tl",
    "t_18.0": "left_service_t", "t_60.0": "right_service_t",
}
SOLVE_LANDMARKS = ("doubles_bl", "doubles_br", "doubles_tr", "doubles_tl")


def sample_frame_indices(frame_count: int, count: int) -> list[int]:
    """Return deterministic, whole-video frame positions without duplicate frames."""
    if frame_count < 1 or count < 1:
        return []
    return np.linspace(0, frame_count - 1, min(frame_count, count), dtype=int).tolist()


def record_from_observations(frame: int, observed: dict[str, list[float]]) -> dict[str, object] | None:
    """Fit an image-to-court H using only the declared solve landmarks."""
    if not all(name in observed for name in SOLVE_LANDMARKS):
        return None
    image = np.float32([observed[name] for name in SOLVE_LANDMARKS])
    court = np.float32([COURT[name] for name in SOLVE_LANDMARKS])
    homography = cv2.getPerspectiveTransform(image, court)
    if not np.isfinite(homography).all() or abs(float(homography[2, 2])) < 1e-12:
        return None
    return {"frame": int(frame), "image_to_court": homography.tolist(),
            "observed": observed, "solve_landmarks": list(SOLVE_LANDMARKS)}


def emit_trace(video: Path, weights: Path, output: Path, frames: int = 20,
               confidence: float = 0.0, device: str = "cpu") -> int:
    """Write a judge-contract JSONL trace for one video and return its row count."""
    model, names, sport = load_model(weights, device)
    if sport != "tennis":
        raise ValueError("tennis weights required")
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    output.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        positions = sample_frame_indices(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), frames)
        with output.open("w", encoding="ascii", newline="\n") as handle:
            for frame_index in positions:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, image = capture.read()
                if not ok:
                    continue
                pixels, scores = predict(model, image, names, device)
                observed = {
                    judge_name: [float(point[0]), float(point[1])]
                    for name, point, score in zip(names, pixels, scores)
                    if name in MODEL_TO_JUDGE and float(score) >= confidence
                    for judge_name in (MODEL_TO_JUDGE[name],)
                }
                row = record_from_observations(frame_index, observed)
                if row is not None:
                    handle.write(json.dumps(row, allow_nan=False, separators=(",", ":")) + "\n")
                    written += 1
    finally:
        capture.release()
    return written


def _outputs(directory: Path, videos: Iterable[Path]) -> Iterable[tuple[Path, Path]]:
    for video in videos:
        yield video, directory / (video.stem + ".jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", required=True, type=Path)
    parser.add_argument("--video", required=True, type=Path, action="append")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--frames-per-video", type=int, default=20)
    parser.add_argument("--confidence", type=float, default=0.0)
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.frames_per_video < 1:
        parser.error("--frames-per-video must be positive")
    for video, output in _outputs(args.output_dir, args.video):
        count = emit_trace(video, args.weights, output, args.frames_per_video,
                           args.confidence, args.device)
        print("TRACE video=%s rows=%d output=%s" % (video, count, output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
