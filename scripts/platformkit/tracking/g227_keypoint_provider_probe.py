"""Measure the existing semantic basketball keypoint provider on G140 labels."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import (
    TOLERANCE_PX,
    _read_targets,
    _source_path,
    score_frame,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g227_keypoint_provider_probe"
CANDIDATE = "basketball_keypoint_provider_default"
DEFAULT_MIN_EDGE_SUPPORT = 0.16
RENDER_INDICES = (0, 4, 8, 12, 16)
ROLE_TO_PROVIDER = {
    "paint_near_baseline_left_corner": "left_paint_bl",
    "paint_near_baseline_right_corner": "left_paint_tl",
    "paint_near_free_throw_left_corner": "left_paint_br",
    "paint_near_free_throw_right_corner": "left_paint_tr",
}


def _provider_landmarks(detections: dict[str, tuple[float, float, float]]) -> dict[str, tuple[float, float, float]]:
    """Return the four fixed-role provider landmarks, or no proposal."""
    if not all(name in detections for name in ROLE_TO_PROVIDER.values()):
        return {}
    return {role: detections[name] for role, name in ROLE_TO_PROVIDER.items()}


def _role_distance(target: dict[str, str], landmarks: dict[str, tuple[float, float, float]]) -> float:
    detection = landmarks.get(target["role"])
    if detection is None:
        return float("inf")
    return float(np.hypot(float(target["x_px"]) - detection[0], float(target["y_px"]) - detection[1]))


def _contour_diagnostic(frame: np.ndarray) -> dict[str, int]:
    """Count the provider's fixed absolute-perimeter gate without altering it."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    perimeters = [float(cv2.arcLength(contour, True)) for contour in contours]
    return {
        "contours_total": len(perimeters),
        "contours_perimeter_ge_120": sum(value >= 120.0 for value in perimeters),
    }


def _render(
    image: np.ndarray,
    targets: list[dict[str, str]],
    landmarks: dict[str, tuple[float, float, float]],
    destination: Path,
) -> None:
    panel = image.copy()
    ordered = [landmarks[role] for role in ROLE_TO_PROVIDER if role in landmarks]
    if len(ordered) == 4:
        polygon = np.asarray([(round(item[0]), round(item[1])) for item in ordered], dtype=np.int32)
        cv2.polylines(panel, [polygon], True, (255, 255, 0), 2)
    for target in targets:
        point = (int(target["x_px"]), int(target["y_px"]))
        cv2.circle(panel, point, round(TOLERANCE_PX), (0, 255, 255), 1)
        cv2.drawMarker(panel, point, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 11, 2)
    for role, landmark in landmarks.items():
        point = (round(landmark[0]), round(landmark[1]))
        cv2.drawMarker(panel, point, (0, 255, 0), cv2.MARKER_CROSS, 11, 2)
        cv2.putText(panel, ROLE_TO_PROVIDER[role], point, cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 0), 1)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(destination)


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _league(audit_id: str) -> str:
    return "wnba" if audit_id.startswith("wnba__") else "ncaa_basketball"


