"""Compare G215 chained propagation with direct seed-to-frame homographies."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import (
    court_points_for_sport,
    render_overlay,
    solve_homography,
)
from scripts.platformkit.tracking.g215_temporal_homography_propagation import (
    DEFAULT_STRIDE,
    SEED_FRAME,
    SEED_IMAGE_POINTS,
    _features,
    _read_stride,
    compose_image_to_court,
    estimate_motion,
    project_court_points,
)


DEFAULT_FRAME_COUNT = 1200
DEFAULT_RENDER_DISTANCES = frozenset((0, 200, 400, 600, 800, 1000, 1200))


def _write_render(path: Path, image: np.ndarray, image_to_court: np.ndarray, court: np.ndarray) -> None:
    corners = project_court_points(image_to_court, court)
    if not cv2.imwrite(str(path), render_overlay(image, image_to_court, "wnba", corners)):
        raise OSError(f"could not write {path}")


def _paint_drift(left: np.ndarray, right: np.ndarray, court: np.ndarray) -> tuple[float, float]:
    distances = np.linalg.norm(project_court_points(left, court) - project_court_points(right, court), axis=1)
    return float(np.median(distances)), float(np.max(distances))


def _direct_reference_drift(direct: np.ndarray, court: np.ndarray) -> tuple[float, float]:
    """Apply G215's image-space paint-corner drift measure to its direct reference."""
    return _paint_drift(direct, direct, court)


def _record(
    distance: int,
    source_frame: int,
    chained: np.ndarray | None,
    direct: np.ndarray | None,
    step: object,
    direct_diagnostic: object,
    court: np.ndarray,
) -> dict[str, object]:
    chain_median = chain_maximum = direct_median = direct_maximum = None
    if chained is not None and direct is not None:
        chain_median, chain_maximum = _paint_drift(chained, direct, court)
    if direct is not None:
        direct_median, direct_maximum = _direct_reference_drift(direct, court)
    return {
        "distance_frames": distance,
        "source_frame": source_frame,
        "chained_eligible": chained is not None,
        "direct_seed_eligible": direct is not None,
        "chained_paint_corner_drift_median_px": chain_median,
        "chained_paint_corner_drift_max_px": chain_maximum,
        "direct_seed_paint_corner_drift_median_px": direct_median,
        "direct_seed_paint_corner_drift_max_px": direct_maximum,
        "step": asdict(step),
        "direct_seed": asdict(direct_diagnostic),
    }


def _write_records(records: list[dict[str, object]], output_dir: Path, seed_frame: int, frame_count: int, stride: int) -> None:
    fields = list(records[0])
    with (output_dir / "drift_records.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow({key: json.dumps(value) if isinstance(value, dict) else value for key, value in record.items()})
    summary = {
        "seed_frame": seed_frame,
        "frame_count_requested": frame_count,
        "stride": stride,
        "frames_chained_eligible": sum(bool(row["chained_eligible"]) for row in records),
        "frames_direct_seed_eligible": sum(bool(row["direct_seed_eligible"]) for row in records),
        "records": records,
    }
    (output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")


def measure_paired(
    video_path: Path,
    output_dir: Path,
    seed_frame: int = SEED_FRAME,
    frame_count: int = DEFAULT_FRAME_COUNT,
    stride: int = DEFAULT_STRIDE,
    render_distances: frozenset[int] = DEFAULT_RENDER_DISTANCES,
) -> list[dict[str, object]]:
    """Measure chained and direct homographies over identical decoded frames."""
    if frame_count < 1 or stride < 1:
        raise ValueError("frame_count and stride must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    chain_dir = output_dir / "chained_renders"
    direct_dir = output_dir / "direct_seed_renders"
    chain_dir.mkdir(exist_ok=True)
    direct_dir.mkdir(exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, seed_frame)
    ok, seed_image = capture.read()
    if not ok:
        raise RuntimeError(f"could not decode seed frame {seed_frame}")
    court = court_points_for_sport("wnba")
    seed_image_to_court = solve_homography(SEED_IMAGE_POINTS, court)
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
    seed_features = _features(cv2.cvtColor(seed_image, cv2.COLOR_BGR2GRAY), orb)
    previous_features = seed_features
    seed_to_current = np.eye(3, dtype=np.float64)
    if 0 in render_distances:
        _write_render(chain_dir / "render_distance_0000.jpg", seed_image, seed_image_to_court, court)
        _write_render(direct_dir / "render_distance_0000.jpg", seed_image, seed_image_to_court, court)
    records: list[dict[str, object]] = []
    for step_index in range(1, frame_count + 1):
        image = _read_stride(capture, stride)
        if image is None:
            break
        current_features = _features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb)
        step, step_diagnostic = estimate_motion(previous_features, current_features)
        seed_to_frame, direct_diagnostic = estimate_motion(seed_features, current_features)
        chained = direct = None
        if step is not None:
            seed_to_current = step @ seed_to_current
            chained = compose_image_to_court(seed_image_to_court, seed_to_current)
        if seed_to_frame is not None:
            direct = compose_image_to_court(seed_image_to_court, seed_to_frame)
        distance = step_index * stride
        records.append(_record(distance, seed_frame + distance, chained, direct, step_diagnostic, direct_diagnostic, court))
        if distance in render_distances:
            if chained is not None:
                _write_render(chain_dir / f"render_distance_{distance:04d}.jpg", image, chained, court)
            if direct is not None:
                _write_render(direct_dir / f"render_distance_{distance:04d}.jpg", image, direct, court)
        previous_features = current_features
    capture.release()
    if not records:
        raise RuntimeError("no frames decoded after seed")
    _write_records(records, output_dir, seed_frame, frame_count, stride)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed-frame", type=int, default=SEED_FRAME)
    parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT)
    parser.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    args = parser.parse_args()
    records = measure_paired(args.video, args.output_dir, args.seed_frame, args.frame_count, args.stride)
    print(f"CHAINED_ELIGIBLE={sum(bool(row['chained_eligible']) for row in records)}")
    print(f"DIRECT_SEED_ELIGIBLE={sum(bool(row['direct_seed_eligible']) for row in records)}")


if __name__ == "__main__":
    main()
