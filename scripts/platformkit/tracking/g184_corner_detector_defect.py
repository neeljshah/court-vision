"""Read-only, per-frame observer for the tennis corner-detector gates."""
from __future__ import annotations

import argparse
import base64
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_lines import (
    CROSS_RATIO_TOLERANCE,
    TOPHAT_CONTRASTS,
    CourtLines,
    _ACROSS_TARGET,
    _ALONG_TARGETS,
    _ALONG_TEMPLATES,
    _match,
    _row_on,
    court_line_segments,
    detect_court,
    select_court_lines,
    solve_corners,
    split_orientation,
)


def evenly_spaced_positions(length: int, count: int) -> list[int]:
    """Return inclusive, integer floor-linspace positions without a head slice."""
    if count < 1 or length < count:
        raise ValueError("need 1 <= count <= length")
    positions = np.linspace(0, length - 1, num=count, dtype=int).tolist()
    if len(set(positions)) != count:
        raise RuntimeError("even positions are not unique")
    return positions


def g182_loss_sample(report_path: Path, count: int = 200) -> tuple[list[int], list[int]]:
    """Return A3 positions and source frames from G182's named loss population."""
    report = json.loads(report_path.read_text(encoding="ascii"))
    losses = [record["frame"] for record in report["frame_records"] if not record["enough_corners"]]
    if len(losses) != 26113 or losses != sorted(set(losses)):
        raise RuntimeError("G182 eligible corner-loss population did not reproduce")
    positions = evenly_spaced_positions(len(losses), count)
    return positions, [losses[position] for position in positions]


def _match_measurement(positions: list[float], size: int, target: tuple[float, ...],
                       windows: Optional[list[tuple[float, float]]] = None) -> dict[str, Any]:
    """Measure the production cross-ratio predicate without changing its choice."""
    details: dict[str, Any] = {
        "position_count": len(positions), "required_count": size,
        "max_position_count": 14, "tolerance": CROSS_RATIO_TOLERANCE,
        "window_eligible_combinations": 0, "minimum_max_abs_deviation": None,
    }
    if len(positions) < size or len(positions) > 14:
        return details
    best: float | None = None
    for combo in combinations(range(len(positions)), size):
        if windows is not None and any(not low <= positions[index] <= high
                                       for index, (low, high) in zip(combo, windows)):
            continue
        details["window_eligible_combinations"] += 1
        points = tuple(positions[index] for index in combo)
        if len(points) == 4:
            got = ((points[0] - points[2]) * (points[1] - points[3]) /
                   ((points[2] - points[1]) * (points[3] - points[0])))
            deviations = [abs(got - target[0])]
        else:
            first = ((points[0] - points[2]) * (points[1] - points[4]) /
                     ((points[2] - points[1]) * (points[4] - points[0])))
            second = ((points[1] - points[3]) * (points[2] - points[4]) /
                      ((points[3] - points[2]) * (points[4] - points[1])))
            deviations = [abs(first - target[0]), abs(second - target[1])]
        maximum = max(deviations)
        best = maximum if best is None else min(best, maximum)
    details["minimum_max_abs_deviation"] = best
    return details


