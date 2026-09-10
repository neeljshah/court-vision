"""Additive G370 teacher-admission row schema and validation."""
from __future__ import annotations

import json
from typing import Any, Mapping

POSITION_SOURCES = frozenset(("DETECTION", "PREDICTION", "HELD", "UNKNOWN"))
TASK_STATUSES = frozenset(("PASS", "FAIL", "ABSENT", "NOT_APPLICABLE"))
ADMISSION_STATUSES = frozenset(("ELIGIBLE", "PARTIAL", "UNVERIFIED"))

PROVENANCE_FIELDS = (
    "source_id", "source_uri", "requested_start_s", "requested_end_s",
    "source_sha256", "byte_size", "frame_sha256", "table_sha256",
    "source_identity_status", "alignment_error_native_frames",
    "deploy_manifest_sha256", "route_sha256", "weights_sha256",
)
CLOCK_IMAGE_FIELDS = (
    "game_id", "competition", "section_id", "frame_index", "pts", "timebase",
    "decoded_frame_count", "evaluated_tick_id", "evaluated_tick_verified",
    "width", "height", "crop_xywh", "pixel_transform_sha256", "split", "inclusion_probability",
)
CALIBRATION_FIELDS = (
    "court_presence_label", "court_presence_probability", "court_presence_model_sha256",
    "geometry_status", "orientation_status", "symmetry_class", "H_sha256",
    "template_sha256", "template_status", "validation_support_sha256", "residual_px",
    "uncertainty_m",
)
DECISION_FIELDS = (
    "gate_scores_m0", "gate_scores_m1", "gate_status_by_task", "task_mask",
    "reason_codes", "evidence_sha256s", "admission_spec_sha256", "admission_status",
    "scorable",
)
ARRAY_FIELDS = ("track_observations", "ball_observations")
ADMISSION_COLUMNS = (*PROVENANCE_FIELDS, *CLOCK_IMAGE_FIELDS, "ball_x2d_px", "ball_y2d_px",
                     *ARRAY_FIELDS, *CALIBRATION_FIELDS, *DECISION_FIELDS)
TRACK_FIELDS = (
    "track_id", "track_generation", "bbox_px", "xy_px", "position_source",
    "producer_branch_file_line", "attribution_evidence_sha256", "last_observed_pts",
    "age_s", "observed",
)
BALL_FIELDS = (*TRACK_FIELDS, "observed_box_px")


def new_admission_row(**values: Any) -> dict[str, Any]:
    """Create a complete nullable row without silently inventing evidence."""
    row = {field: None for field in ADMISSION_COLUMNS}
    row.update({"track_observations": [], "ball_observations": [], "gate_scores_m0": {},
                "gate_scores_m1": {}, "gate_status_by_task": {}, "task_mask": {},
                "reason_codes": [], "evidence_sha256s": {}, "scorable": False,
                "admission_status": "UNVERIFIED"})
    unknown = sorted(set(values).difference(ADMISSION_COLUMNS))
    if unknown:
        raise ValueError("unknown admission field(s): {}".format(", ".join(unknown)))
    row.update(values)
    return row


def position_observed(source: str) -> bool:
    """Only a detection provenance may be labelled as observed."""
    if source not in POSITION_SOURCES:
        raise ValueError("invalid position source {}".format(source))
    return source == "DETECTION"


def task_mask_for(statuses: Mapping[str, str], control_bars: Mapping[str, bool] | None = None,
                  plant_bars: Mapping[str, bool] | None = None) -> dict[str, bool]:
    """Enable only PASS tasks whose sealed control and plant bars are explicitly met."""
    bad = sorted(set(statuses.values()).difference(TASK_STATUSES))
    if bad:
        raise ValueError("invalid task status(es): {}".format(", ".join(bad)))
    controls, plants = control_bars or {}, plant_bars or {}
    return {task: status == "PASS" and controls.get(task) is True and plants.get(task) is True
            for task, status in statuses.items()}


def admission_status_for(statuses: Mapping[str, str], control_bars: Mapping[str, bool] | None = None,
                         plant_bars: Mapping[str, bool] | None = None) -> str:
    """Classify task readiness without treating ABSENT as a bad frame."""
    if not statuses:
        return "UNVERIFIED"
    masks = task_mask_for(statuses, control_bars, plant_bars)
    return "ELIGIBLE" if all(masks.values()) else "PARTIAL"


def _array(value: Any, field: str) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("{} must be a list of objects".format(field))
    return value


def _validate_observations(items: list[dict[str, Any]], fields: tuple[str, ...], name: str) -> None:
    for index, item in enumerate(items):
        missing = [field for field in fields if field not in item]
        if missing:
            raise ValueError("{}[{}] missing {}".format(name, index, ", ".join(missing)))
        source = item["position_source"]
        if source not in POSITION_SOURCES:
            raise ValueError("{}[{}] has invalid position source".format(name, index))
        if bool(item["observed"]) != position_observed(source):
            raise ValueError("{}[{}] labels {} as observed".format(name, index, source))


def validate_admission_row(row: Mapping[str, Any], control_bars: Mapping[str, bool] | None = None,
                           plant_bars: Mapping[str, bool] | None = None) -> None:
    """Validate the additive row contract, including no false observed labels."""
    missing = [field for field in ADMISSION_COLUMNS if field not in row]
    if missing:
        raise ValueError("admission row missing {}".format(", ".join(missing)))
    _validate_observations(_array(row["track_observations"], "track_observations"),
                           TRACK_FIELDS, "track_observations")
    _validate_observations(_array(row["ball_observations"], "ball_observations"),
                           BALL_FIELDS, "ball_observations")
    statuses = row["gate_status_by_task"]
    masks = row["task_mask"]
    if isinstance(statuses, str):
        statuses = json.loads(statuses)
    if isinstance(masks, str):
        masks = json.loads(masks)
    if not isinstance(statuses, dict) or not isinstance(masks, dict):
        raise ValueError("task status and task mask must be objects")
    expected = task_mask_for(statuses, control_bars, plant_bars)
    if masks != expected:
        raise ValueError("task mask does not independently match task statuses")
    if row["admission_status"] not in ADMISSION_STATUSES:
        raise ValueError("invalid admission status")
    if row["admission_status"] != admission_status_for(statuses, control_bars, plant_bars):
        raise ValueError("admission status does not match task statuses")
    if row["geometry_status"] == "IMAGE_ONLY" and bool(row["scorable"]):
        raise ValueError("image-only geometry cannot be scorable")


def canonicalize_row(row: Mapping[str, Any], control_bars: Mapping[str, bool] | None = None,
                     plant_bars: Mapping[str, bool] | None = None) -> dict[str, Any]:
    """Return a validated, JSON-serializable row with deterministic array values."""
    value = dict(row)
    for field in ARRAY_FIELDS:
        value[field] = _array(value[field], field)
    for field in ("gate_scores_m0", "gate_scores_m1", "gate_status_by_task", "task_mask",
                  "evidence_sha256s"):
        if isinstance(value[field], str):
            value[field] = json.loads(value[field])
    if isinstance(value["reason_codes"], str):
        value["reason_codes"] = json.loads(value["reason_codes"])
    validate_admission_row(value, control_bars, plant_bars)
    return value
