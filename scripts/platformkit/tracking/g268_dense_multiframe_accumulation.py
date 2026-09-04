"""G268 dense same-shot, joint line-support control measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from scripts.platformkit.tracking.g215_temporal_homography_propagation import _features, estimate_motion
from scripts.platformkit.tracking.g253_line_conic_calibration import projected_discrepancy_px, render_court


SEED_FRAME = 19599
FRAME_STEP = 5
FRAME_OFFSETS = tuple(range(-100, 101, FRAME_STEP))
PUBLISHED = np.array(((0.050071754999888064, 0.01225404716365722, 2.3351407383547964),
                      (-0.0047586809476217904, 0.1153980129798286, -44.493666860263815),
                      (3.054485397744623e-05, 0.0011147252900901028, 1.0)))
INITIAL = np.array(((0.049814191579082755, 0.012106674793965622, 2.382662102314414),
                    (-0.0043500048696123415, 0.11484012855776558, -44.46748977912508),
                    (3.254917273333284e-05, 0.0010985169929204593, 1.0)))
LINES = (("near_baseline", ((0.0, 0.0), (50.0, 0.0))),
         ("left_lane_boundary", ((17.0, 0.0), (17.0, 19.0))),
         ("right_lane_boundary", ((33.0, 0.0), (33.0, 19.0))),
         ("near_free_throw_line", ((17.0, 19.0), (33.0, 19.0))))


def project(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Project two-dimensional points through a homography."""
    return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(1, -1, 2), matrix)[0]


def line(endpoints: np.ndarray) -> np.ndarray:
    """Return a unit-normal homogeneous line."""
    result = np.cross(np.r_[endpoints[0], 1.0], np.r_[endpoints[1], 1.0])
    return result / np.hypot(result[0], result[1])


def frame_images(video: Path) -> dict[int, np.ndarray]:
    """Stream the fixed dense span once and retain only selected images in memory."""
    wanted = {SEED_FRAME + offset for offset in FRAME_OFFSETS}
    capture, images = cv2.VideoCapture(str(video)), {}
    capture.set(cv2.CAP_PROP_POS_FRAMES, min(wanted))
    for frame in range(min(wanted), max(wanted) + 1):
        ok, image = capture.read()
        if not ok:
            raise RuntimeError("stream decode failed at frame %d" % frame)
        if frame in wanted:
            images[frame] = image
    capture.release()
    if len(images) != len(wanted):
        raise RuntimeError("selected-frame count mismatch")
    return images


def motions(images: dict[int, np.ndarray]) -> dict[int, tuple[np.ndarray, dict[str, object]]]:
    """Estimate all direct seed transports with G222's unchanged matcher."""
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
    seed_features = _features(cv2.cvtColor(images[SEED_FRAME], cv2.COLOR_BGR2GRAY), orb)
    result = {SEED_FRAME: (np.eye(3), {"matches": None, "inliers": None, "rms_reprojection_px": None})}
    for frame, image in images.items():
        if frame == SEED_FRAME:
            continue
        matrix, diagnostic = estimate_motion(seed_features, _features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb))
        if matrix is None:
            raise RuntimeError("G222 matcher returned no map at frame %d" % frame)
        result[frame] = (matrix, asdict(diagnostic))
    return result