def _solve_measurement(court: CourtLines, shape: tuple[int, int]) -> tuple[str, dict[str, Any]]:
    """Capture only the values consulted by the unchanged corner solver."""
    height, width = shape
    near_left = TennisAdapter._intersection(court.near, court.left)
    near_right = TennisAdapter._intersection(court.near, court.right)
    far_left = TennisAdapter._intersection(court.far, court.left)
    service_t = TennisAdapter._intersection(court.near_service, court.centre)
    values: dict[str, Any] = {"depth_order": {
        "near_left_y": None if near_left is None else float(near_left[1]),
        "near_right_present": near_right is not None,
        "far_left_y": None if far_left is None else float(far_left[1]),
        "service_y": None if service_t is None else float(service_t[1]),
        "predicate": "far_left_y < service_y < near_left_y",
    }}
    if near_left is None or near_right is None or far_left is None or service_t is None:
        return "depth_order", values
    if not far_left[1] < service_t[1] < near_left[1]:
        return "depth_order", values
    anchors = np.float32((near_left, near_right, far_left, service_t))
    to_image, _ = cv2.findHomography(np.float32(((0., 0.), (0., 36.), (78., 0.), (18., 18.))), anchors)
    values["homography"] = {"is_none": to_image is None}
    if to_image is None:
        return "homography", values
    far_right = cv2.perspectiveTransform(np.float32([[(78., 36.)]]), to_image)[0, 0]
    result = np.asarray((near_left, near_right, far_left, far_right), dtype=np.float32)
    depth = float(result[0][1] - result[2][1])
    far_y_delta = float(abs(result[2][1] - result[3][1]))
    values["skew"] = {"depth": depth, "depth_threshold": 0.0,
                      "far_y_delta": far_y_delta, "far_y_limit": 0.25 * depth}
    if depth <= 0.0 or far_y_delta > 0.25 * depth:
        return "skew", values
    values["image_bounds"] = {"min_x": float(result[:, 0].min()), "max_x": float(result[:, 0].max()),
                              "min_y": float(result[:, 1].min()), "max_y": float(result[:, 1].max()),
                              "low_limit": -5.0, "high_x_limit": float(width + 5),
                              "high_y_limit": float(height + 5)}
    if np.any(result[:, 0] < -5) or np.any(result[:, 0] > width + 5) or np.any(result[:, 1] < -5) or np.any(result[:, 1] > height + 5):
        return "image_bounds", values
    observed = TennisAdapter._intersection(court.far, court.right)
    distance = None if observed is None else float(np.linalg.norm(observed - far_right))
    values["far_right_consistency"] = {"distance": distance, "limit": 0.02 * width}
    return ("far_right_consistency" if observed is None or distance > 0.02 * width else "accepted"), values


