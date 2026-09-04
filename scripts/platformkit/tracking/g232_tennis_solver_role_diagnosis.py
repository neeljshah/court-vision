"""Observe unchanged tennis court-line solver evidence on individual frame files."""
from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_lines import (
    CROSS_RATIO_TOLERANCE,
    TOPHAT_CONTRASTS,
    _ACROSS_TARGET,
    _ALONG_TARGETS,
    _ALONG_TEMPLATES,
    _invariants,
    _match,
    _row_on,
    court_line_segments,
    detect_court,
    select_court_lines,
    solve_corners,
    split_orientation,
)

_VERTICAL_ROLES = ("left_doubles", "left_singles", "centre_service", "right_singles", "right_doubles")
_COLORS = {
    "left_doubles": (0, 255, 0), "right_doubles": (0, 255, 0),
    "left_singles": (0, 180, 180), "right_singles": (0, 180, 180),
    "centre_service": (255, 0, 255), "far": (255, 255, 0),
    "far_service": (255, 128, 0), "near_service": (255, 128, 0), "near": (0, 0, 255),
}


def _line(value: np.ndarray) -> list[float]:
    return [round(float(item), 4) for item in value]


def _point(value: np.ndarray | None) -> list[float] | None:
    return None if value is None else [round(float(item), 4) for item in value]


def _match_evidence(positions: list[float], roles: tuple[str, ...], windows: list[tuple[float, float]]) -> dict[str, Any]:
    target = _ALONG_TARGETS[roles]
    candidates: list[dict[str, Any]] = []
    for combo in combinations(range(len(positions)), len(roles)):
        if any(not low <= positions[index] <= high for index, (low, high) in zip(combo, windows)):
            continue
        invariants = _invariants(tuple(positions[index] for index in combo))
        deviations = [abs(got - want) for got, want in zip(invariants, target)]
        candidates.append({"indices": list(combo), "invariants": list(invariants),
                           "deviations": deviations, "sum_deviation": sum(deviations),
                           "within_tolerance": max(deviations) <= CROSS_RATIO_TOLERANCE})
    accepted = [item for item in candidates if item["within_tolerance"]]
    best = min(accepted, key=lambda item: item["sum_deviation"]) if accepted else None
    return {"roles": list(roles), "target_invariants": list(target), "best": best,
            "candidate_count": len(candidates)}


def _stage(frame: np.ndarray, contrast: int) -> dict[str, Any]:
    shape = frame.shape[:2]
    segments = court_line_segments(frame, contrast=contrast)
    horizontal, vertical = split_orientation(segments)
    trace: dict[str, Any] = {
        "contrast": contrast, "segments": [_line(segment) for segment in segments],
        "horizontal_segment_count": len(horizontal), "vertical_segment_count": len(vertical),
    }
    if len(horizontal) < 2 or len(vertical) < 2:
        trace["gate"] = "insufficient_oriented_lines"
        return trace
    h_clusters = TennisAdapter._cluster_lines(horizontal, True, shape)
    v_clusters = TennisAdapter._cluster_lines(vertical, False, shape)
    trace["horizontal_clusters"] = [[_line(line) for line in cluster] for cluster in h_clusters]
    trace["vertical_clusters"] = [[_line(line) for line in cluster] for cluster in v_clusters]
    if len(h_clusters) < 4 or len(v_clusters) < 5:
        trace["gate"] = "vertical_cluster_count"
        return trace
    fitted_vertical = [TennisAdapter._fit_line(cluster) for cluster in v_clusters]
    across = [TennisAdapter._line_position(line, False, shape) for line in fitted_vertical]
    chosen = _match(across, 5, _ACROSS_TARGET)
    trace["vertical_positions"] = across
    trace["vertical_target_invariants"] = list(_ACROSS_TARGET)
    trace["vertical_chosen_indices"] = None if chosen is None else list(chosen)
    if chosen is None:
        trace["gate"] = "cross_ratio"
        return trace
    five = [v_clusters[index] for index in chosen]
    centre = fitted_vertical[chosen[2]]
    rows = [line[1] for cluster in five for line in cluster] + [line[3] for cluster in five for line in cluster]
    top, bottom = min(rows), max(rows)
    margin = 0.1 * (bottom - top)
    candidates: list[tuple[float, np.ndarray]] = []
    for cluster in h_clusters:
        fitted = TennisAdapter._fit_line(cluster)
        row = _row_on(fitted, centre)
        if row is not None and top - margin <= row <= bottom + margin:
            candidates.append((row, fitted))
    candidates.sort(key=lambda item: item[0])
    positions = [row for row, _ in candidates]
    centre_rows = [line[1] for line in five[2]] + [line[3] for line in five[2]]
    centre_top, centre_bottom = min(centre_rows), max(centre_rows)
    span, centre_span = bottom - top, centre_bottom - centre_top
    window_map = {
        "far": (top - 0.1 * span, top + 0.1 * span), "near": (bottom - 0.1 * span, bottom + 0.1 * span),
        "far_service": (top - 0.1 * span, centre_top + 0.06 * centre_span),
        "near_service": (centre_bottom - 0.1 * centre_span, bottom + 0.1 * span), "net": (top, bottom),
    }
    trace["horizontal_candidate_rows"] = positions
    trace["horizontal_role_evidence"] = [_match_evidence(positions, roles, [window_map[role] for role in roles])
                                         for roles in _ALONG_TEMPLATES]
    court, gate = select_court_lines(segments, shape)
    trace["gate"] = gate
    trace["assigned_roles"] = _roles(court, chosen, candidates, fitted_vertical)
    if court is not None:
        corners, corner_gate = solve_corners(court, shape)
        trace["solve_gate"] = corner_gate
        trace["corners_image"] = None if corners is None else [_point(point) for point in corners]
    return trace


