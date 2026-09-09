"""Additive, non-scorable image-pixel tracking gate evaluation."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from scripts.platformkit.liveness_metrics import compute_liveness_metrics, thresholds_for
from scripts.platformkit.tracking_schema import IMAGE_PX_CONTAINMENT_MIN
from scripts.platformkit.tracking_harness import MIN_FRAMES_FOR_METRICS, SPORTS

IMAGE_SPACE = "image_px"
CONTAINMENT_MIN = IMAGE_PX_CONTAINMENT_MIN
GATE_ORDER = (
    "coordinate_contract", "insufficient_data", "duplicate_frame_identity",
    "coverage_attempted_frames", "median_track_len", "oob", "jump_max",
    "attempted_frames", "ball_valid_attempted_frames", "liveness_frozen",
    "zero_step_share", "median_step_distance", "distinct_position_ratio",
    "stationary_track_share", "jump_p95", "ball_detected_share",
    "g325_wholly_off_frame", "any_gate",
)
COURT_ONLY = {"coordinate_contract", "oob"}


def _row(gate: str, status: str, reason: str, measurement: float | int | None,
         threshold: float | int | None, unit: str) -> dict[str, Any]:
    """Return one additive status row with the non-scorable image stamp."""
    return {
        "gate": gate,
        "status": status,
        "reason": reason,
        "measurement": measurement,
        "threshold": threshold,
        "unit": unit,
        "scorable": False,
        "coordinate_space": IMAGE_SPACE,
    }


def _check(value: float, threshold: float, direction: str) -> str:
    failed = value > threshold if direction == "max" else value < threshold
    return "REJECT" if failed else "PASS"


def _image_rows(df: pd.DataFrame) -> pd.DataFrame:
    required = {"frame", "track_id", "x", "y", "cls", "coordinate_space"}
    missing = sorted(required.difference(df.columns))
    if missing:
        raise ValueError("image-space table missing columns: {}".format(", ".join(missing)))
    declared = set(df["coordinate_space"].dropna().astype(str))
    if declared != {IMAGE_SPACE}:
        raise ValueError("evaluate_image_space requires only coordinate_space=image_px")
    return df.copy(deep=True)


def _steps(players: pd.DataFrame) -> pd.Series:
    ordered = players.sort_values(["track_id", "frame"])
    dx = ordered.groupby("track_id")["x"].diff()
    dy = ordered.groupby("track_id")["y"].diff()
    return (dx.pow(2) + dy.pow(2)).pow(0.5).dropna()


def _containment(frame: pd.DataFrame, width: float, height: float) -> float:
    numeric = frame[["x", "y"]].apply(pd.to_numeric, errors="coerce")
    inside = (numeric["x"].between(0, width - 1) & numeric["y"].between(0, height - 1))
    return float(inside.sum() / len(frame)) if len(frame) else 0.0


def _any_gate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    statuses = [row["status"] for row in rows if row["gate"] not in COURT_ONLY]
    if "REJECT" in statuses:
        return _row("any_gate", "REJECT", "one or more image gates rejected", None, None, "derived")
    if "PASS" in statuses:
        return _row("any_gate", "PASS", "all thresholded image gates passed", None, None, "derived")
    return _row("any_gate", "NOT_APPLICABLE", "no image gate reached", None, None, "derived")


def evaluate_image_space(df: pd.DataFrame, sport: str, frame_width: float | None,
                         frame_height: float | None,
                         frame_size_source: str = "decoded") -> list[dict[str, Any]]:
    """Evaluate image-pixel health gates without certifying court coordinates.

    The return contract is intentionally independent of ``evaluate()``: each row
    is stamped non-scorable, and court geometry gates remain not applicable.
    """
    if sport not in SPORTS:
        raise ValueError("unknown sport {}".format(sport))
    has_sidecar_frame_size = frame_size_source in {"decoded", "sidecar"}
    if has_sidecar_frame_size:
        if frame_width is None or frame_height is None:
            raise ValueError("decoded frame size requires width and height")
        width, height = float(frame_width), float(frame_height)
        if width <= 0 or height <= 0:
            raise ValueError("frame_width and frame_height must be positive")
    else:
        width = height = 0.0
    frame = _image_rows(df)
    for column in ("frame", "x", "y"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame[["frame", "x", "y"]].isna().any().any():
        raise ValueError("image-space frame, x, and y must be numeric")

    cfg = SPORTS[sport]
    players = frame.loc[frame["cls"].eq("player")].copy()
    n_frames = int(frame["frame"].nunique())
    rows: list[dict[str, Any]] = [
        _row("coordinate_contract", "NOT_APPLICABLE", "court_space_required", None, None, "none"),
        _row("oob", "NOT_APPLICABLE", "court_space_required", None, None, "none"),
    ]
    rows.append(_row("insufficient_data", "REJECT" if n_frames < MIN_FRAMES_FOR_METRICS else "PASS",
                     "fewer than {} frames".format(MIN_FRAMES_FOR_METRICS) if n_frames < MIN_FRAMES_FOR_METRICS
                     else "at least {} frames".format(MIN_FRAMES_FOR_METRICS), n_frames,
                     MIN_FRAMES_FOR_METRICS, "frames"))

    duplicate_count = int(frame.duplicated(["frame", "track_id"]).sum())
    rows.append(_row("duplicate_frame_identity", "REJECT" if duplicate_count else "PASS",
                     "duplicate frame-track rows" if duplicate_count else "no duplicate frame-track rows",
                     duplicate_count, 0, "rows"))
    per_frame = players.groupby("frame")["track_id"].nunique()
    density = float((per_frame >= cfg["min_players"]).sum() / n_frames) if n_frames else 0.0
    rows.append(_row("coverage_attempted_frames", "MEASURED_NO_BAR",
                     "emitted-frame density; attempted-frame denominator unavailable", density, None,
                     "share_of_emitted_frames"))
    lengths = players.groupby("track_id")["frame"].count()
    median_length = float(lengths.median()) if not lengths.empty else 0.0
    rows.append(_row("median_track_len", _check(median_length, cfg["min_median_track_len"], "min"),
                     "landed minimum track length", median_length, cfg["min_median_track_len"], "frames"))

    steps = _steps(players)
    jump_p95 = float(steps.quantile(0.95)) if not steps.empty else 0.0
    rows.append(_row("jump_max", "MEASURED_NO_BAR",
                     "G48 has no landed pixel-rate threshold", jump_p95, None, "px_per_frame_p95"))
    rows.append(_row("jump_p95", "MEASURED_NO_BAR",
                     "G48 has no landed pixel-rate threshold", jump_p95, None, "px_per_frame_p95"))
    rows.append(_row("attempted_frames", "MEASURED_NO_BAR",
                     "attempted-frame metadata is outside image-space inputs", None, None, "frames"))

    player_frames = set(players["frame"])
    ball_frames = set(frame.loc[frame["cls"].eq("ball"), "frame"])
    ball_overlap = float(len(player_frames & ball_frames) / n_frames) if n_frames else 0.0
    ball_status = _check(ball_overlap, cfg["ball_valid_min"], "min")
    for gate in ("ball_valid_attempted_frames", "ball_detected_share"):
        rows.append(_row(gate, ball_status, "landed ball-row presence minimum", ball_overlap,
                         cfg["ball_valid_min"], "share_of_emitted_frames"))

    liveness = compute_liveness_metrics(frame, sport)
    rows.append(_row("liveness_frozen", "REJECT" if liveness.verdict == "FROZEN" else "PASS",
                     "liveness verdict {}".format(liveness.verdict), None, None, "verdict"))
    liveness_values = {
        "zero_step_share": liveness.zero_step_share,
        "median_step_distance": liveness.median_step_distance,
        "distinct_position_ratio": liveness.distinct_position_ratio,
        "stationary_track_share": liveness.stationary_track_share,
    }
    directions = {"zero_step_share": "max", "median_step_distance": "max",
                  "distinct_position_ratio": "min", "stationary_track_share": "max"}
    for gate, value in liveness_values.items():
        threshold = thresholds_for(sport)[gate + ("_max" if directions[gate] == "max" else "_min")]
        if threshold is None:
            rows.append(_row(gate, "MEASURED_NO_BAR", "sport has no landed liveness threshold",
                             value, None, "image_px"))
        else:
            rows.append(_row(gate, _check(value, threshold, directions[gate]),
                             "landed liveness threshold", value, threshold, "image_px"))

    if has_sidecar_frame_size:
        containment = _containment(frame, width, height)
        rows.append(_row("g325_wholly_off_frame", _check(containment, CONTAINMENT_MIN, "min"),
                         "landed image point containment minimum", containment, CONTAINMENT_MIN,
                         "share_inside_decoded_frame"))
    else:
        rows.append(_row("g325_wholly_off_frame", "NOT_APPLICABLE", "frame_size_absent",
                         None, CONTAINMENT_MIN, "share_inside_decoded_frame"))
    rows.append(_any_gate(rows))
    return sorted(rows, key=lambda row: GATE_ORDER.index(row["gate"]))
