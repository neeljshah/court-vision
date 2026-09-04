"""Measure court-space motion plausibility through G233d's published WNBA map."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.adapter import BasketballAdapter
from scripts.platformkit.tracking import g196_homography_from_labelled_corners as g196
from scripts.platformkit.tracking import g215_temporal_homography_propagation as g215


SEED_FRAME = 19599
MAX_DISTANCE = 3800
FPS = 30.0
COURT_WIDTH_FT, COURT_LENGTH_FT = 50.0, 94.0
IMAGE_POINTS = np.float32(((350.0, 400.0), (835.0, 420.0), (390.0, 696.0), (990.0, 730.0)))
PUBLISHED_H = np.array(((0.050071754999888064, 0.01225404716365722, 2.3351407383547964),
                        (-0.0047586809476217904, 0.1153980129798286, -44.493666860263815),
                        (3.054485397744623e-05, 0.0011147252900901028, 1.0)), dtype=float)
SPEED_REFERENCES_FTPS = (25.0, 30.0, 33.0, 40.0)
LARGE_PIXEL_JUMP_PX = 100.0


def _q(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values); position = (len(ordered) - 1) * percentile
    low, high = math.floor(position), math.ceil(position)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _distribution(values: list[float], low_quantiles: bool = False) -> dict[str, float | int | None]:
    output: dict[str, float | int | None] = {"n": len(values), "median": _q(values, .5), "p90": _q(values, .9),
                                               "p99": _q(values, .99), "max": max(values) if values else None}
    if low_quantiles:
        output.update({"p10": _q(values, .1), "p01": _q(values, .01), "min": min(values) if values else None})
    return output


def _project(points: np.ndarray, homography: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(points.astype(np.float32).reshape(1, -1, 2), homography.astype(np.float64))[0]


def local_scale(homography: np.ndarray, court_point: tuple[float, float]) -> dict[str, Any]:
    """Return the local inverse-projective principal scales in feet per image pixel."""
    inverse = np.linalg.inv(homography)
    image_point = _project(np.array([court_point]), inverse)[0]
    origin = _project(np.array([image_point]), homography)[0]
    x_step = _project(np.array([image_point + (1.0, 0.0)]), homography)[0] - origin
    y_step = _project(np.array([image_point + (0.0, 1.0)]), homography)[0] - origin
    singular = np.linalg.svd(np.column_stack((x_step, y_step)), compute_uv=False)
    return {"court_point_ft": [float(value) for value in court_point], "image_point_px": [float(value) for value in image_point],
            "principal_scale_ft_per_px_min": float(singular[-1]), "principal_scale_ft_per_px_max": float(singular[0]),
            "area_equivalent_ft_per_px": float(math.sqrt(abs(np.linalg.det(np.column_stack((x_step, y_step)))))),
            "error_5px_ft_range": [float(5 * singular[-1]), float(5 * singular[0])],
            "error_19px_ft_range": [float(19 * singular[-1]), float(19 * singular[0])]}


def _inside(x: float, y: float) -> bool:
    return 0.0 <= x <= COURT_WIDTH_FT and 0.0 <= y <= COURT_LENGTH_FT


def analyze(frame_records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize retained finite observations and same-ID motion steps without exclusions."""
    tracks: dict[int, list[dict[str, Any]]] = defaultdict(list)
    finite_rows, inter_distances = [], []
    for frame in frame_records:
        rows = [row for row in frame["detections"] if row["finite"]]
        finite_rows.extend(rows)
        for index, left in enumerate(rows):
            for right in rows[index + 1:]:
                inter_distances.append(math.hypot(left["court_x_ft"] - right["court_x_ft"], left["court_y_ft"] - right["court_y_ft"]))
        for row in rows:
            tracks[int(row["track_id"])].append(row)
    speeds, implausible, nonpositive_gaps = [], [], 0
    for track_id, rows in tracks.items():
        rows.sort(key=lambda row: row["source_frame"])
        for prior, current in zip(rows, rows[1:]):
            gap = current["source_frame"] - prior["source_frame"]
            if gap <= 0:
                nonpositive_gaps += 1; continue
            speed = math.hypot(current["court_x_ft"] - prior["court_x_ft"], current["court_y_ft"] - prior["court_y_ft"]) * FPS / gap
            step = {"track_id": track_id, "prior_source_frame": prior["source_frame"], "source_frame": current["source_frame"], "frame_gap": gap,
                    "speed_ft_per_s": speed, "pixel_jump_px": math.hypot(current["foot_x_px"] - prior["foot_x_px"], current["foot_y_px"] - prior["foot_y_px"]),
                    "nearest_previous_id_changed": current["nearest_previous_id_changed"]}
            speeds.append(step)
            if speed > 40.0:
                implausible.append(step)
    values = [step["speed_ft_per_s"] for step in speeds]
    reference = {str(int(limit)): {"count": sum(value > limit for value in values), "fraction": sum(value > limit for value in values) / len(values) if values else None}
                 for limit in SPEED_REFERENCES_FTPS}
    changed = sum(step["nearest_previous_id_changed"] for step in implausible)
    jumps = {str(int(limit)): sum(step["pixel_jump_px"] > limit for step in implausible) for limit in (20.0, 40.0, LARGE_PIXEL_JUMP_PX)}
    return {"denominator": {"all_finite_detector_box_feet": len(finite_rows), "emitted_track_ids": len(tracks), "same_track_consecutive_observation_steps": len(speeds),
                            "nonpositive_frame_gap_steps_excluded": nonpositive_gaps},
            "in_court": {"inside_rows": sum(_inside(row["court_x_ft"], row["court_y_ft"]) for row in finite_rows), "fraction": sum(_inside(row["court_x_ft"], row["court_y_ft"]) for row in finite_rows) / len(finite_rows) if finite_rows else None},
            "speed_ft_per_s": {"distribution": _distribution(values), "above_reference_ft_per_s": reference,
                                "implausible_definition": "strictly greater than 40 ft/s; descriptive error signal, not a production gate",
                                "implausible_steps": len(implausible), "implausible_fraction": len(implausible) / len(speeds) if speeds else None,
                                "implausible_step_records": implausible},
            "attribution": {"nearest_previous_id_changed_among_implausible": changed,
                            "large_pixel_jump_definition": ">100 px between consecutive same-ID bottom-centres; diagnostic only, not a gate",
                            "implausible_with_pixel_jump_counts": jumps,
                            "unattributable": len(implausible) - changed},
            "inter_detection_distance_ft": {"all_same_frame_finite_box_pairs": _distribution(inter_distances, low_quantiles=True),
                                               "strict_near_coincidences_at_or_below_0_01ft": sum(value <= .01 for value in inter_distances),
                                               "sub_1ft_pairs": sum(value < 1.0 for value in inter_distances)}}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def measure(video: Path) -> dict[str, Any]:
    """Stream one detector draw and G233d direct-to-seed maps through the frozen association."""
    from src.tracking.player_detection import FeetDetector
    detector, tracker = FeetDetector([]), BasketballAdapter(detector=lambda _frame: [])
    capture = cv2.VideoCapture(str(video)); capture.set(cv2.CAP_PROP_POS_FRAMES, SEED_FRAME)
    ok, seed = capture.read()
    if not ok:
        raise RuntimeError("could not decode published G233d seed frame")
    orb = cv2.ORB_create(nfeatures=2000, fastThreshold=12)
    seed_features = g215._features(cv2.cvtColor(seed, cv2.COLOR_BGR2GRAY), orb)
    previous: list[dict[str, Any]] = []; frame_records = []
    for distance in range(MAX_DISTANCE + 1):
        image = seed if distance == 0 else g215._read_stride(capture, 1)
        if image is None:
            raise RuntimeError("source ended before the declared pre-cut span")
        homography = PUBLISHED_H
        if distance:
            motion, diagnostics = g215.estimate_motion(seed_features, g215._features(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), orb))
            if motion is None:
                frame_records.append({"source_frame": SEED_FRAME + distance, "distance_frames": distance, "direct_seed_eligible": False, "direct_seed": diagnostics.__dict__, "detections": []}); continue
            homography = g215.compose_image_to_court(PUBLISHED_H, motion)
        result = detector.model(image, classes=[0], conf=.3, verbose=False, imgsz=detector._infer_imgsz, half=detector._use_half, device=detector._device)
        boxes = result[0].boxes.xyxy.cpu().numpy() if result[0].boxes is not None else []
        feet = [(float((box[0] + box[2]) / 2), float(box[3])) for box in boxes]
        ids = tracker._assign_tracks([np.array(((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)) for box in boxes])
        projected = _project(np.array(feet), homography) if feet else []
        rows = []
        for track_id, foot, court in zip(ids, feet, projected):
            nearest = min(previous, key=lambda prior: math.hypot(foot[0] - prior["foot_x_px"], foot[1] - prior["foot_y_px"]), default=None)
            finite = bool(np.isfinite(court).all())
            rows.append({"track_id": track_id, "source_frame": SEED_FRAME + distance, "foot_x_px": foot[0], "foot_y_px": foot[1], "court_x_ft": float(court[0]), "court_y_ft": float(court[1]), "finite": finite,
                         "nearest_previous_track_id": None if nearest is None else nearest["track_id"], "nearest_previous_id_changed": bool(nearest is not None and nearest["track_id"] != track_id)})
        frame_records.append({"source_frame": SEED_FRAME + distance, "distance_frames": distance, "direct_seed_eligible": True, "detections": rows})
        previous = rows
    capture.release()
    root = Path(__file__).resolve().parents[3]
    routes = ("scripts/platformkit/tracking/g267_court_space_physical_plausibility.py", "scripts/platformkit/tracking/g196_homography_from_labelled_corners.py", "scripts/platformkit/tracking/g215_temporal_homography_propagation.py", "src/tracking/player_detection.py", "domains/basketball/tracking/adapter.py")
    scales = {"near_sideline_x0_y19": local_scale(PUBLISHED_H, (0.0, 19.0)), "far_sideline_x50_y19": local_scale(PUBLISHED_H, (50.0, 19.0)), "near_baseline_midpoint": local_scale(PUBLISHED_H, (25.0, 0.0)), "mid_court": local_scale(PUBLISHED_H, (25.0, 47.0))}
    return {"input": {"absolute_path": str(video.resolve()), "bytes": video.stat().st_size, "resolution_px": [1920, 1080], "seed_frame": SEED_FRAME, "source_frame_span_inclusive": [SEED_FRAME, SEED_FRAME + MAX_DISTANCE], "fps": FPS},
            "method": {"published_homography_image_to_court": PUBLISHED_H.tolist(), "pixel_scale": "local singular-value range of image-to-court Jacobian; no global px-to-ft factor", "track_association": "unchanged BasketballAdapter nearest-centre assignment; identity unvalidated"},
            "local_pixel_to_feet": scales, "frame_records": frame_records, "analysis": analyze(frame_records),
            "route_sha256": {route: _hash(root / route) for route in routes}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path); parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(); report = measure(args.video)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    print("G267_FRAMES=" + str(len(report["frame_records"])))
    print("G267_IMPLAUSIBLE_STEPS=" + str(report["analysis"]["speed_ft_per_s"]["implausible_steps"]))


if __name__ == "__main__":
    main()
