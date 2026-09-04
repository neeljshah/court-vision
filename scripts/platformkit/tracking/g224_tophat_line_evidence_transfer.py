"""Measure fixed tennis top-hat line evidence on the G217 basketball construct."""
from __future__ import annotations

import csv
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import ObservedSegment
from domains.tennis.tracking.court_lines import TOPHAT_CONTRASTS, TOPHAT_KERNEL_720P_PX
from scripts.platformkit.g123_low_contrast_lines import enhance_contrast
from scripts.platformkit.g132_additive_candidate_union import union_segments
from scripts.platformkit.g134_grouping_stability import stable_groups
from scripts.platformkit.tracking import g205_zero_shot_corner_probe as g205
from scripts.platformkit.tracking import g210b_court_fit_untruncated_search as g210b
from scripts.platformkit.tracking.g210_court_model_fit_to_lines import _sources


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g224_tophat_line_evidence_transfer_artifact"
MIN_LSD_LENGTH_PX = 28.0
TOPHAT_CONTRAST = TOPHAT_CONTRASTS[0]
RENDER_INDICES = (0, 8, 16)
ROLE_PAIRS = (
    ("near_baseline", 0, 1),
    ("near_free_throw", 2, 3),
    ("lane_left", 0, 2),
    ("lane_right", 1, 3),
)


def kernel_size(height: int) -> int:
    """Scale tennis's fixed 720p kernel by native image height and keep it odd."""
    return max(3, int(round(TOPHAT_KERNEL_720P_PX * height / 720.0)) | 1)


def tophat_mask(frame: np.ndarray) -> np.ndarray:
    """Return the one fixed thin-bright-structure mask for a native frame."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    size = kernel_size(frame.shape[0])
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    return cv2.inRange(cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel), TOPHAT_CONTRAST, 255)


def tophat_lsd_segments(frame: np.ndarray, min_length: float = MIN_LSD_LENGTH_PX) -> list[ObservedSegment]:
    """Run the existing OpenCV LSD over top-hat evidence instead of raw grayscale."""
    detected = cv2.createLineSegmentDetector().detect(tophat_mask(frame))[0]
    if detected is None:
        return []
    return [segment for values in detected.reshape(-1, detected.shape[-1])
            if (segment := ObservedSegment(tuple(float(value) for value in values))).length >= min_length]


def tophat_groups(image: np.ndarray):
    """Keep G210's raw-plus-CLAHE grouping topology while replacing evidence only."""
    baseline = tophat_lsd_segments(image, MIN_LSD_LENGTH_PX)
    enhanced = tophat_lsd_segments(enhance_contrast(image), MIN_LSD_LENGTH_PX)
    return stable_groups(baseline, union_segments(baseline, enhanced))


@contextmanager
def _tophat_route() -> Iterator[None]:
    """Temporarily replace only the line-evidence call sites in this local process."""
    prior_groups, prior_segments = g210b._groups, g205.detect_lsd_segments
    g210b._groups, g205.detect_lsd_segments = tophat_groups, tophat_lsd_segments
    try:
        yield
    finally:
        g210b._groups, g205.detect_lsd_segments = prior_groups, prior_segments


def _read_targets() -> dict[str, list[dict[str, str]]]:
    with (ROOT / "g140_corner_targets/corner_pixel_targets.csv").open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row["audit_id"], []).append(row)
    if len(rows) != 68 or len(grouped) != 17 or any(len(values) != 4 for values in grouped.values()):
        raise ValueError("G140 construct changed")
    return grouped


def _max_error(rows: list[dict[str, Any]]) -> float:
    return max(float(row["nearest_proposal_distance_px"]) for row in rows)


