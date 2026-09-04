"""Measure direct-seed WNBA player-foot projections without the tracking route."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g196_homography_from_labelled_corners import court_points_for_sport, render_overlay, solve_homography
from scripts.platformkit.tracking.g215_temporal_homography_propagation import SEED_FRAME, SEED_IMAGE_POINTS, _features, _read_stride, compose_image_to_court, estimate_motion
from scripts.platformkit.tracking.g222_direct_to_seed_propagation import DEFAULT_RENDER_DISTANCES

COURT_LENGTH_FT, COURT_WIDTH_FT, DEFAULT_FRAME_COUNT = 94.0, 50.0, 1200


def outside_distance_ft(x: float, y: float) -> float:
    """Return Euclidean distance outside the declared 94-by-50-foot plane."""
    return math.hypot(max(0.0, -x, x - COURT_WIDTH_FT), max(0.0, -y, y - COURT_LENGTH_FT))


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "median_ft": None, "p90_ft": None, "p99_ft": None, "max_ft": None}
    ordered = sorted(values)
    def q(p: float) -> float:
        position = (len(ordered) - 1) * p
        low, high = math.floor(position), math.ceil(position)
        return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (position - low)
    return {"n": len(values), "median_ft": q(.5), "p90_ft": q(.9), "p99_ft": q(.99), "max_ft": max(values)}


def project_feet(image_to_court: np.ndarray, feet_px: list[tuple[float, float]]) -> list[dict[str, float | bool]]:
    """Project detector box-bottom centres through one image-to-court homography."""
    if not feet_px:
        return []
    projected = cv2.perspectiveTransform(np.float32(feet_px).reshape(1, -1, 2), image_to_court)[0]
    rows: list[dict[str, float | bool]] = []
    for (foot_x, foot_y), (court_x, court_y) in zip(feet_px, projected):
        finite = bool(np.isfinite(court_x) and np.isfinite(court_y))
        distance = outside_distance_ft(float(court_x), float(court_y)) if finite else math.inf
        rows.append({"foot_x_px": float(foot_x), "foot_y_px": float(foot_y), "court_x_ft": float(court_x), "court_y_ft": float(court_y), "finite": finite, "inside_94x50ft_court": bool(finite and distance == 0.0), "outside_distance_ft": float(distance)})
    return rows


def _detect(detector: Any, image: np.ndarray) -> list[tuple[float, float]]:
    results = detector.model(image, classes=[0], conf=.3, verbose=False, imgsz=detector._infer_imgsz, half=detector._use_half, device=detector._device)
    boxes = results[0].boxes.xyxy.cpu().numpy() if results[0].boxes is not None else []
    height, width = image.shape[:2]
    return [(float(np.clip((x1 + x2) / 2, 0, width - 1)), float(np.clip(y2, 0, height - 1))) for x1, _y1, x2, y2 in boxes]


def summarize(records: list[dict[str, Any]], bin_width: int = 200) -> dict[str, Any]:
    """Apply G230 all-player-row denominator and outside-distance vocabulary by distance bin."""
    bins: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        bins.setdefault((int(record["distance_frames"]) // bin_width) * bin_width, []).extend(record["projected_player_feet"])
    output = []
    for start, rows in sorted(bins.items()):
        finite = [row for row in rows if row["finite"]]
        inside = sum(bool(row["inside_94x50ft_court"]) for row in finite)
        outside = [float(row["outside_distance_ft"]) for row in finite if float(row["outside_distance_ft"]) > 0]
        output.append({"distance_bin_frames": [start, start + bin_width - 1], "detected_player_boxes": len(rows), "finite_projected_player_feet": len(finite), "inside_94x50ft_court_rows": inside, "in_court_fraction_of_finite_projected_rows": inside / len(finite) if finite else None, "outside_distance_ft_positive_rows_only": _distribution(outside)})
    return {"denominator": "all direct-detector player boxes with finite projections; positive outside distances are retained", "distance_bins": output}


def _render(path: Path, image: np.ndarray, homography: np.ndarray, rows: list[dict[str, float | bool]]) -> None:
    corners = cv2.perspectiveTransform(court_points_for_sport("wnba").reshape(1, -1, 2), np.linalg.inv(homography))[0]
    rendered = render_overlay(image, homography, "wnba", corners)
    for row in rows:
        color = (0, 255, 0) if row["inside_94x50ft_court"] else (0, 0, 255)
        cv2.circle(rendered, (round(float(row["foot_x_px"])), round(float(row["foot_y_px"]))), 7, color, -1, cv2.LINE_AA)
    if not cv2.imwrite(str(path), rendered):
        raise OSError(path)


def measure(video_path: Path, output_dir: Path, frame_count: int = DEFAULT_FRAME_COUNT) -> dict[str, Any]:
    """Use G222 direct-to-seed motion plus FeetDetector's direct YOLO call."""
    from src.tracking.player_detection import FeetDetector
    output_dir.mkdir(parents=True, exist_ok=True)
    renders = output_dir / "renders"; renders.mkdir(exist_ok=True)
    capture = cv2.VideoCapture(str(video_path)); capture.set(cv2.CAP_PROP_POS_FRAMES, SEED_FRAME)
    ok, seed_image = capture.read()
    if not ok: raise RuntimeError(f"could not decode seed frame {SEED_FRAME}")
    court = court_points_for_sport("wnba"); seed_h = solve_homography(SEED_IMAGE_POINTS, court)
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12); seed_features = _features(cv2.cvtColor(seed_image, cv2.COLOR_BGR2GRAY), orb)
    detector, records = FeetDetector([]), []
    for distance in range(frame_count + 1):
        image = seed_image if distance == 0 else _read_stride(capture, 1)
        if image is None: break
        h, diagnostic, eligible = seed_h, None, True
        if distance:
            seed_to_frame, diag = estimate_motion(seed_features, _features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb))
            diagnostic = {"matches": diag.matches, "inliers": diag.inliers, "inlier_ratio": diag.inlier_ratio, "rms_reprojection_px": diag.rms_reprojection_px}
            eligible = seed_to_frame is not None
            if eligible: h = compose_image_to_court(seed_h, seed_to_frame)
        projected = project_feet(h, _detect(detector, image)) if eligible else []
        record = {"distance_frames": distance, "source_frame": SEED_FRAME + distance, "direct_seed_eligible": eligible, "direct_seed": diagnostic, "detected_player_boxes": len(projected), "projected_player_feet": projected}
        records.append(record)
        if distance in DEFAULT_RENDER_DISTANCES and eligible: _render(renders / f"render_distance_{distance:04d}.jpg", image, h, projected)
    capture.release()
    result = {"seed_frame": SEED_FRAME, "seed_image_points_px": SEED_IMAGE_POINTS.astype(float).tolist(), "seed_court_points_ft": court.astype(float).tolist(), "seed_homography_image_to_court": seed_h.astype(float).tolist(), "frame_count_requested": frame_count, "frames_decoded": len(records), "direct_seed_eligible_frames": sum(bool(row["direct_seed_eligible"]) for row in records), "records": records, "physical_plausibility": summarize(records)}
    (output_dir / "measurement.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--video", type=Path, required=True); parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT)
    args = parser.parse_args()
    result = measure(args.video, args.output_dir, args.frame_count)
    print(f"DECODED_FRAMES={result['frames_decoded']}"); print(f"DIRECT_SEED_ELIGIBLE={result['direct_seed_eligible_frames']}")


if __name__ == "__main__": main()
