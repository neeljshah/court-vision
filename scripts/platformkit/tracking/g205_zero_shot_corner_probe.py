"""Run G205's fixed native-pixel stable-line intersection measurement."""
from __future__ import annotations

import csv
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import CandidateLineGroup, detect_lsd_segments
from scripts.platformkit.g123_low_contrast_lines import enhance_contrast
from scripts.platformkit.g132_additive_candidate_union import union_segments
from scripts.platformkit.g134_grouping_stability import stable_groups


ROOT = Path("docs/evidence/tracking")
TARGETS = ROOT / "g140_corner_targets/corner_pixel_targets.csv"
OUT = ROOT / "g205_zero_shot_corner_probe"
TOLERANCE_PX = 12.0
MIN_LSD_LENGTH_PX = 28.0
GROUP_ANGLE_DEG = 5.0
GROUP_OFFSET_PX = 10.0
MIN_INTERSECTION_ANGLE_DEG = 35.0
SUPPORT_EXTENSION_PX = 45.0
DEDUPLICATE_RADIUS_PX = 2.0
CANDIDATE = "g134_stable_lsd_intersections"
RENDER_INDICES = (0, 4, 8, 12, 16)


def _read_targets() -> dict[str, list[dict[str, str]]]:
    with TARGETS.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 68 or any(row["status"] != "target" for row in rows):
        raise ValueError("G140 target construct changed")
    frames: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        frames.setdefault(row["audit_id"], []).append(row)
    if len(frames) != 17 or any(len(values) != 4 for values in frames.values()):
        raise ValueError("G140 must retain four targets on each of 17 frames")
    return frames


def _source_path(row: dict[str, str]) -> Path:
    return (TARGETS.parent / row["source_decode"]).resolve()


def _group_supports(group: CandidateLineGroup, point: tuple[float, float]) -> bool:
    x0, y0 = group.anchor
    vx, vy = group.direction
    distance = (point[0] - x0) * vx + (point[1] - y0) * vy
    return group.extent[0] - SUPPORT_EXTENSION_PX <= distance <= group.extent[1] + SUPPORT_EXTENSION_PX


def _intersection(first: CandidateLineGroup, second: CandidateLineGroup) -> tuple[float, float] | None:
    alignment = abs(first.direction[0] * second.direction[0] + first.direction[1] * second.direction[1])
    if alignment > float(np.cos(np.deg2rad(MIN_INTERSECTION_ANGLE_DEG))):
        return None
    point = np.cross(first.line, second.line)
    if abs(float(point[2])) < 1e-9:
        return None
    return (float(point[0] / point[2]), float(point[1] / point[2]))