def marking_support(image: np.ndarray, expected: np.ndarray) -> np.ndarray:
    """Extract fixed-rule bright, low-saturation marking support near one expected line."""
    expected_line = line(expected)
    height, width = image.shape[:2]
    xx, yy = np.meshgrid(np.arange(width), np.arange(height))
    distance = np.abs(expected_line[0] * xx + expected_line[1] * yy + expected_line[2])
    direction = expected[1] - expected[0]
    length = float(np.linalg.norm(direction))
    unit = direction / length
    longitudinal = (xx - expected[0, 0]) * unit[0] + (yy - expected[0, 1]) * unit[1]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = ((distance <= 12.0) & (longitudinal >= -0.1 * length) & (longitudinal <= 1.1 * length) &
            (hsv[:, :, 2] >= 180) & (hsv[:, :, 1] <= 80))
    points = np.column_stack((xx[mask], yy[mask])).astype(float)
    if len(points) < 12:
        raise RuntimeError("insufficient fixed-rule support")
    fitted = cv2.fitLine(points.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
    normal = np.array((-fitted[1], fitted[0]))
    residual = np.abs((points - fitted[2:]) @ normal)
    return points[residual <= 3.0]


def observations(images: dict[int, np.ndarray], maps: dict[int, tuple[np.ndarray, dict[str, object]]]) -> list[dict[str, object]]:
    """Create four newly image-supported line primitives for every selected frame."""
    result = []
    for frame, image in images.items():
        matrix = maps[frame][0]
        current_to_court = INITIAL @ np.linalg.inv(matrix)
        for name, court_endpoints in LINES:
            expected = project(np.asarray(court_endpoints), np.linalg.inv(current_to_court))
            support = marking_support(image, expected)
            result.append({"frame": frame, "primitive": name, "court_endpoints_ft": court_endpoints,
                           "image_support_px": support, "expected_endpoints_px": expected})
    return result


def joint_fit(items: list[dict[str, object]], maps: dict[int, tuple[np.ndarray, dict[str, object]]], initial: np.ndarray = INITIAL) -> tuple[np.ndarray, object]:
    """Jointly minimize all observed image-support distances to named court lines."""
    normals = {name: line(np.asarray(points, float)) for name, points in LINES}

    def residual(parameters: np.ndarray) -> np.ndarray:
        homography = np.r_[parameters, 1.0].reshape(3, 3)
        values = []
        for item in items:
            current = homography @ np.linalg.inv(maps[int(item["frame"])][0])
            court_points = project(np.asarray(item["image_support_px"]), current)
            values.extend(court_points @ normals[str(item["primitive"])][:2] + normals[str(item["primitive"])][2])
        return np.asarray(values)

    result = least_squares(residual, initial.ravel()[:8], method="trf", loss="linear", x_scale="jac",
                           ftol=1e-10, xtol=1e-10, gtol=1e-10, max_nfev=2000)
    fitted = np.r_[result.x, 1.0].reshape(3, 3)
    return fitted / fitted[2, 2], result


def write_contact_sheet(images: dict[int, np.ndarray], output: Path) -> None:
    """Write five evenly spaced context frames for the no-cut visual check."""
    frames = sorted(images)
    chosen = [frames[index] for index in np.linspace(0, len(frames) - 1, 5, dtype=int)]
    tiles = []
    for frame in chosen:
        tile = cv2.resize(images[frame], (480, 270))
        cv2.putText(tile, str(frame), (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(tile, str(frame), (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    sheet = np.vstack((np.hstack(tiles[:3]), np.hstack(tiles[3:] + [np.zeros_like(tiles[0])])) )
    if not cv2.imwrite(str(output), sheet):
        raise OSError(output)


def run(video: Path, output: Path) -> dict[str, object]:
    """Run the one-control dense joint measurement and retain its complete evidence."""
    images, maps = frame_images(video), None
    maps = motions(images)
    items = observations(images, maps)
    fitted, optimizer = joint_fit(items, maps)
    discrepancy = projected_discrepancy_px(fitted, PUBLISHED, "wnba", images[SEED_FRAME].shape[:2])
    output.mkdir(parents=True, exist_ok=True)
    write_contact_sheet(images, output / "same_shot_context.jpg")
    if not cv2.imwrite(str(output / "joint_fit_seed_render.jpg"), render_court(images[SEED_FRAME], fitted, "wnba", (0, 255, 255))):
        raise OSError("joint seed render")
    diagnostics = [row[1] for frame, row in maps.items() if frame != SEED_FRAME]
    report = {"seed_frame": SEED_FRAME, "frame_span": [min(images), max(images)], "frame_step": FRAME_STEP,
              "frame_count": len(images), "per_frame_primitives": 4, "line_constraints": len(items),
              "endpoint_count": 2 * len(items), "g222_matcher": "ORB nfeatures=2000 fastThreshold=12; BF/Hamming; 0.75 ratio; RANSAC 3 px",
              "transports": {str(frame): diagnostic for frame, (_map, diagnostic) in maps.items()},
              "transport_quality": {"matches_min": min(int(item["matches"]) for item in diagnostics),
                                    "inliers_min": min(int(item["inliers"]) for item in diagnostics),
                                    "rms_max_px": max(float(item["rms_reprojection_px"]) for item in diagnostics)},
              "objective": {"name": "sum squared image-support to mapped named-court-line distances", "optimizer": "scipy.optimize.least_squares trf linear",
                            "convergence": {"success": bool(optimizer.success), "status": int(optimizer.status), "message": str(optimizer.message),
                                            "nfev": int(optimizer.nfev), "cost": float(optimizer.cost), "optimality": float(optimizer.optimality),
                                            "ftol_xtol_gtol": 1e-10}}, "homography_image_to_court": fitted.tolist(),
              "published_homography_image_to_court": PUBLISHED.tolist(), "projected_court_discrepancy_px": discrepancy,
              "primitives": [{**item, "image_support_px": np.asarray(item["image_support_px"]).round(3).tolist(),
                               "expected_endpoints_px": np.asarray(item["expected_endpoints_px"]).round(3).tolist(),
                               "support_count": int(len(item["image_support_px"]))} for item in items]}
    (output / "g268_measurement.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.video, args.output)
    metric = result["projected_court_discrepancy_px"]
    print("G268_SHARED=" + str(int(metric["shared_in_frame_sample_points"])))
    print("G268_MAX_PX=" + format(float(metric["shared_in_frame_max_px"]), ".6f"))


if __name__ == "__main__":
    main()