def _distance_rows(image: np.ndarray, sport: str, targets: list[dict[str, str]], arm: str) -> tuple[np.ndarray | None, list[dict[str, Any]]]:
    homography, picked, distances = g210b.oracle_fit(image, sport, targets)
    records = []
    for (role, first, second), index, distance in zip(ROLE_PAIRS, picked, distances):
        records.append({"arm": arm, "role": role, "group_index": index,
                        "mean_abs_point_line_distance_px": f"{distance:.12f}",
                        "target_roles": f"{targets[first]['role']};{targets[second]['role']}"})
    return homography, records


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _panel(image: np.ndarray, targets: list[dict[str, str]], groups: list[Any], label: str) -> np.ndarray:
    panel = image.copy()
    for group in groups:
        for segment in group.segments:
            x1, y1, x2, y2 = (round(value) for value in segment.endpoints)
            cv2.line(panel, (x1, y1), (x2, y2), (170, 170, 170), 1, cv2.LINE_AA)
    for target in targets:
        point = (round(float(target["x_px"])), round(float(target["y_px"])))
        cv2.circle(panel, point, round(g205.TOLERANCE_PX), (0, 255, 255), 1, cv2.LINE_AA)
        cv2.drawMarker(panel, point, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 13, 2, cv2.LINE_AA)
    cv2.putText(panel, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(panel, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return panel


def _render(image: np.ndarray, targets: list[dict[str, str]], destination: Path) -> None:
    raw = _panel(image, targets, g210b._groups(image), "raw LSD evidence")
    top_hat = _panel(image, targets, tophat_groups(image), "top-hat LSD evidence")
    if not cv2.imwrite(str(destination), cv2.hconcat((raw, top_hat)), [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)


def run() -> dict[str, Any]:
    """Run the preregistered single top-hat evidence substitution on all 17 frames."""
    OUT.mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    targets, frames, distances = _read_targets(), [], []
    raw_counts, top_hat_counts, raw_distances, top_hat_distances = [], [], [], []
    for index, source in enumerate(_sources()):
        image = cv2.imread(str(source.source_path), cv2.IMREAD_COLOR)
        if image is None or image.shape[1::-1] != (source.width, source.height):
            raise ValueError(f"bad source decode: {source.audit_id}")
        raw_fit = g210b.fit_image(image, source.sport)
        raw_oracle, raw_rows = _distance_rows(image, source.sport, targets[source.audit_id], "raw_lsd")
        raw_scores, _, raw_real_all = g205.score_frame(targets[source.audit_id], g210b._proposals(None if raw_fit is None else np.asarray(raw_fit.homography_image_to_court), source.sport))
        raw_oracle_scores, _, raw_oracle_all = g205.score_frame(targets[source.audit_id], g210b._proposals(raw_oracle, source.sport))
        raw_proposals = g205.propose(image)
        with _tophat_route():
            top_hat_fit = g210b.fit_image(image, source.sport)
            top_hat_oracle, top_hat_rows = _distance_rows(image, source.sport, targets[source.audit_id], "top_hat")
            top_hat_scores, _, top_hat_real_all = g205.score_frame(targets[source.audit_id], g210b._proposals(None if top_hat_fit is None else np.asarray(top_hat_fit.homography_image_to_court), source.sport))
            top_hat_oracle_scores, _, top_hat_oracle_all = g205.score_frame(targets[source.audit_id], g210b._proposals(top_hat_oracle, source.sport))
            top_hat_proposals = g205.propose(image)
        raw_distances.extend(raw_rows)
        top_hat_distances.extend(top_hat_rows)
        distances.extend({"audit_id": source.audit_id, **row} for row in [*raw_rows, *top_hat_rows])
        raw_counts.append(len(raw_proposals))
        top_hat_counts.append(len(top_hat_proposals))
        frames.append({"audit_id": source.audit_id, "sport": source.sport, "source_path": str(source.source_path),
                       "source_bytes": source.source_path.stat().st_size, "source_sha256": hashlib.sha256(source.source_path.read_bytes()).hexdigest(),
                       "source_width_px": source.width, "source_height_px": source.height, "top_hat_kernel_px": kernel_size(source.height),
                       "raw_real_all_four_within_12px": raw_real_all, "raw_oracle_all_four_within_12px": raw_oracle_all,
                       "raw_oracle_max_corner_error_px": f"{_max_error(raw_oracle_scores):.12f}", "raw_proposals": len(raw_proposals),
                       "top_hat_real_all_four_within_12px": top_hat_real_all, "top_hat_oracle_all_four_within_12px": top_hat_oracle_all,
                       "top_hat_oracle_max_corner_error_px": f"{_max_error(top_hat_oracle_scores):.12f}", "top_hat_proposals": len(top_hat_proposals)})
        if index in RENDER_INDICES:
            _render(image, targets[source.audit_id], OUT / "renders" / f"{index:02d}_{source.audit_id}.jpg")
    summary = {"machine": "local Windows worktree C:/Users/neelj/nba-track-a3; no pod access", "frames_total": len(frames), "corner_roles_total": len(distances) // 2,
               "tolerance_px": g205.TOLERANCE_PX, "configuration": {"kernel_720p_px": TOPHAT_KERNEL_720P_PX, "kernel_rule": "round(11 * native_height / 720), odd, minimum 3", "contrast": TOPHAT_CONTRAST, "min_lsd_length_px": MIN_LSD_LENGTH_PX},
               "raw_lsd": {"real_frames_all_four": sum(bool(row["raw_real_all_four_within_12px"]) for row in frames), "oracle_frames_all_four": sum(bool(row["raw_oracle_all_four_within_12px"]) for row in frames), "selected_line_distance_px": {"median": float(np.median([float(row["mean_abs_point_line_distance_px"]) for row in raw_distances])), "max": float(max(float(row["mean_abs_point_line_distance_px"]) for row in raw_distances))}, "proposals_per_frame": float(np.mean(raw_counts))},
               "top_hat": {"real_frames_all_four": sum(bool(row["top_hat_real_all_four_within_12px"]) for row in frames), "oracle_frames_all_four": sum(bool(row["top_hat_oracle_all_four_within_12px"]) for row in frames), "selected_line_distance_px": {"median": float(np.median([float(row["mean_abs_point_line_distance_px"]) for row in top_hat_distances])), "max": float(max(float(row["mean_abs_point_line_distance_px"]) for row in top_hat_distances))}, "proposals_per_frame": float(np.mean(top_hat_counts))}, "render_indices": list(RENDER_INDICES)}
    _write_csv(OUT / "per_frame.csv", frames)
    _write_csv(OUT / "selected_line_distances.csv", distances)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"raw_real={summary['raw_lsd']['real_frames_all_four']}/17 raw_oracle={summary['raw_lsd']['oracle_frames_all_four']}/17 top_hat_real={summary['top_hat']['real_frames_all_four']}/17 top_hat_oracle={summary['top_hat']['oracle_frames_all_four']}/17")
    return summary


if __name__ == "__main__":
    run()