def _deduplicate(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    kept: list[tuple[float, float]] = []
    for point in sorted(points):
        if all(float(np.hypot(point[0] - saved[0], point[1] - saved[1])) > DEDUPLICATE_RADIUS_PX for saved in kept):
            kept.append(point)
    return kept


def propose(image: np.ndarray) -> list[tuple[float, float]]:
    """Return fixed generic corner proposals in this image's native pixels."""
    baseline = detect_lsd_segments(image, MIN_LSD_LENGTH_PX)
    enhanced = detect_lsd_segments(enhance_contrast(image), MIN_LSD_LENGTH_PX)
    groups = stable_groups(baseline, union_segments(baseline, enhanced))
    height, width = image.shape[:2]
    points: list[tuple[float, float]] = []
    for first, second in combinations(groups, 2):
        point = _intersection(first, second)
        if point is None or not (0.0 <= point[0] < width and 0.0 <= point[1] < height):
            continue
        if _group_supports(first, point) and _group_supports(second, point):
            points.append(point)
    return _deduplicate(points)


def _nearest(point: tuple[float, float], proposals: list[tuple[float, float]]) -> float:
    if not proposals:
        return float("inf")
    return min(float(np.hypot(point[0] - item[0], point[1] - item[1])) for item in proposals)


def score_frame(targets: list[dict[str, str]], proposals: list[tuple[float, float]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Score one frame using G141's generic-proposal availability rules."""
    target_rows: list[dict[str, Any]] = []
    for target in targets:
        point = (float(target["x_px"]), float(target["y_px"]))
        distance = _nearest(point, proposals)
        target_rows.append({**target, "nearest_proposal_distance_px": distance, "available": distance <= TOLERANCE_PX})
    proposal_rows: list[dict[str, Any]] = []
    points = [(float(item["x_px"]), float(item["y_px"])) for item in targets]
    for rank, point in enumerate(proposals):
        distance = _nearest(point, points)
        proposal_rows.append({"audit_id": targets[0]["audit_id"], "rank": rank, "x_px": point[0], "y_px": point[1], "nearest_target_distance_px": distance, "on_any_target": distance <= TOLERANCE_PX})
    return target_rows, proposal_rows, all(bool(row["available"]) for row in target_rows)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else ["audit_id", "rank", "x_px", "y_px"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _render(image: np.ndarray, targets: list[dict[str, str]], proposals: list[tuple[float, float]], destination: Path) -> None:
    panel = image.copy()
    for x, y in proposals:
        cv2.drawMarker(panel, (round(x), round(y)), (170, 170, 170), cv2.MARKER_CROSS, 8, 1)
    for target in targets:
        point = (int(target["x_px"]), int(target["y_px"]))
        cv2.circle(panel, point, round(TOLERANCE_PX), (0, 255, 255), 1)
        cv2.drawMarker(panel, point, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 11, 2)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(destination)


def run() -> dict[str, Any]:
    """Write the frozen G205 measurement artifacts and return its summary."""
    frames = _read_targets()
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    target_rows: list[dict[str, Any]] = []
    proposal_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    sorted_ids = sorted(frames)
    for index, audit_id in enumerate(sorted_ids):
        targets = frames[audit_id]
        image = cv2.imread(str(_source_path(targets[0])))
        if image is None:
            raise FileNotFoundError(_source_path(targets[0]))
        height, width = image.shape[:2]
        if (width, height) != (int(targets[0]["image_width"]), int(targets[0]["image_height"])):
            raise ValueError(f"native dimension mismatch for {audit_id}")
        proposals = propose(image)
        scored_targets, scored_proposals, all_four = score_frame(targets, proposals)
        target_rows.extend(scored_targets)
        proposal_rows.extend(scored_proposals)
        frame_rows.append({"candidate": CANDIDATE, "audit_id": audit_id, "image_width": width, "image_height": height, "proposals": len(proposals), "matched_roles": sum(bool(row["available"]) for row in scored_targets), "all_four_within_12px": all_four})
        if index in RENDER_INDICES:
            _render(image, targets, proposals, renders / f"{index:02d}_{audit_id}.jpg")
    _write_csv(OUT / "target_scores.csv", target_rows)
    _write_csv(OUT / "proposal_scores.csv", proposal_rows)
    _write_csv(OUT / "per_frame.csv", frame_rows)
    summary = {"candidate": CANDIDATE, "frames_all_four": sum(bool(row["all_four_within_12px"]) for row in frame_rows), "frames_total": len(frame_rows), "corner_recall": sum(bool(row["available"]) for row in target_rows), "corner_total": len(target_rows), "proposal_precision_hits": sum(bool(row["on_any_target"]) for row in proposal_rows), "proposal_total": len(proposal_rows), "tolerance_px": TOLERANCE_PX, "render_indices": list(RENDER_INDICES)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"candidate={CANDIDATE} all_four={summary['frames_all_four']}/{summary['frames_total']} recall={summary['corner_recall']}/{summary['corner_total']} precision={summary['proposal_precision_hits']}/{summary['proposal_total']}")
    return summary


if __name__ == "__main__":
    run()
