"""Additive G305 registration evidence around the unchanged tracking harness."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd

from scripts.platformkit.tracking_harness import (
    DEFAULT_CONFIG_VERSION,
    CONFIG_VERSIONS,
    QualityReport,
    evaluate,
)

_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_PATHS = {
    "harness_sha256": _ROOT / "scripts/platformkit/tracking_harness.py",
    "schema_sha256": _ROOT / "scripts/platformkit/tracking_schema.py",
    "liveness_sha256": _ROOT / "scripts/platformkit/liveness_metrics.py",
    "producer_sha256": Path(__file__).resolve(),
}
_AXIS_SWAP = ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
Q_TIMES_R_CONDITION = "q * r >= 0.60"
CONSTRUCT_CASES = (
    "near_left_corner",
    "near_right_corner",
    "far_left_corner",
    "far_right_corner",
    "asymmetric_interior_point",
    "original_harness_run",
    "reflected_harness_run",
    "worked_additive_record",
)


def sha256_lf(path: Path) -> str:
    """Return the SHA-256 seal after normalizing line endings to LF."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(path: Path) -> str:
    """Return the SHA-256 identity of the source bytes without normalization."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    """Return the four raw code-identity hashes carried by each additive record."""
    return {name: sha256_bytes(path) for name, path in _SOURCE_PATHS.items()}


def source_hashes_lf() -> dict[str, str]:
    """Return the four LF-normalized seals reported in the evidence memo."""
    return {name: sha256_lf(path) for name, path in _SOURCE_PATHS.items()}


def geometry_to_harness_point(point: Sequence[float]) -> tuple[float, float]:
    """Map geometry `(width_x, length_y)` feet to harness `(length_x, width_y)`."""
    return float(point[1]), float(point[0])


def harness_to_geometry_point(point: Sequence[float]) -> tuple[float, float]:
    """Map harness `(length_x, width_y)` feet to geometry `(width_x, length_y)`."""
    return float(point[1]), float(point[0])


def _swap_homography_axes(matrix: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise ValueError("homography must be a finite 3x3 matrix")
    result = tuple(tuple(float(value) for value in row) for row in matrix)
    if not all(math.isfinite(value) for row in result for value in row):
        raise ValueError("homography must be finite")
    return tuple(tuple(sum(_AXIS_SWAP[row][idx] * result[idx][col] for idx in range(3))
                       for col in range(3)) for row in range(3))


def geometry_to_harness_homography(matrix: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Left-compose a geometry-output homography with the named axis swap."""
    return _swap_homography_axes(matrix)


def harness_to_geometry_homography(matrix: Sequence[Sequence[float]]) -> tuple[tuple[float, ...], ...]:
    """Left-compose a harness-output homography with the named axis swap."""
    return _swap_homography_axes(matrix)


def canonical_passing_table() -> pd.DataFrame:
    """Construct the fixed 30-frame canonical table for the reflection check."""
    rows: list[dict[str, object]] = []
    for frame in range(30):
        for track_id in range(6):
            rows.append({"frame": frame, "timestamp": frame / 25.0, "track_id": track_id,
                         "cls": "player", "x": 10.0 + track_id * 5.0 + frame * 0.02,
                         "y": 10.0 + track_id * 3.0, "attempted_frames": 30,
                         "coordinate_space": "court_feet"})
        rows.append({"frame": frame, "timestamp": frame / 25.0, "track_id": 99,
                     "cls": "ball", "x": 47.0, "y": 25.0, "attempted_frames": 30,
                     "coordinate_space": "court_feet"})
    return pd.DataFrame(rows)


def reflect_harness_table(table: pd.DataFrame) -> pd.DataFrame:
    """Reflect a harness table through `x' = 94 - x` without changing other fields."""
    reflected = table.copy(deep=True)
    reflected.loc[:, "x"] = 94.0 - reflected["x"]
    return reflected


def attempted_frame_manifest(table: pd.DataFrame) -> dict[str, object]:
    """Seal every attempted synthetic frame before either harness evaluation runs."""
    frames = [int(frame) for frame in sorted(table["frame"].unique())]
    payload = {"frame_ids": frames, "denominator": "pre_inference_attempted_frames"}
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("ascii")
    return {"payload": payload, "sha256": hashlib.sha256(encoded).hexdigest()}


