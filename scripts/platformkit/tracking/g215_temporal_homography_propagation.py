"""Measure frame-to-frame propagation from one hand-labelled court homography."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    render_overlay,
    solve_homography,
)


SEED_IMAGE_POINTS = np.float32(((350, 400), (835, 420), (390, 696), (990, 730)))
SEED_FRAME = 1600
DEFAULT_FRAME_COUNT = 300
DEFAULT_STRIDE = 1
RENDER_DISTANCES = frozenset((0, 25, 50, 100, 200, 300))


@dataclass(frozen=True)
class MotionDiagnostic:
    """One RANSAC image-motion estimate's traceable diagnostic values."""

    matches: int
    inliers: int
    inlier_ratio: float | None
    rms_reprojection_px: float | None


def _features(image: np.ndarray, orb: cv2.ORB) -> tuple[list[cv2.KeyPoint], np.ndarray | None]:
    return orb.detectAndCompute(image, None)


def estimate_motion(
    source: tuple[list[cv2.KeyPoint], np.ndarray | None],
    destination: tuple[list[cv2.KeyPoint], np.ndarray | None],
) -> tuple[np.ndarray | None, MotionDiagnostic]:
    """Estimate source-image to destination-image projective motion with ORB."""
    source_keys, source_descriptors = source
    destination_keys, destination_descriptors = destination
    if source_descriptors is None or destination_descriptors is None:
        return None, MotionDiagnostic(0, 0, None, None)
    pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(source_descriptors, destination_descriptors, k=2)
    good = [first for first, second in pairs if first.distance < 0.75 * second.distance]
    if len(good) < 4:
        return None, MotionDiagnostic(len(good), 0, None, None)
    source_points = np.float32([source_keys[match.queryIdx].pt for match in good])
    destination_points = np.float32([destination_keys[match.trainIdx].pt for match in good])
    matrix, mask = cv2.findHomography(source_points, destination_points, cv2.RANSAC, 3.0)
    if matrix is None or mask is None or not np.isfinite(matrix).all():
        return None, MotionDiagnostic(len(good), 0, None, None)
    kept = mask.ravel().astype(bool)
    projected = cv2.perspectiveTransform(source_points[kept].reshape(1, -1, 2), matrix)[0]
    errors = np.linalg.norm(projected - destination_points[kept], axis=1)
    return matrix, MotionDiagnostic(
        len(good), int(kept.sum()), float(kept.mean()), float(np.sqrt(np.mean(np.square(errors))))
    )


def compose_image_to_court(seed_image_to_court: np.ndarray, seed_to_frame: np.ndarray) -> np.ndarray:
    """Compose a seed image-to-court map with seed-to-current image motion."""
    return seed_image_to_court @ np.linalg.inv(seed_to_frame)


def project_court_points(image_to_court: np.ndarray, court_points: np.ndarray) -> np.ndarray:
    """Return image-space positions for court points through an inverse homography."""
    return cv2.perspectiveTransform(court_points.reshape(1, -1, 2), np.linalg.inv(image_to_court))[0]


def _read_stride(capture: cv2.VideoCapture, stride: int) -> np.ndarray | None:
    image = None
    for _ in range(stride):
        ok, image = capture.read()
        if not ok:
            return None
    return image


def _write_render(path: Path, image: np.ndarray, image_to_court: np.ndarray, court_points: np.ndarray) -> None:
    overlay = render_overlay(image, image_to_court, "wnba", project_court_points(image_to_court, court_points))
    if not cv2.imwrite(str(path), overlay):
        raise OSError(f"could not write {path}")


def measure_propagation(
    video_path: Path,
    output_dir: Path,
    seed_frame: int = SEED_FRAME,
    frame_count: int = DEFAULT_FRAME_COUNT,
    stride: int = DEFAULT_STRIDE,
) -> list[dict[str, object]]:
    """Propagate one WNBA G140 seed and write bounded measurement artifacts."""
    if frame_count < 1 or stride < 1:
        raise ValueError("frame_count and stride must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, seed_frame)
    ok, seed_image = capture.read()
    if not ok:
        raise RuntimeError(f"could not decode seed frame {seed_frame}")
    court_points = court_points_for_sport("wnba")
    seed_image_to_court = solve_homography(SEED_IMAGE_POINTS, court_points)
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
    seed_gray = cv2.cvtColor(seed_image, cv2.COLOR_BGR2GRAY)
    seed_features = _features(seed_gray, orb)
    previous_features = seed_features
    seed_to_current = np.eye(3, dtype=np.float64)
    records: list[dict[str, object]] = []
    _write_render(output_dir / "render_distance_0000.jpg", seed_image, seed_image_to_court, court_points)
    for distance in range(1, frame_count + 1):
        current = _read_stride(capture, stride)
        if current is None:
            break
        current_features = _features(cv2.cvtColor(current, cv2.COLOR_BGR2GRAY), orb)
        step, step_diagnostic = estimate_motion(previous_features, current_features)
        direct, direct_diagnostic = estimate_motion(seed_features, current_features)
        record: dict[str, object] = {
            "distance_frames": distance * stride,
            "source_frame": seed_frame + distance * stride,
            "propagated": step is not None,
            "step": asdict(step_diagnostic),
            "direct_seed": asdict(direct_diagnostic),
            "paint_corner_drift_median_px": None,
            "paint_corner_drift_max_px": None,
        }
        if step is not None:
            seed_to_current = step @ seed_to_current
            propagated = compose_image_to_court(seed_image_to_court, seed_to_current)
            if direct is not None:
                direct_image_to_court = compose_image_to_court(seed_image_to_court, direct)
                drift = np.linalg.norm(
                    project_court_points(propagated, court_points)
                    - project_court_points(direct_image_to_court, court_points),
                    axis=1,
                )
                record["paint_corner_drift_median_px"] = float(np.median(drift))
                record["paint_corner_drift_max_px"] = float(np.max(drift))
            if distance * stride in RENDER_DISTANCES:
                _write_render(output_dir / f"render_distance_{distance * stride:04d}.jpg", current, propagated, court_points)
        records.append(record)
        previous_features = current_features
    capture.release()
    with (output_dir / "drift_records.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            writer.writerow({key: json.dumps(value) if isinstance(value, dict) else value for key, value in record.items()})
    (output_dir / "run_summary.json").write_text(
        json.dumps({"seed_frame": seed_frame, "frame_count_requested": frame_count, "stride": stride,
                    "frames_propagated": sum(bool(row["propagated"]) for row in records), "records": records}, indent=2) + "\n",
        encoding="ascii",
    )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed-frame", type=int, default=SEED_FRAME)
    parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    args = parser.parse_args()
    records = measure_propagation(args.video, args.output_dir, args.seed_frame, args.frame_count, args.stride)
    print(f"PROPAGATED_FRAMES={sum(bool(row['propagated']) for row in records)}")
    print(f"DECODED_DISTANCE_FRAMES={len(records) * args.stride}")


if __name__ == "__main__":
    main()
