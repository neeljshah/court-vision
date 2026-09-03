"""Read a non-circular attempted-frame denominator from a sibling ball table."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import isfinite
from pathlib import Path
from typing import Any

from scripts.platformkit.tracking_timebase import sampling_plan


@dataclass(frozen=True)
class PairedFrameAudit:
    """Frame-set facts needed to accept or reject a sibling ball table."""

    ball_table: Path | None
    attempted_frames: int | None
    reason: str | None
    tracking_frame_count: int
    ball_frame_count: int
    missing_tracking_frames: int
    tracking_modal_stride: int | None
    ball_modal_stride: int | None
    tracking_last_frame: int | None
    ball_last_frame: int | None


def _frame_value(value: str | None) -> int | None:
    """Return one integral frame identifier, rejecting blank and fractional values."""
    if value is None or not value.strip():
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    return int(number)


def _read_frame_values(path: Path, require_detected: bool = False) -> tuple[set[int] | None, int, str | None]:
    """Read the complete frame column without inspecting tracking payload fields."""
    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "frame" not in reader.fieldnames:
                return None, 0, "frame column unavailable"
            if require_detected and "detected" not in reader.fieldnames:
                return None, 0, "paired ball detection flag unavailable"
            values: set[int] = set()
            rows = 0
            for row in reader:
                rows += 1
                frame = _frame_value(row.get("frame"))
                if frame is None:
                    return None, rows, "invalid frame value"
                values.add(frame)
    except (OSError, csv.Error, UnicodeDecodeError):
        return None, 0, "ball table unreadable"
    return values, rows, None


def _modal_stride(frames: set[int]) -> int | None:
    """Return the unique modal positive spacing, without inferring a configured stride."""
    ordered = sorted(frames)
    if len(ordered) < 2:
        return None
    counts: dict[int, int] = {}
    for previous, current in zip(ordered, ordered[1:]):
        gap = current - previous
        counts[gap] = counts.get(gap, 0) + 1
    high = max(counts.values())
    modes = [gap for gap, count in counts.items() if count == high]
    return modes[0] if len(modes) == 1 else None


def audit_paired_ball_table(tracking_table_path: str | Path) -> PairedFrameAudit:
    """Audit the sibling ball table before treating its rows as attempts."""
    tracking_path = Path(tracking_table_path)
    ball_path = tracking_path.with_name("ball_tracking.csv")
    if not ball_path.is_file():
        return PairedFrameAudit(None, None, "paired ball table unavailable", 0, 0, 0,
                                None, None, None, None)
    tracking_frames, _, tracking_error = _read_frame_values(tracking_path)
    if tracking_error is not None or tracking_frames is None:
        return PairedFrameAudit(ball_path, None, tracking_error or "tracking table unreadable",
                                0, 0, 0, None, None, None, None)
    ball_frames, ball_rows, ball_error = _read_frame_values(ball_path, require_detected=True)
    if ball_error is not None or ball_frames is None:
        return PairedFrameAudit(ball_path, None, ball_error or "ball table unreadable",
                                len(tracking_frames), 0, 0, _modal_stride(tracking_frames),
                                None, max(tracking_frames, default=None), None)
    missing = tracking_frames - ball_frames
    tracking_stride = _modal_stride(tracking_frames)
    ball_stride = _modal_stride(ball_frames)
    if not tracking_frames:
        reason = "tracking frame set unavailable"
    elif not ball_frames:
        reason = "paired ball frame set empty"
    elif ball_rows != len(ball_frames):
        reason = "paired ball table has duplicate frame rows"
    elif missing:
        reason = "paired ball frames are not a superset"
    else:
        reason = None
    return PairedFrameAudit(
        ball_path, len(ball_frames) if reason is None else None, reason,
        len(tracking_frames), len(ball_frames), len(missing), tracking_stride, ball_stride,
        max(tracking_frames, default=None), max(ball_frames, default=None),
    )


def attempted_frames_from_paired_ball_table(tracking_table_path: str | Path) -> int | None:
    """Return a verified sibling ball-frame count, otherwise fail closed with ``None``."""
    return audit_paired_ball_table(tracking_table_path).attempted_frames


def _positive_integral(value: object) -> int | None:
    """Return one finite positive integer without rounding a source fact."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(number) or number <= 0 or not number.is_integer():
        return None
    return int(number)


def _positive_float(value: object) -> float | None:
    """Return one finite positive source rate without inventing a fallback."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number > 0 else None


def evaluated_frames_from_metadata(decoded_frames: object, source_fps: object,
                                   max_frames: object) -> int | None:
    """Count pre-tracking adapter evaluations from recorded source facts only."""
    decoded = _positive_integral(decoded_frames)
    fps = _positive_float(source_fps)
    cap = _positive_integral(max_frames)
    if decoded is None or fps is None or cap is None:
        return None
    stride = sampling_plan(fps).stride
    return len(range(0, min(decoded, stride * cap), stride))


def _sidecar_evaluated_frames(tracking_table_path: str | Path) -> int | None:
    """Read one self-validating pre-tracking evaluated-count sidecar."""
    path = Path(tracking_table_path).with_name("evaluated_frame_count.json")
    try:
        with path.open("r", encoding="utf-8") as handle:
            sidecar = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    if (not isinstance(sidecar, dict) or sidecar.get("schema_version") != "g206-v1"
            or sidecar.get("reason") is not None
            or sidecar.get("formula") != "ceil(decoded_frames / stride) when max_frames is null and start_frame is 0"):
        return None
    decoded = _positive_integral(sidecar.get("decoded_frames"))
    source_frames = _positive_integral(sidecar.get("source_frame_count"))
    fps = _positive_float(sidecar.get("source_fps"))
    stride = _positive_integral(sidecar.get("stride"))
    cap_value = sidecar.get("max_frames")
    cap = None if cap_value is None else _positive_integral(cap_value)
    count = _positive_integral(sidecar.get("evaluated_frames"))
    if (decoded is None or source_frames != decoded or fps is None or stride is None
            or count is None or sidecar.get("start_frame") != 0
            or not isinstance(sidecar.get("source_path"), str)
            or not sidecar["source_path"] or _positive_integral(sidecar.get("source_size_bytes")) is None):
        return None
    if cap is not None:
        return None
    expected = (decoded + stride - 1) // stride
    return count if count == expected else None


def _stable_column_value(frame: Any, column: str) -> object | None:
    """Return a value only when every emitted row repeats one non-null fact."""
    if column not in frame or frame.empty or frame[column].isna().any():
        return None
    values = frame[column].unique()
    return values[0] if len(values) == 1 else None


def evaluated_frames_from_tracking_table(frame: Any,
                                         tracking_table_path: str | Path | None = None) -> int | None:
    """Derive direct-harness attempts from stable producer metadata, else ``None``."""
    from_columns = evaluated_frames_from_metadata(
        _stable_column_value(frame, "decoded_frames"),
        _stable_column_value(frame, "source_fps"),
        _stable_column_value(frame, "max_frames"),
    )
    if from_columns is not None:
        return from_columns
    return _sidecar_evaluated_frames(tracking_table_path) if tracking_table_path else None