def inspect_frame(frame: np.ndarray) -> dict[str, Any]:
    """Observe both contrast attempts and assert parity with production output."""
    shape = frame.shape[:2]
    attempts: list[dict[str, Any]] = []
    for contrast in TOPHAT_CONTRASTS:
        segments = court_line_segments(frame, contrast=contrast)
        attempt: dict[str, Any] = {"contrast": contrast, "segment_count": len(segments), "gate": "no_hough_lines"}
        if not segments:
            attempts.append(attempt)
            continue
        horizontal, vertical = split_orientation(segments)
        attempt["oriented_lines"] = {"horizontal": len(horizontal), "vertical": len(vertical),
                                      "minimum_each": 2}
        if len(horizontal) < 2 or len(vertical) < 2:
            attempt["gate"] = "insufficient_oriented_lines"
            attempts.append(attempt)
            continue
        horizontal_clusters = TennisAdapter._cluster_lines(horizontal, True, shape)
        vertical_clusters = TennisAdapter._cluster_lines(vertical, False, shape)
        attempt["cluster_count"] = {"horizontal": len(horizontal_clusters), "vertical": len(vertical_clusters),
                                    "minimum_horizontal": 4, "minimum_vertical": 5}
        if len(horizontal_clusters) < 4 or len(vertical_clusters) < 5:
            attempt["gate"] = "vertical_cluster_count"
            attempts.append(attempt)
            continue
        fitted_vertical = [TennisAdapter._fit_line(cluster) for cluster in vertical_clusters]
        across = [TennisAdapter._line_position(line, False, shape) for line in fitted_vertical]
        chosen = _match(across, 5, _ACROSS_TARGET)
        attempt["cross_ratio"] = _match_measurement(across, 5, _ACROSS_TARGET)
        if chosen is None:
            attempt["gate"] = "cross_ratio"
            attempts.append(attempt)
            continue
        five = [vertical_clusters[index] for index in chosen]
        left, centre, right = fitted_vertical[chosen[0]], fitted_vertical[chosen[2]], fitted_vertical[chosen[4]]
        rows = [line[1] for cluster in five for line in cluster] + [line[3] for cluster in five for line in cluster]
        top, bottom = min(rows), max(rows)
        margin = 0.1 * (bottom - top)
        candidates = []
        for cluster in horizontal_clusters:
            fitted = TennisAdapter._fit_line(cluster)
            row = _row_on(fitted, centre)
            if row is not None and top - margin <= row <= bottom + margin:
                candidates.append((row, fitted))
        candidates.sort(key=lambda item: item[0])
        positions = [row for row, _ in candidates]
        centre_rows = [line[1] for line in five[2]] + [line[3] for line in five[2]]
        centre_top, centre_bottom = min(centre_rows), max(centre_rows)
        span, centre_span = bottom - top, centre_bottom - centre_top
        windows = {"far": (top - .1 * span, top + .1 * span), "near": (bottom - .1 * span, bottom + .1 * span),
                   "far_service": (top - .1 * span, centre_top + .06 * centre_span),
                   "near_service": (centre_bottom - .1 * centre_span, bottom + .1 * span), "net": (top, bottom)}
        role_measures = {}
        selected: tuple[tuple[str, ...], tuple[int, ...]] | None = None
        for roles in _ALONG_TEMPLATES:
            picked = _match(positions, len(roles), _ALONG_TARGETS[roles], [windows[role] for role in roles])
            role_measures["|".join(roles)] = _match_measurement(positions, len(roles), _ALONG_TARGETS[roles], [windows[role] for role in roles])
            if picked is not None and selected is None:
                selected = (roles, picked)
        attempt["horizontal_roles"] = {"candidate_position_count": len(positions), "templates": role_measures}
        if selected is None:
            attempt["gate"] = "horizontal_roles"
            attempts.append(attempt)
            continue
        roles, picked = selected
        by_role = {role: candidates[index][1] for role, index in zip(roles, picked)}
        court = CourtLines(left, right, centre, by_role["far"], by_role["near_service"], by_role["near"], by_role.get("far_service"), tuple(five))
        gate, values = _solve_measurement(court, shape)
        attempt["solve"] = values
        attempt["gate"] = gate
        attempts.append(attempt)
        if gate == "accepted":
            break
    _, corners, production_gate = detect_court(frame)
    if production_gate != attempts[-1]["gate"] or (corners is not None) != (production_gate == "accepted"):
        raise RuntimeError("observer/production parity failure")
    return {"shape": [int(shape[0]), int(shape[1])], "attempts": attempts,
            "first_attempt_gate": attempts[0]["gate"], "terminal_gate": production_gate,
            "accepted": corners is not None}


def measure_video(video: Path, frames: list[int]) -> list[dict[str, Any]]:
    """Sequentially decode only the requested source indices and observe each once."""
    wanted = set(frames)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    records: list[dict[str, Any]] = []
    index = 0
    try:
        while wanted:
            ok, frame = capture.read()
            if not ok:
                break
            if index in wanted:
                record = inspect_frame(frame)
                record["frame"] = index
                records.append(record)
                wanted.remove(index)
            index += 1
    finally:
        capture.release()
    if wanted:
        raise RuntimeError("could not decode frames: %s" % sorted(wanted))
    return sorted(records, key=lambda record: record["frame"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--frames", required=True, help="comma-separated source-frame indices")
    parser.add_argument("--output", type=Path, help="optional local JSON artifact path")
    args = parser.parse_args()
    frames = [int(value) for value in args.frames.split(",") if value]
    if frames != sorted(set(frames)):
        raise ValueError("frames must be sorted and unique")
    payload = json.dumps({"frame_records": measure_video(args.video, frames)}, sort_keys=True, indent=2) + "\n"
    if args.output is None:
        print(payload, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
