"""Measure a fixed Harris corner proposal against G140 pixel targets."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import cv2


REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKING_ROOT = REPO_ROOT / "docs" / "evidence" / "tracking"
TARGETS_PATH = TRACKING_ROOT / "g140_corner_targets" / "corner_pixel_targets.csv"
OUTPUT_DIR = TRACKING_ROOT / "g141_corner_recall"
TOLERANCE_PX = 12.0
MAX_CORNERS = 100
QUALITY_LEVEL = 0.01
MIN_DISTANCE_PX = 10.0
BLOCK_SIZE = 5
HARRIS_K = 0.04
WILSON_Z = 1.959963984540054
RENDER_POSITIONS = (0, 3, 5, 8, 10, 13, 16)
ROLE_SHORT_NAMES = {
    "paint_near_baseline_left_corner": "BL",
    "paint_near_baseline_right_corner": "BR",
    "paint_near_free_throw_left_corner": "FL",
    "paint_near_free_throw_right_corner": "FR",
}
PAINT_DEPTH_FEET = 19.0


def propose_corners(image: Any) -> list[tuple[int, int]]:
    """Return fixed-parameter native-pixel Harris corner proposals."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners = cv2.goodFeaturesToTrack(
        gray,
        maxCorners=MAX_CORNERS,
        qualityLevel=QUALITY_LEVEL,
        minDistance=MIN_DISTANCE_PX,
        blockSize=BLOCK_SIZE,
        useHarrisDetector=True,
        k=HARRIS_K,
    )
    if corners is None:
        return []
    return [(round(float(point[0][0])), round(float(point[0][1]))) for point in corners]


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Return a two-sided 95 percent Wilson interval as proportions."""
    if total <= 0:
        raise ValueError("Wilson interval needs a positive denominator")
    proportion = successes / total
    z_squared = WILSON_Z * WILSON_Z
    denominator = 1.0 + z_squared / total
    center = (proportion + z_squared / (2.0 * total)) / denominator
    margin = WILSON_Z * math.sqrt(
        proportion * (1.0 - proportion) / total + z_squared / (4.0 * total * total)
    ) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _distance(point: tuple[int, int], target: dict[str, str]) -> float:
    return math.dist(point, (float(target["x_px"]), float(target["y_px"])))


def score_targets(
    targets: Iterable[dict[str, str]],
    proposals_by_audit_id: dict[str, list[tuple[int, int]]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    """Score every committed G140 target and every generic local proposal."""
    target_rows = list(targets)
    target_keys = {(row["clip"], row["source_frame"], row["role"]) for row in target_rows}
    if len(target_rows) != len(target_keys):
        raise ValueError("G140 target keys must be unique")
    grouped_targets: dict[str, list[dict[str, str]]] = defaultdict(list)
    for target in target_rows:
        grouped_targets[target["audit_id"]].append(target)
    if set(grouped_targets) != set(proposals_by_audit_id):
        raise ValueError("proposal frames must exactly equal G140 target frames")

    target_scores: list[dict[str, object]] = []
    proposal_scores: list[dict[str, object]] = []
    for audit_id, frame_targets in grouped_targets.items():
        proposals = proposals_by_audit_id[audit_id]
        for target in frame_targets:
            distances = [_distance(point, target) for point in proposals]
            nearest_distance = min(distances, default=math.inf)
            nearest_rank = distances.index(nearest_distance) + 1 if distances else None
            target_scores.append({
                "audit_id": audit_id,
                "clip": target["clip"],
                "source_frame": int(target["source_frame"]),
                "role": target["role"],
                "target_x_px": int(target["x_px"]),
                "target_y_px": int(target["y_px"]),
                "proposal_count": len(proposals),
                "nearest_proposal_distance_px": round(nearest_distance, 6),
                "nearest_proposal_rank": nearest_rank,
                "available": nearest_distance <= TOLERANCE_PX,
            })
        for rank, point in enumerate(proposals, start=1):
            distances = [_distance(point, target) for target in frame_targets]
            nearest_distance = min(distances, default=math.inf)
            proposal_scores.append({
                "audit_id": audit_id,
                "rank": rank,
                "x_px": point[0],
                "y_px": point[1],
                "nearest_target_distance_px": round(nearest_distance, 6),
                "on_any_target": nearest_distance <= TOLERANCE_PX,
            })

    by_role = Counter(row["role"] for row in target_scores)
    detected_by_role = Counter(row["role"] for row in target_scores if row["available"])
    role_metrics = []
    for role in sorted(by_role):
        lower, upper = wilson_interval(detected_by_role[role], by_role[role])
        role_metrics.append({
            "role": role,
            "detected": detected_by_role[role],
            "denominator": by_role[role],
            "recall": detected_by_role[role] / by_role[role],
            "wilson_95_lower": lower,
            "wilson_95_upper": upper,
        })
    available = sum(bool(row["available"]) for row in target_scores)
    matched_proposals = sum(bool(row["on_any_target"]) for row in proposal_scores)
    recall_lower, recall_upper = wilson_interval(available, len(target_scores))
    precision_lower, precision_upper = wilson_interval(matched_proposals, len(proposal_scores))
    return target_scores, proposal_scores, {
        "role_metrics": role_metrics,
        "targets": len(target_scores),
        "available_targets": available,
        "recall": available / len(target_scores),
        "recall_wilson_95": [recall_lower, recall_upper],
        "proposals": len(proposal_scores),
        "matched_proposals": matched_proposals,
        "precision": matched_proposals / len(proposal_scores),
        "precision_wilson_95": [precision_lower, precision_upper],
    }


def _load_targets() -> list[dict[str, str]]:
    with TARGETS_PATH.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 68 or len({row["audit_id"] for row in rows}) != 17:
        raise ValueError("G140 must retain 68 targets across 17 source frames")
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"cannot write empty artifact: {path}")
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _scale_rows(targets: list[dict[str, str]]) -> list[dict[str, object]]:
    by_audit_id: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for target in targets:
        by_audit_id[target["audit_id"]][target["role"]] = target
    rows = []
    for audit_id, roles in sorted(by_audit_id.items()):
        for side, baseline, free_throw in (
            ("left", "paint_near_baseline_left_corner", "paint_near_free_throw_left_corner"),
            ("right", "paint_near_baseline_right_corner", "paint_near_free_throw_right_corner"),
        ):
            pixel_depth = math.dist(
                (float(roles[baseline]["x_px"]), float(roles[baseline]["y_px"])),
                (float(roles[free_throw]["x_px"]), float(roles[free_throw]["y_px"])),
            )
            rows.append({
                "audit_id": audit_id,
                "clip": roles[baseline]["clip"],
                "source_frame": roles[baseline]["source_frame"],
                "side": side,
                "paint_depth_px": round(pixel_depth, 6),
                "paint_depth_feet_assumed": PAINT_DEPTH_FEET,
                "tolerance_px": TOLERANCE_PX,
                "tolerance_feet_along_paint_depth": round(TOLERANCE_PX * PAINT_DEPTH_FEET / pixel_depth, 6),
            })
    return rows


def _write_render(
    audit_id: str,
    source: Path,
    targets: list[dict[str, str]],
    proposals: list[tuple[int, int]],
) -> str:
    image = cv2.imread(str(source))
    if image is None:
        raise ValueError(f"missing source image: {source}")
    for point in proposals:
        cv2.drawMarker(image, point, (160, 160, 160), cv2.MARKER_CROSS, 9, 1)
    for target in targets:
        point = (int(target["x_px"]), int(target["y_px"]))
        cv2.circle(image, point, round(TOLERANCE_PX), (0, 255, 255), 1)
        cv2.drawMarker(image, point, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 15, 2)
        cv2.putText(image, ROLE_SHORT_NAMES[target["role"]], (point[0] + 5, point[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 2)
        cv2.putText(image, ROLE_SHORT_NAMES[target["role"]], (point[0] + 5, point[1] - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
    output = OUTPUT_DIR / "renders" / f"{audit_id}.jpg"
    if not cv2.imwrite(str(output), image):
        raise ValueError(f"cannot write render: {output}")
    return f"renders/{output.name}"


def write_artifacts() -> None:
    """Generate fixed proposals, scores, conversion context, and diagnostic renders."""
    targets = _load_targets()
    OUTPUT_DIR.mkdir(exist_ok=True)
    render_dir = OUTPUT_DIR / "renders"
    render_dir.mkdir(exist_ok=True)
    for render in render_dir.glob("*.jpg"):
        render.unlink()
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for target in targets:
        grouped[target["audit_id"]].append(target)
    proposals_by_audit_id: dict[str, list[tuple[int, int]]] = {}
    raw_proposals: list[dict[str, object]] = []
    source_paths: dict[str, Path] = {}
    for audit_id, frame_targets in grouped.items():
        source = (TARGETS_PATH.parent / frame_targets[0]["source_decode"]).resolve()
        image = cv2.imread(str(source))
        if image is None:
            raise ValueError(f"missing source image: {source}")
        if image.shape[1] != int(frame_targets[0]["image_width"]) or image.shape[0] != int(frame_targets[0]["image_height"]):
            raise ValueError(f"source dimensions differ from G140 target: {audit_id}")
        proposals = propose_corners(image)
        proposals_by_audit_id[audit_id] = proposals
        source_paths[audit_id] = source
        for rank, point in enumerate(proposals, start=1):
            raw_proposals.append({"audit_id": audit_id, "rank": rank, "x_px": point[0], "y_px": point[1]})
    target_scores, proposal_scores, summary = score_targets(targets, proposals_by_audit_id)
    sorted_audit_ids = sorted(grouped)
    render_paths = [
        _write_render(audit_id, source_paths[audit_id], grouped[audit_id], proposals_by_audit_id[audit_id])
        for audit_id in (sorted_audit_ids[position] for position in RENDER_POSITIONS)
    ]
    scales = _scale_rows(targets)
    summary.update({
        "g140_targets_path": "../g140_corner_targets/corner_pixel_targets.csv",
        "unique_frames": len(grouped),
        "tolerance_px": TOLERANCE_PX,
        "parameters": {
            "max_corners": MAX_CORNERS,
            "quality_level": QUALITY_LEVEL,
            "min_distance_px": MIN_DISTANCE_PX,
            "block_size": BLOCK_SIZE,
            "harris_k": HARRIS_K,
        },
        "render_audit_ids": [sorted_audit_ids[position] for position in RENDER_POSITIONS],
        "render_paths": render_paths,
        "scale_conversion_feet": {
            "minimum": min(row["tolerance_feet_along_paint_depth"] for row in scales),
            "median": sorted(row["tolerance_feet_along_paint_depth"] for row in scales)[len(scales) // 2],
            "maximum": max(row["tolerance_feet_along_paint_depth"] for row in scales),
        },
    })
    _write_csv(OUTPUT_DIR / "proposals.csv", raw_proposals)
    _write_csv(OUTPUT_DIR / "target_scores.csv", target_scores)
    _write_csv(OUTPUT_DIR / "proposal_scores.csv", proposal_scores)
    _write_csv(OUTPUT_DIR / "scale_conversion.csv", scales)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii")
    print(f"g141 targets={summary['targets']} available={summary['available_targets']} proposals={summary['proposals']}")


if __name__ == "__main__":
    write_artifacts()
