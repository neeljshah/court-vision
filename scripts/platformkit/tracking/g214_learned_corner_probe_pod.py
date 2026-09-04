"""Run G214's M-LSD pod control with G205's frozen scorer."""
from __future__ import annotations

import csv
import json
import os
import sys
from itertools import combinations
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.tracking.g205_zero_shot_corner_probe import (
    RENDER_INDICES,
    TOLERANCE_PX,
    _read_targets,
    _render,
    _source_path,
    score_frame,
)


OUT_ENV = "G214_OUT"
SOURCE_ENV = "G214_MLSD_SOURCE"
DEFAULT_OUT = Path("docs/evidence/tracking/g214_learned_corner_probe_pod")
MLSD_CONFIG = {
    "model": "tflite_models/M-LSD_512_tiny_fp32.tflite",
    "input_size": 512,
    "score_threshold": 0.10,
    "distance_threshold": 20.0,
    "intersection_min_angle_degrees": 35.0,
    "support_extension_px": 0.0,
    "deduplicate_radius_px": 2.0,
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else ["audit_id", "rank", "x_px", "y_px"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _intersection(first: np.ndarray, second: np.ndarray) -> tuple[float, float] | None:
    first_start, first_end = first.reshape(2, 2)
    second_start, second_end = second.reshape(2, 2)
    first_vector = first_end - first_start
    second_vector = second_end - second_start
    first_length = float(np.linalg.norm(first_vector))
    second_length = float(np.linalg.norm(second_vector))
    if first_length == 0.0 or second_length == 0.0:
        return None
    alignment = abs(float(np.dot(first_vector, second_vector) / (first_length * second_length)))
    if alignment > float(np.cos(np.deg2rad(MLSD_CONFIG["intersection_min_angle_degrees"]))):
        return None
    matrix = np.array([[first_vector[0], -second_vector[0]], [first_vector[1], -second_vector[1]]])
    try:
        first_fraction, second_fraction = np.linalg.solve(matrix, second_start - first_start)
    except np.linalg.LinAlgError:
        return None
    extension = float(MLSD_CONFIG["support_extension_px"])
    if not (-extension / first_length <= first_fraction <= 1.0 + extension / first_length):
        return None
    if not (-extension / second_length <= second_fraction <= 1.0 + extension / second_length):
        return None
    point = first_start + first_fraction * first_vector
    return (float(point[0]), float(point[1]))


def intersections(segments: np.ndarray, width: int, height: int) -> list[tuple[float, float]]:
    """Convert fixed native-pixel line supports to generic point proposals."""
    proposals = [
        point
        for first, second in combinations(np.asarray(segments, dtype=float), 2)
        if (point := _intersection(first, second)) is not None
        and 0.0 <= point[0] < width
        and 0.0 <= point[1] < height
    ]
    kept: list[tuple[float, float]] = []
    for point in sorted(proposals):
        if all(
            float(np.hypot(point[0] - saved[0], point[1] - saved[1]))
            > MLSD_CONFIG["deduplicate_radius_px"]
            for saved in kept
        ):
            kept.append(point)
    return kept


def _propose(image: np.ndarray, source: Path) -> list[tuple[float, float]]:
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    import tensorflow as tf
    from utils import pred_lines

    model_path = source / str(MLSD_CONFIG["model"])
    interpreter = tf.lite.Interpreter(model_path=str(model_path))
    interpreter.allocate_tensors()
    segments = pred_lines(
        image,
        interpreter,
        interpreter.get_input_details(),
        interpreter.get_output_details(),
        input_shape=[int(MLSD_CONFIG["input_size"])] * 2,
        score_thr=float(MLSD_CONFIG["score_threshold"]),
        dist_thr=float(MLSD_CONFIG["distance_threshold"]),
    )
    height, width = image.shape[:2]
    return intersections(np.asarray(segments), width, height)


def run_mlsd(source: Path, out: Path) -> dict[str, Any]:
    """Measure one fixed M-LSD configuration on all G140 source frames."""
    if not (source / str(MLSD_CONFIG["model"])).is_file():
        raise FileNotFoundError(source / str(MLSD_CONFIG["model"]))
    renders = out / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    frames = _read_targets()
    target_rows: list[dict[str, Any]] = []
    proposal_rows: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    for index, audit_id in enumerate(sorted(frames)):
        targets = frames[audit_id]
        image = cv2.imread(str(_source_path(targets[0])))
        if image is None:
            raise FileNotFoundError(_source_path(targets[0]))
        height, width = image.shape[:2]
        if (width, height) != (int(targets[0]["image_width"]), int(targets[0]["image_height"])):
            raise ValueError(f"native dimension mismatch for {audit_id}")
        proposals = _propose(image, source)
        scored_targets, scored_proposals, all_four = score_frame(targets, proposals)
        target_rows.extend(scored_targets)
        proposal_rows.extend(scored_proposals)
        frame_rows.append({"candidate": "mlsd_control", "audit_id": audit_id, "image_width": width, "image_height": height, "proposals": len(proposals), "matched_roles": sum(bool(row["available"]) for row in scored_targets), "all_four_within_12px": all_four})
        if index in RENDER_INDICES:
            _render(image, targets, proposals, renders / f"mlsd_{index:02d}_{audit_id}.jpg")
    _write_csv(out / "mlsd_target_scores.csv", target_rows)
    _write_csv(out / "mlsd_proposal_scores.csv", proposal_rows)
    _write_csv(out / "mlsd_per_frame.csv", frame_rows)
    summary = {"candidate": "mlsd_control", "frames_all_four": sum(bool(row["all_four_within_12px"]) for row in frame_rows), "frames_total": len(frame_rows), "corner_recall": sum(bool(row["available"]) for row in target_rows), "corner_total": len(target_rows), "proposal_precision_hits": sum(bool(row["on_any_target"]) for row in proposal_rows), "proposal_total": len(proposal_rows), "proposals_per_frame": len(proposal_rows) / len(frame_rows), "tolerance_px": TOLERANCE_PX, "config": MLSD_CONFIG, "render_indices": list(RENDER_INDICES)}
    (out / "mlsd_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return summary


def main() -> None:
    source_value = os.environ.get(SOURCE_ENV)
    if not source_value:
        raise ValueError(f"set {SOURCE_ENV} to an official M-LSD checkout")
    summary = run_mlsd(Path(source_value).resolve(), Path(os.environ.get(OUT_ENV, DEFAULT_OUT)))
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
