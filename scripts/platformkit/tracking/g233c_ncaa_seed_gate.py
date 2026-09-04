"""Render G233c's fixed NCAA seed after its frame-provenance check."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    render_overlay,
    solve_homography,
)


SOURCE_FRAME = 46154
SPORT = "ncaa_basketball"
LABEL_RESOLUTION = (640, 360)
VIDEO_RESOLUTION = (1920, 1080)
LABEL_POINTS = np.float32(((38, 223), (39, 289), (274, 224), (273, 282)))
SCALE_FACTOR = 3.0


def scaled_image_points() -> np.ndarray:
    """Return the four ordered G140 coordinates at native video scale."""
    return LABEL_POINTS * SCALE_FACTOR


def sha256_path(path: Path) -> str:
    """Return a streaming SHA-256 for the named input artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def measure(seed_image_path: Path, output_dir: Path) -> dict[str, object]:
    """Write G233c's seed render and traceability record from an exact decoded PNG."""
    image = cv2.imread(str(seed_image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(seed_image_path)
    rendered, homography, court_points = render_seed(image)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_path = output_dir / "seed_render_source_frame_46154.jpg"
    if not cv2.imwrite(str(render_path), rendered):
        raise OSError(f"could not write {render_path}")
    height, width = image.shape[:2]
    record: dict[str, object] = {
        "source_frame_zero_based": SOURCE_FRAME,
        "frame_accurate_decode_method": "ffmpeg select=eq(n,46154) after input; no input-side -ss",
        "decoded_seed_image": {
            "path": str(seed_image_path.resolve()),
            "bytes": seed_image_path.stat().st_size,
            "sha256": sha256_path(seed_image_path),
            "resolution_px": [width, height],
        },
        "label_resolution_px": list(LABEL_RESOLUTION),
        "scale_factor": SCALE_FACTOR,
        "label_image_points_px": LABEL_POINTS.astype(float).tolist(),
        "scaled_image_points_px": scaled_image_points().astype(float).tolist(),
        "sport": SPORT,
        "court_points_ft": court_points.astype(float).tolist(),
        "homography_image_to_court": homography.astype(float).tolist(),
        "render_filename": render_path.name,
    }
    (output_dir / "seed_gate_record.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="ascii"
    )
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-image", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    record = measure(args.seed_image, args.output_dir)
    print(f"SOURCE_FRAME={record['source_frame_zero_based']}")
    print(f"DECODED_RESOLUTION={record['decoded_seed_image']['resolution_px'][0]}x{record['decoded_seed_image']['resolution_px'][1]}")
    print(f"SCALE_FACTOR={record['scale_factor']:.1f}")


if __name__ == "__main__":
    main()
