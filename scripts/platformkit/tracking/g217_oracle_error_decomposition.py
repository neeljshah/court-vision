"""Attribute G210b oracle error between detected and exact labelled paint lines."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame
from scripts.platformkit.tracking.g210_court_model_fit_to_lines import _court_lines, _sources, solve_line_pairs
from scripts.platformkit.tracking.g210b_court_fit_untruncated_search import _proposals, _render, fit_image, oracle_fit


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g217_oracle_error_decomposition_artifact"
ROLE_PAIRS = (
    ("near_baseline", "paint_near_baseline_left_corner", "paint_near_baseline_right_corner"),
    ("near_free_throw", "paint_near_free_throw_left_corner", "paint_near_free_throw_right_corner"),
    ("lane_left", "paint_near_baseline_left_corner", "paint_near_free_throw_left_corner"),
    ("lane_right", "paint_near_baseline_right_corner", "paint_near_free_throw_right_corner"),
)
RENDER_INDICES = (0, 8, 16)


def true_paint_lines(targets: list[dict[str, str]]) -> dict[str, np.ndarray]:
    """Construct the four prescribed image paint lines from G140 corner labels."""
    points = {
        row["role"]: np.array((float(row["x_px"]), float(row["y_px"]), 1.0))
        for row in targets
    }
    required = {role for _, first, second in ROLE_PAIRS for role in (first, second)}
    if set(points) != required:
        raise ValueError("G217 requires exactly the four G140 paint-corner roles")
    lines = {}
    for name, first, second in ROLE_PAIRS:
        line = np.cross(points[first], points[second])
        norm = float(np.hypot(line[0], line[1]))
        if norm < 1e-12:
            raise ValueError(f"degenerate labelled line: {name}")
        lines[name] = line / norm
    return lines


def true_line_fit(targets: list[dict[str, str]], sport: str) -> np.ndarray | None:
    """Pass exact labelled paint lines to G210's unchanged line-pair solver."""
    lines, model = true_paint_lines(targets), _court_lines(sport)
    return solve_line_pairs(
        (lines["near_baseline"], lines["near_free_throw"]),
        (lines["lane_left"], lines["lane_right"]),
        (model["near_baseline"], model["near_free_throw"]),
        (model["lane_left"], model["lane_right"]),
    )


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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_pair(image: np.ndarray, oracle: np.ndarray, truth: np.ndarray, sport: str, destination: Path) -> None:
    left, right = OUT / "temporary_oracle.jpg", OUT / "temporary_true.jpg"
    _render(image, oracle, sport, left)
    _render(image, truth, sport, right)
    oracle_panel, truth_panel = cv2.imread(str(left)), cv2.imread(str(right))
    left.unlink()
    right.unlink()
    if oracle_panel is None or truth_panel is None:
        raise ValueError("G217 render read failed")
    cv2.putText(oracle_panel, "G210b detected-line oracle", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(oracle_panel, "G210b detected-line oracle", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(truth_panel, "G217 exact labelled lines", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(truth_panel, "G217 exact labelled lines", (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    if not cv2.imwrite(str(destination), cv2.hconcat((oracle_panel, truth_panel)), [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise OSError(destination)


def run() -> dict[str, Any]:
    """Reproduce G210b and score the exact-line control on all 17 local frames."""
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    targets, sources = _read_targets(), _sources()
    frames: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    oracle_scores: list[dict[str, Any]] = []
    true_scores: list[dict[str, Any]] = []
    label_free_scores: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        image = cv2.imread(str(source.source_path), cv2.IMREAD_COLOR)
        if image is None or image.shape[1::-1] != (source.width, source.height):
            raise ValueError(f"bad source decode: {source.audit_id}")
        source_bytes = source.source_path.stat().st_size
        source_hash = hashlib.sha256(source.source_path.read_bytes()).hexdigest()
        label_free = fit_image(image, source.sport)
        label_rows, _, label_all = score_frame(
            targets[source.audit_id],
            _proposals(None if label_free is None else np.asarray(label_free.homography_image_to_court), source.sport),
        )
        oracle, picked, distances = oracle_fit(image, source.sport, targets[source.audit_id])
        oracle_rows, _, oracle_all = score_frame(targets[source.audit_id], _proposals(oracle, source.sport))
        truth = true_line_fit(targets[source.audit_id], source.sport)
        true_rows, _, true_all = score_frame(targets[source.audit_id], _proposals(truth, source.sport))
        label_free_scores.extend(label_rows)
        oracle_scores.extend(oracle_rows)
        true_scores.extend(true_rows)
        for (role, _, _), group_index, distance in zip(ROLE_PAIRS, picked, distances):
            selected.append({"audit_id": source.audit_id, "sport": source.sport, "role": role, "group_index": group_index, "mean_abs_point_line_distance_px": f"{distance:.12f}"})
        frames.append({
            "audit_id": source.audit_id,
            "sport": source.sport,
            "source_path": str(source.source_path),
            "source_bytes": source_bytes,
            "source_sha256": source_hash,
            "source_width_px": source.width,
            "source_height_px": source.height,
            "g210b_label_free_all_four_within_12px": label_all,
            "g210b_label_free_max_corner_error_px": f"{_max_error(label_rows):.12f}",
            "g210b_oracle_all_four_within_12px": oracle_all,
            "g210b_oracle_max_corner_error_px": f"{_max_error(oracle_rows):.12f}",
            "true_line_all_four_within_12px": true_all,
            "true_line_max_corner_error_px": f"{_max_error(true_rows):.12f}",
        })
        if index in RENDER_INDICES:
            _render_pair(image, oracle, truth, source.sport, renders / f"{index:02d}_{source.audit_id}.jpg")
    label_free_maxima = [_max_error(label_free_scores[index:index + 4]) for index in range(0, len(label_free_scores), 4)]
    oracle_maxima = [_max_error(oracle_scores[index:index + 4]) for index in range(0, len(oracle_scores), 4)]
    true_maxima = [_max_error(true_scores[index:index + 4]) for index in range(0, len(true_scores), 4)]
    summary = {
        "machine": "local Windows worktree C:/Users/neelj/nba-track-a5; no pod access",
        "frames_total": len(frames),
        "corner_roles_total": len(selected),
        "tolerance_px": 12.0,
        "g210b_label_free_frames_all_four": sum(bool(row["g210b_label_free_all_four_within_12px"]) for row in frames),
        "g210b_label_free_median_max_corner_error_px": float(np.median(label_free_maxima)),
        "g210b_oracle_frames_all_four": sum(bool(row["g210b_oracle_all_four_within_12px"]) for row in frames),
        "g210b_oracle_median_max_corner_error_px": float(np.median(oracle_maxima)),
        "g210b_oracle_selected_line_distance_px": {"min": float(min(float(row["mean_abs_point_line_distance_px"]) for row in selected)), "median": float(np.median([float(row["mean_abs_point_line_distance_px"]) for row in selected])), "p90": float(np.percentile([float(row["mean_abs_point_line_distance_px"]) for row in selected], 90)), "max": float(max(float(row["mean_abs_point_line_distance_px"]) for row in selected))},
        "true_line_frames_all_four": sum(bool(row["true_line_all_four_within_12px"]) for row in frames),
        "true_line_median_max_corner_error_px": float(np.median(true_maxima)),
        "render_indices": list(RENDER_INDICES),
    }
    _write_csv(OUT / "per_frame.csv", frames)
    _write_csv(OUT / "selected_line_distances.csv", selected)
    _write_csv(OUT / "g210b_label_free_target_scores.csv", label_free_scores)
    _write_csv(OUT / "g210b_oracle_target_scores.csv", oracle_scores)
    _write_csv(OUT / "true_line_target_scores.csv", true_scores)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(f"label_free={summary['g210b_label_free_frames_all_four']}/17 oracle={summary['g210b_oracle_frames_all_four']}/17 true_line={summary['true_line_frames_all_four']}/17")
    return summary


if __name__ == "__main__":
    run()
