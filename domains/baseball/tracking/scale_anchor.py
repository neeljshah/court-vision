"""Landmark-anchored, per-pitch scale stabilization for baseball tracking.

This module is intentionally offline and metadata-only.  It does not alter the
adapter or discard pitch-view frames: rejected raw scale observations are
recorded for diagnostics, while every previously retained calibration receives
its segment's fixed median scale.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil, floor
from typing import Any, Iterable, Mapping


SCALE_FIELDS = ("pixels_per_foot", "px_per_foot", "scale")
DEFAULT_RELATIVE_TOLERANCE = 0.15


@dataclass(frozen=True)
class ScaleAnchorReport:
    """Stability measurements for one metadata anchoring pass."""

    segments: int
    frames_accepted: int
    frames_rejected: int
    scale_p50_per_segment: dict[str, float]
    scale_jump_p95_before: float
    scale_jump_p95_after: float

    def as_dict(self) -> dict[str, object]:
        """Return the report in the specified JSON-ready shape."""
        return asdict(self)


def _scale_key(row: Mapping[str, Any]) -> str:
    for key in SCALE_FIELDS:
        if key in row:
            return key
    raise ValueError("calibration row is missing a scale field")


def _segment_key(row: Mapping[str, Any]) -> object:
    if "segment_id" not in row:
        raise ValueError("calibration row is missing segment_id")
    return row["segment_id"]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low, high = floor(position), ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _jump_p95(rows: Iterable[Mapping[str, Any]]) -> float:
    per_segment: dict[object, list[tuple[float, float]]] = {}
    for ordinal, row in enumerate(rows):
        scale = float(row[_scale_key(row)])
        if scale <= 0.0:
            raise ValueError("calibration scales must be positive")
        frame = float(row.get("frame", ordinal))
        per_segment.setdefault(_segment_key(row), []).append((frame, scale))
    jumps = []
    for values in per_segment.values():
        ordered = sorted(values)
        jumps.extend(abs(right[1] - left[1]) for left, right in zip(ordered, ordered[1:]))
    return _quantile(jumps, 0.95)


def anchor_calibrations(
    raw_calibrations: Iterable[Mapping[str, Any]],
    calibrations: Iterable[Mapping[str, Any]],
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
) -> tuple[list[dict[str, Any]], ScaleAnchorReport]:
    """Anchor retained calibrations at accepted raw-scale medians per segment.

    ``raw_calibrations`` supplies the scale observations and segment boundaries.
    ``calibrations`` supplies the frames already retained by the adapter.  The
    latter's frame membership is preserved, so anchoring cannot lower
    pitch-view coverage merely by dropping rows.
    """
    if not 0.0 <= relative_tolerance < 1.0:
        raise ValueError("relative_tolerance must be in [0, 1)")
    raw_rows = [dict(row) for row in raw_calibrations]
    retained_rows = [dict(row) for row in calibrations]
    if not raw_rows:
        raise ValueError("raw_calibrations must not be empty")

    values: dict[object, list[float]] = {}
    for row in raw_rows:
        scale = float(row[_scale_key(row)])
        if scale <= 0.0:
            raise ValueError("calibration scales must be positive")
        values.setdefault(_segment_key(row), []).append(scale)
    initial_medians = {segment: _median(scales) for segment, scales in values.items()}
    accepted_values: dict[object, list[float]] = {segment: [] for segment in values}
    for row in raw_rows:
        segment = _segment_key(row)
        scale = float(row[_scale_key(row)])
        if abs(scale - initial_medians[segment]) <= relative_tolerance * initial_medians[segment]:
            accepted_values[segment].append(scale)
    medians = {
        segment: _median(scales) if scales else initial_medians[segment]
        for segment, scales in accepted_values.items()
    }

    accepted_by_frame: dict[tuple[object, object], bool] = {}
    accepted = 0
    for ordinal, row in enumerate(raw_rows):
        segment = _segment_key(row)
        scale = float(row[_scale_key(row)])
        accepted_row = abs(scale - medians[segment]) <= relative_tolerance * medians[segment]
        frame = row.get("frame", ordinal)
        accepted_by_frame[(segment, frame)] = accepted_row
        accepted += int(accepted_row)

    anchored: list[dict[str, Any]] = []
    for ordinal, row in enumerate(retained_rows):
        segment = _segment_key(row)
        if segment not in medians:
            raise ValueError("retained calibration has no matching raw segment")
        output = dict(row)
        key = _scale_key(output)
        output[key] = medians[segment]
        output["scale_anchor_accepted"] = accepted_by_frame.get(
            (segment, output.get("frame", ordinal)), False
        )
        anchored.append(output)

    report = ScaleAnchorReport(
        segments=len(medians),
        frames_accepted=accepted,
        frames_rejected=len(raw_rows) - accepted,
        scale_p50_per_segment={str(segment): median for segment, median in medians.items()},
        scale_jump_p95_before=_jump_p95(raw_rows),
        scale_jump_p95_after=_jump_p95(anchored),
    )
    return anchored, report


def anchor_metadata(
    metadata: Mapping[str, Any], relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
) -> tuple[dict[str, Any], ScaleAnchorReport]:
    """Return adapter metadata with anchored calibrations and a stability report.

    The function preserves ``pitch_view_frames`` and ``pitch_segments`` exactly;
    these are the metadata counterparts of pitch-view coverage and
    ``pitches_detected`` in the baseball quality probe.
    """
    raw = metadata.get("raw_calibrations")
    retained = metadata.get("calibrations")
    if not isinstance(raw, list) or not isinstance(retained, list):
        raise ValueError("metadata requires list raw_calibrations and calibrations")
    anchored, report = anchor_calibrations(raw, retained, relative_tolerance)
    output = dict(metadata)
    output["calibrations"] = anchored
    output["scale_anchor_report"] = report.as_dict()
    return output, report
