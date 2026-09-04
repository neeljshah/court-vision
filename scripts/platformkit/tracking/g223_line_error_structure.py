"""Characterize signed offset, angle, and conditioning for G217 oracle lines."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame
from scripts.platformkit.tracking.g210_court_model_fit_to_lines import _sources
from scripts.platformkit.tracking.g210b_court_fit_untruncated_search import oracle_fit
from scripts.platformkit.tracking.g217_oracle_error_decomposition import ROLE_PAIRS, _read_targets, true_paint_lines


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g223_line_error_structure_artifact"
EXPECTED_MEDIAN_PX = 10.2347919059155
EXPECTED_MAX_PX = 59.693249497295
LABEL_FLOOR_P90_PX = 11.39


def _normalised(line: np.ndarray) -> np.ndarray:
    norm = float(np.hypot(line[0], line[1]))
    if norm < 1e-12:
        raise ValueError("degenerate image line")
    return np.asarray(line, dtype=float) / norm


def canonical_line(selected: np.ndarray, truth: np.ndarray) -> np.ndarray:
    """Normalize selected line and orient its normal toward the truth normal."""
    selected_line, truth_line = _normalised(selected), _normalised(truth)
    if float(np.dot(selected_line[:2], truth_line[:2])) < 0.0:
        selected_line *= -1.0
    return selected_line


def angle_offset(
    selected: np.ndarray, truth: np.ndarray, first: tuple[float, float], second: tuple[float, float]
) -> tuple[float, float, float, float, float]:
    """Return acute line angle, midpoint offset, endpoint angle component, and signed endpoints."""
    line = canonical_line(selected, truth)
    first_point = np.array((first[0], first[1], 1.0))
    second_point = np.array((second[0], second[1], 1.0))
    first_distance, second_distance = float(line @ first_point), float(line @ second_point)
    midpoint_offset = (first_distance + second_distance) / 2.0
    endpoint_angle_component = abs(second_distance - first_distance) / 2.0
    alignment = float(np.clip(abs(np.dot(_normalised(selected)[:2], _normalised(truth)[:2])), 0.0, 1.0))
    return float(np.degrees(np.arccos(alignment))), midpoint_offset, endpoint_angle_component, first_distance, second_distance


def _line_angle(first: np.ndarray, second: np.ndarray) -> float:
    """Return the acute angle in degrees between two image lines."""
    alignment = float(np.clip(abs(np.dot(_normalised(first)[:2], _normalised(second)[:2])), 0.0, 1.0))
    return float(np.degrees(np.arccos(alignment)))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": float(np.mean(values)),
        "sample_sd": float(np.std(values, ddof=1)),
        "median": float(np.median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def _rank_desc(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: (-values[index], index))
    ranks = [0.0] * len(values)
    for rank, index in enumerate(order, start=1):
        ranks[index] = float(rank)
    return ranks


def _spearman_desc(first: list[float], second: list[float]) -> float:
    return float(np.corrcoef(_rank_desc(first), _rank_desc(second))[0, 1])


def _endpoints(line: np.ndarray, width: int, height: int) -> tuple[tuple[int, int], tuple[int, int]]:
    normal = _normalised(line)
    direction = np.array((-normal[1], normal[0]))
    point = -normal[2] * normal[:2]
    start = tuple(np.round(point - 10000.0 * direction).astype(int))
    end = tuple(np.round(point + 10000.0 * direction).astype(int))
    ok, clipped_start, clipped_end = cv2.clipLine((0, 0, width, height), start, end)
    if not ok:
        raise ValueError("line does not cross source image")
    return clipped_start, clipped_end


def _render(image: np.ndarray, targets: list[dict[str, str]], selected: dict[str, np.ndarray], truth: dict[str, np.ndarray], destination: Path) -> None:
    panel = image.copy()
    height, width = panel.shape[:2]
    for role in selected:
        cv2.line(panel, *_endpoints(selected[role], width, height), (0, 255, 0), 2, cv2.LINE_AA)
        cv2.line(panel, *_endpoints(truth[role], width, height), (0, 255, 255), 2, cv2.LINE_AA)
    for target in targets:
        cv2.drawMarker(panel, (round(float(target["x_px"])), round(float(target["y_px"]))), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 13, 2)
    cv2.putText(panel, "green: detected oracle line; yellow: label line; magenta: labelled corner", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(panel, "green: detected oracle line; yellow: label line; magenta: labelled corner", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)


def run() -> dict[str, Any]:
    """Reproduce G217 selection and write the G223 structure-only artifact."""
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    targets, sources = _read_targets(), _sources()
    selections: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    render_inputs: dict[str, tuple[np.ndarray, list[dict[str, str]], dict[str, np.ndarray], dict[str, np.ndarray]]] = {}
    for source in sources:
        image = cv2.imread(str(source.source_path), cv2.IMREAD_COLOR)
        if image is None or image.shape[1::-1] != (source.width, source.height):
            raise ValueError(f"bad source decode: {source.audit_id}")
        oracle, picked, g217_distances = oracle_fit(image, source.sport, targets[source.audit_id])
        if oracle is None:
            raise ValueError(f"G217 oracle unexpectedly unsolved: {source.audit_id}")
        groups = __import__("scripts.platformkit.tracking.g210_court_model_fit_to_lines", fromlist=["_groups"])._groups(image)
        truth = true_paint_lines(targets[source.audit_id])
        selected_lines: dict[str, np.ndarray] = {}
        role_rows: list[dict[str, Any]] = []
        for (role, first_role, second_role), group_index, g217_distance in zip(ROLE_PAIRS, picked, g217_distances):
            first_row = next(row for row in targets[source.audit_id] if row["role"] == first_role)
            second_row = next(row for row in targets[source.audit_id] if row["role"] == second_role)
            first = (float(first_row["x_px"]), float(first_row["y_px"]))
            second = (float(second_row["x_px"]), float(second_row["y_px"]))
            selected = groups[group_index].line
            angle, midpoint, angle_component, first_distance, second_distance = angle_offset(selected, truth[role], first, second)
            mean_abs = (abs(first_distance) + abs(second_distance)) / 2.0
            if not np.isclose(mean_abs, g217_distance, rtol=0.0, atol=1e-9):
                raise ValueError(f"G217 distance mismatch: {source.audit_id} {role}")
            selected_lines[role] = selected
            role_rows.append({
                "audit_id": source.audit_id, "sport": source.sport, "role": role, "group_index": group_index,
                "signed_first_corner_distance_px": f"{first_distance:.12f}", "signed_second_corner_distance_px": f"{second_distance:.12f}",
                "mean_signed_distance_px": f"{midpoint:.12f}", "mean_abs_distance_px": f"{mean_abs:.12f}",
                "angle_error_deg": f"{angle:.12f}", "midpoint_offset_px": f"{midpoint:.12f}",
                "endpoint_angle_component_px": f"{angle_component:.12f}",
            })
        oracle_rows, _, _ = score_frame(targets[source.audit_id], __import__("scripts.platformkit.tracking.g210b_court_fit_untruncated_search", fromlist=["_proposals"])._proposals(oracle, source.sport))
        corner_maximum = max(float(row["nearest_proposal_distance_px"]) for row in oracle_rows)
        corner_angles = [_line_angle(selected_lines[transverse], selected_lines[longitudinal]) for transverse in ("near_baseline", "near_free_throw") for longitudinal in ("lane_left", "lane_right")]
        frames.append({
            "audit_id": source.audit_id, "sport": source.sport, "source_path": str(source.source_path), "source_bytes": source.source_path.stat().st_size,
            "source_sha256": hashlib.sha256(source.source_path.read_bytes()).hexdigest(), "source_width_px": source.width, "source_height_px": source.height,
            "oracle_max_corner_error_px": f"{corner_maximum:.12f}", "max_role_angle_error_deg": f"{max(float(row['angle_error_deg']) for row in role_rows):.12f}",
            "max_abs_midpoint_offset_px": f"{max(abs(float(row['midpoint_offset_px'])) for row in role_rows):.12f}",
            "min_selected_intersection_angle_deg": f"{min(corner_angles):.12f}",
        })
        selections.extend(role_rows)
        render_inputs[source.audit_id] = (image, targets[source.audit_id], selected_lines, truth)
    absolute = [float(row["mean_abs_distance_px"]) for row in selections]
    if not (np.isclose(np.median(absolute), EXPECTED_MEDIAN_PX, atol=1e-9) and np.isclose(max(absolute), EXPECTED_MAX_PX, atol=1e-9)):
        raise ValueError("G217 selected-line control did not reproduce")
    role_summary: dict[str, Any] = {}
    for role, _, _ in ROLE_PAIRS:
        rows = [row for row in selections if row["role"] == role]
        signed = [float(row["mean_signed_distance_px"]) for row in rows]
        role_summary[role] = {**_stats(signed), "positive_n": sum(value > 0.0 for value in signed), "negative_n": sum(value < 0.0 for value in signed), "zero_n": sum(value == 0.0 for value in signed)}
    midpoint = [abs(float(row["midpoint_offset_px"])) for row in selections]
    angle_component = [float(row["endpoint_angle_component_px"]) for row in selections]
    corner_error = [float(row["oracle_max_corner_error_px"]) for row in frames]
    max_angle = [float(row["max_role_angle_error_deg"]) for row in frames]
    shallowness = [-float(row["min_selected_intersection_angle_deg"]) for row in frames]
    top_frames = [dict(row) for row in sorted(frames, key=lambda row: (-float(row["oracle_max_corner_error_px"]), row["audit_id"]))[:3]]
    for rank, frame in enumerate(top_frames, start=1):
        frame["corner_error_rank"] = rank
        _render(*render_inputs[frame["audit_id"]], renders / f"{rank:02d}_{frame['audit_id']}.jpg")
    summary = {
        "machine": "local Windows worktree C:/Users/neelj/nba-track-a5; no pod access",
        "frames_total": len(frames), "selections_total": len(selections), "label_repeatability_p90_px": LABEL_FLOOR_P90_PX,
        "g217_control": {"median_mean_abs_distance_px": float(np.median(absolute)), "max_mean_abs_distance_px": float(max(absolute))},
        "sign_convention": "True lines use G217 ordered ROLE_PAIRS. Each selected line is unit-normalized and multiplied by -1 only when its normal has negative dot product with that role's true-line normal. Positive signed distance is therefore the selected line's displacement toward that fixed true-line normal.",
        "per_role_signed_distance_px": role_summary,
        "decomposition_px": {"abs_midpoint_offset": _stats(midpoint), "endpoint_angle_component": _stats(angle_component), "angle_error_deg": _stats([float(row["angle_error_deg"]) for row in selections])},
        "corner_relation": {"spearman_corner_error_vs_max_role_angle": _spearman_desc(corner_error, max_angle), "spearman_corner_error_vs_shallowness": _spearman_desc(corner_error, shallowness), "top_frames": top_frames},
    }
    _write_csv(OUT / "per_selection.csv", selections)
    _write_csv(OUT / "per_frame.csv", frames)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"control_median={summary['g217_control']['median_mean_abs_distance_px']:.12f} control_max={summary['g217_control']['max_mean_abs_distance_px']:.12f}")
    return summary


if __name__ == "__main__":
    run()
