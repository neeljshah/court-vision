"""Render the exact G233b NCAA hand-label seed before any propagation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    render_overlay,
    solve_homography,
)


SOURCE_FRAME = 28171
SPORT = "ncaa_basketball"
LABEL_RESOLUTION = (640, 360)
VIDEO_RESOLUTION = (1920, 1080)
LABEL_POINTS = np.float32(((38, 223), (39, 289), (274, 224), (273, 282)))
SCALE_FACTOR = 3.0


def scaled_image_points() -> np.ndarray:
    """Return the four ordered G140 coordinates at the native video scale."""
    return LABEL_POINTS * SCALE_FACTOR


def decode_frame_sequentially(video_path: Path, source_frame: int = SOURCE_FRAME) -> np.ndarray:
    """Decode from frame zero through the zero-based requested source-frame index."""
    if source_frame < 0:
        raise ValueError("source_frame must be non-negative")
    capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"could not open {video_path}")
        image: np.ndarray | None = None
        for index in range(source_frame + 1):
            ok, image = capture.read()
            if not ok or image is None:
                raise RuntimeError(f"decode ended before source frame {source_frame} at {index}")
        return image
    finally:
        capture.release()


def render_seed(image: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve and inverse-project the fixed NCAA seed geometry onto one image."""
    height, width = image.shape[:2]
    if (width, height) != VIDEO_RESOLUTION:
        raise ValueError(f"expected {VIDEO_RESOLUTION}, decoded {(width, height)}")
    image_points = scaled_image_points()
    court_points = court_points_for_sport(SPORT)
    homography = solve_homography(image_points, court_points)
    if not np.isfinite(homography).all() or abs(float(np.linalg.det(homography))) < 1e-12:
        raise ValueError("seed homography is non-finite or singular")
    return render_overlay(image, homography, SPORT, image_points), homography, court_points


def measure(video_path: Path, output_dir: Path) -> dict[str, object]:
    """Write only the seed overlay and its traceability record."""
    output_dir.mkdir(parents=True, exist_ok=False)
    image = decode_frame_sequentially(video_path)
    rendered, homography, court_points = render_seed(image)
    render_path = output_dir / "seed_render_source_frame_28171.jpg"
    if not cv2.imwrite(str(render_path), rendered):
        raise OSError(f"could not write {render_path}")
    height, width = image.shape[:2]
    record: dict[str, object] = {
        "source_frame_zero_based": SOURCE_FRAME,
        "frame_accurate_decode_method": "sequential cv2.VideoCapture.read from frame index 0 through 28171 inclusive",
        "video_path": str(video_path),
        "decoded_resolution_px": [width, height],
        "label_resolution_px": list(LABEL_RESOLUTION),
        "scale_factor": SCALE_FACTOR,
        "label_image_points_px": LABEL_POINTS.astype(float).tolist(),
        "scaled_image_points_px": scaled_image_points().astype(float).tolist(),
        "sport": SPORT,
        "court_points_ft": court_points.astype(float).tolist(),
        "homography_image_to_court": homography.astype(float).tolist(),
        "render_filename": render_path.name,
    }
    (output_dir / "seed_gate_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="ascii")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    record = measure(args.video, args.output_dir)
    print(f"SOURCE_FRAME={record['source_frame_zero_based']}")
    print(f"DECODED_RESOLUTION={record['decoded_resolution_px'][0]}x{record['decoded_resolution_px'][1]}")
    print(f"SCALE_FACTOR={record['scale_factor']:.1f}")


if __name__ == "__main__":
    main()