def run() -> dict[str, Any]:
    """Write G227 artifacts using one predeclared provider configuration."""
    if TOLERANCE_PX != 12.0:
        raise ValueError("G205 tolerance changed")
    frames = _read_targets()
    provider = BasketballKeypointProvider(min_edge_support=DEFAULT_MIN_EDGE_SUPPORT)
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    target_rows: list[dict[str, Any]] = []
    proposal_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    closest: tuple[float, int, str, np.ndarray, list[dict[str, str]], dict[str, tuple[float, float, float]]] | None = None
    for index, audit_id in enumerate(sorted(frames)):
        targets = frames[audit_id]
        source = _source_path(targets[0])
        image = cv2.imread(str(source))
        if image is None:
            raise FileNotFoundError(source)
        height, width = image.shape[:2]
        if (width, height) != (int(targets[0]["image_width"]), int(targets[0]["image_height"])):
            raise ValueError(f"native dimension mismatch for {audit_id}")
        detections = provider.detect(image)
        landmarks = _provider_landmarks(detections)
        proposals = [(item[0], item[1]) for item in landmarks.values()]
        scored_targets, scored_proposals, all_four = score_frame(targets, proposals)
        mapped_distances = [_role_distance(target, landmarks) for target in targets]
        diagnostic = _contour_diagnostic(image)
        for target, score, distance in zip(targets, scored_targets, mapped_distances):
            target_rows.append({
                **score,
                "candidate": CANDIDATE,
                "provider_landmark": ROLE_TO_PROVIDER[target["role"]],
                "mapped_distance_px": distance,
                "mapped_available": distance <= TOLERANCE_PX,
            })
        for score, (role, landmark) in zip(scored_proposals, landmarks.items()):
            proposal_rows.append({**score, "candidate": CANDIDATE, "role": role,
                                  "provider_landmark": ROLE_TO_PROVIDER[role], "confidence": landmark[2]})
        max_distance = max(mapped_distances)
        frame_rows.append({
            "candidate": CANDIDATE,
            "audit_id": audit_id,
            "league": _league(audit_id),
            "source_decode": str(source.relative_to(Path.cwd())).replace("\\", "/"),
            "source_bytes": source.stat().st_size,
            "image_width": width,
            "image_height": height,
            "selected_paint_quad": bool(landmarks),
            "abstained": not bool(landmarks),
            "named_corner_proposals": len(proposals),
            "matched_roles_g205": sum(bool(row["available"]) for row in scored_targets),
            "all_four_within_12px_g205": all_four,
            "all_four_within_12px_mapped": all(distance <= TOLERANCE_PX for distance in mapped_distances),
            "max_mapped_distance_px": max_distance,
            **diagnostic,
        })
        if index in RENDER_INDICES:
            _render(image, targets, landmarks, renders / f"{index:02d}_{audit_id}.jpg")
        candidate = (max_distance, index, audit_id, image, targets, landmarks)
        if closest is None or candidate[:3] < closest[:3]:
            closest = candidate
    assert closest is not None
    _render(closest[3], closest[4], closest[5], renders / f"closest_{closest[1]:02d}_{closest[2]}.jpg")
    target_fields = list(target_rows[0])
    proposal_fields = list(proposal_rows[0]) if proposal_rows else ["audit_id", "rank", "x_px", "y_px", "nearest_target_distance_px", "on_any_target", "candidate", "role", "provider_landmark", "confidence"]
    _write_csv(OUT / "target_scores.csv", target_rows, target_fields)
    _write_csv(OUT / "proposal_scores.csv", proposal_rows, proposal_fields)
    _write_csv(OUT / "per_frame.csv", frame_rows, list(frame_rows[0]))
    splits: dict[str, dict[str, int]] = {}
    for league in ("ncaa_basketball", "wnba"):
        league_frames = [row for row in frame_rows if row["league"] == league]
        league_targets = [row for row in target_rows if _league(str(row["audit_id"])) == league]
        splits[league] = {
            "frames": len(league_frames),
            "all_four_g205": sum(bool(row["all_four_within_12px_g205"]) for row in league_frames),
            "corner_recall_g205": sum(bool(row["available"]) for row in league_targets),
            "corner_total": len(league_targets),
            "selected_paint_quads": sum(bool(row["selected_paint_quad"]) for row in league_frames),
            "abstentions": sum(bool(row["abstained"]) for row in league_frames),
            "proposed_but_missed_frames": sum(not bool(row["abstained"]) and not bool(row["all_four_within_12px_g205"]) for row in league_frames),
            "named_corner_proposals": sum(int(row["named_corner_proposals"]) for row in league_frames),
        }
    summary = {
        "candidate": CANDIDATE,
        "min_edge_support": DEFAULT_MIN_EDGE_SUPPORT,
        "tolerance_px": TOLERANCE_PX,
        "frames_all_four_g205": sum(bool(row["all_four_within_12px_g205"]) for row in frame_rows),
        "frames_total": len(frame_rows),
        "corner_recall_g205": sum(bool(row["available"]) for row in target_rows),
        "corner_total": len(target_rows),
        "selected_paint_quads": sum(bool(row["selected_paint_quad"]) for row in frame_rows),
        "abstentions": sum(bool(row["abstained"]) for row in frame_rows),
        "proposed_but_missed_frames": sum(not bool(row["abstained"]) and not bool(row["all_four_within_12px_g205"]) for row in frame_rows),
        "named_corner_proposals": sum(int(row["named_corner_proposals"]) for row in frame_rows),
        "splits": splits,
        "render_indices": list(RENDER_INDICES),
        "closest_render": f"closest_{closest[1]:02d}_{closest[2]}.jpg",
    }
    summary["named_corner_proposals_per_frame"] = summary["named_corner_proposals"] / summary["frames_total"]
    summary["selected_paint_quads_per_frame"] = summary["selected_paint_quads"] / summary["frames_total"]
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"candidate={CANDIDATE} all_four={summary['frames_all_four_g205']}/{summary['frames_total']} recall={summary['corner_recall_g205']}/{summary['corner_total']} abstentions={summary['abstentions']}")
    return summary


if __name__ == "__main__":
    run()