def _roles(court: Any, chosen: tuple[int, ...] | None, candidates: list[tuple[float, np.ndarray]],
           fitted_vertical: list[np.ndarray]) -> dict[str, Any]:
    if court is None or chosen is None:
        return {}
    result: dict[str, Any] = {
        role: {"cluster_index": int(index), "line": _line(fitted_vertical[index])}
        for role, index in zip(_VERTICAL_ROLES, chosen)
    }
    for role in ("far", "far_service", "near_service", "near"):
        line = getattr(court, role)
        if line is None:
            continue
        cluster_index = next((index for index, (_, fitted) in enumerate(candidates)
                              if np.allclose(fitted, line)), None)
        result[role] = {"horizontal_candidate_index": cluster_index, "line": _line(line)}
    return result


def _court_extent(corners: np.ndarray | None) -> dict[str, Any] | None:
    if corners is None:
        return None
    homography = TennisAdapter.homography_from_corners(corners)
    recovered = cv2.perspectiveTransform(corners.reshape(1, -1, 2), homography)[0]
    return {"image_to_feet_homography": [[round(float(value), 10) for value in row] for row in homography],
            "corner_feet": [_point(point) for point in recovered],
            "extent_ft": {"length": round(float(np.ptp(recovered[:, 0])), 6),
                          "width": round(float(np.ptp(recovered[:, 1])), 6)},
            "note": "The four corner values are algebraically pinned to 78 by 36 by homography_from_corners."}


def analyze_frame(frame: np.ndarray) -> dict[str, Any]:
    """Run the unchanged solver and attach observational role evidence around it."""
    court, corners, gate = detect_court(frame)
    stages = [_stage(frame, contrast) for contrast in TOPHAT_CONTRASTS]
    accepted_stage = next((stage for stage in stages if stage.get("solve_gate") == "ok"), None)
    return {"shape": [int(frame.shape[1]), int(frame.shape[0])], "solver_gate": gate,
            "accepted": court is not None and corners is not None,
            "solver_corners_image": None if corners is None else [_point(point) for point in corners],
            "extent": _court_extent(corners), "stages": stages,
            "accepted_stage_contrast": None if accepted_stage is None else accepted_stage["contrast"]}


def render(frame: np.ndarray, result: dict[str, Any]) -> np.ndarray:
    """Draw selected line roles and the returned court model on a copy of ``frame``."""
    output = frame.copy()
    stage = next((item for item in result["stages"] if item.get("solve_gate") == "ok"), None)
    if stage:
        for role, payload in stage["assigned_roles"].items():
            line = np.int32(np.round(payload["line"])).reshape(2, 2)
            cv2.line(output, tuple(line[0]), tuple(line[1]), _COLORS.get(role, (255, 255, 255)), 3)
            cv2.putText(output, role, tuple(line[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        _COLORS.get(role, (255, 255, 255)), 2, cv2.LINE_AA)
    corners = result["solver_corners_image"]
    if corners:
        points = np.int32(np.round(np.asarray(corners)))
        cv2.polylines(output, [points[[0, 1, 3, 2]]], True, (0, 255, 255), 3)
    cv2.putText(output, "solver_gate=" + result["solver_gate"], (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(output, "solver_gate=" + result["solver_gate"], (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", action="append", required=True, help="label=single-frame image path")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render-dir", type=Path, required=True)
    args = parser.parse_args()
    reports: dict[str, Any] = {}
    args.render_dir.mkdir(parents=True, exist_ok=True)
    for item in args.frame:
        label, raw_path = item.split("=", 1)
        frame = cv2.imread(raw_path)
        if frame is None:
            raise FileNotFoundError(raw_path)
        report = analyze_frame(frame)
        reports[label] = report
        preview = render(frame, report)
        if preview.shape[1] > 1280:
            preview = cv2.resize(preview, (1280, int(preview.shape[0] * 1280 / preview.shape[1])))
        if not cv2.imwrite(str(args.render_dir / (label + ".jpg")), preview,
                           [cv2.IMWRITE_JPEG_QUALITY, 90]):
            raise RuntimeError("could not write render for " + label)
    args.output.write_text(json.dumps(reports, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