def registration_passed(evidence: Mapping[str, object]) -> bool | None:
    """Evaluate only sealed E1 registration evidence; absent packets remain null."""
    if not evidence.get("sealed_g304_packet_available", False):
        return None
    errors = evidence.get("held_out_errors_px")
    per_frame = evidence.get("uncensored_per_frame_errors_px")
    if not isinstance(errors, Sequence) or isinstance(errors, (str, bytes)) or not errors:
        return False
    try:
        values = [float(value) for value in errors]
        per_frame_values = [float(value) for value in per_frame]  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    if values != per_frame_values or not all(math.isfinite(value) for value in values):
        return False
    ordered = sorted(values)
    index = (len(ordered) - 1) * 0.90
    lower, upper = math.floor(index), math.ceil(index)
    p90 = ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)
    required = ("correct_shot_end_orientation", "court_end_identified", "homography_finite",
                "rank_finite", "rank_observable")
    return (evidence.get("fixed_correspondence_count") == 6 and
            all(evidence.get(name) is True for name in required) and p90 <= 12.0 and
            max(values) <= 24.0)


def additive_record(report: QualityReport, mode: Mapping[str, object],
                    registration_evidence: Mapping[str, object], q: float | None = None,
                    r: float | None = None) -> dict[str, object]:
    """Emit additive fields while retaining the original harness record exactly."""
    original_json = report.to_json()
    original_record = json.loads(original_json)
    threshold = CONFIG_VERSIONS[report.config_version][report.sport]["ball_valid_min"]
    ball_value = original_record["ball_valid_pct"]
    q_times_r = None if q is None or r is None else q * r
    return {
        "harness_verdict_json": original_json,
        "harness_verdict_record": original_record,
        "registration_passed": registration_passed(registration_evidence),
        "player_tracking_passed": bool(report.passed),
        "ball_tracking_passed": bool(report.ball_valid_applicable and ball_value is not None and
                                     ball_value >= threshold),
        "q": q,
        "r": r,
        "q_times_r": q_times_r,
        "q_times_r_necessary_condition": Q_TIMES_R_CONDITION,
        "hashes": source_hashes(),
        "lf_normalized_hashes": source_hashes_lf(),
        "mode": dict(mode),
        "registration_evidence": dict(registration_evidence),
    }


def run_construct() -> tuple[QualityReport, QualityReport, dict[str, object]]:
    """Run the two harness cases and build the sole synthetic additive record."""
    original_table = canonical_passing_table()
    manifest = attempted_frame_manifest(original_table)
    original = evaluate(original_table, "basketball", DEFAULT_CONFIG_VERSION, attempted_frames=30)
    reflected = evaluate(reflect_harness_table(original_table), "basketball", DEFAULT_CONFIG_VERSION,
                         attempted_frames=30)
    mode = {"execution": "offline", "manual_inputs": False,
            "court_convention": "harness_x_94_y_50_ft",
            "camera_shot_eligibility": "not_measured_synthetic_construct",
            "attempted_frame_manifest": manifest,
            "attempted_frame_denominator": "all 30 pre-inference attempted frames"}
    evidence = {"sealed_g304_packet_available": False,
                "status": "unmeasured_no_sealed_g304_packet"}
    return original, reflected, additive_record(original, mode, evidence)


def write_construct_evidence(destination: Path) -> tuple[Path, Path, Path]:
    """Write the original, reflected, and additive JSON evidence records."""
    original, reflected, record = run_construct()
    destination.mkdir(parents=True, exist_ok=True)
    paths = (destination / "g305_original_harness_verdict_2026-09-07.json",
             destination / "g305_reflected_harness_verdict_2026-09-07.json",
             destination / "g305_additive_registration_record_2026-09-07.json")
    paths[0].write_text(original.to_json() + "\n", encoding="utf-8", newline="\n")
    paths[1].write_text(reflected.to_json() + "\n", encoding="utf-8", newline="\n")
    paths[2].write_text(json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
                        encoding="utf-8", newline="\n")
    return paths
