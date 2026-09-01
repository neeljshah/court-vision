"""Persist the declared baseball teacher metadata sidecar."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from domains.baseball.tracking.quality_probe import probe_quality


def _segment_rows(metadata: Mapping[str, object]) -> list[dict[str, object]]:
    events = metadata.get("command_events")
    calibrations = metadata.get("calibrations")
    event_rows = events if isinstance(events, list) else []
    calibration_rows = calibrations if isinstance(calibrations, list) else []
    by_segment: dict[object, Mapping[str, object]] = {}
    for row in calibration_rows:
        if isinstance(row, Mapping) and "segment_id" in row:
            by_segment.setdefault(row["segment_id"], row)
    rows: list[dict[str, object]] = []
    for index, event in enumerate(event_rows, start=1):
        source = event if isinstance(event, Mapping) else {}
        segment_id = source.get("segment_id", index)
        calibration = by_segment.get(segment_id, {})
        target = source.get("target_px")
        confident = (
            isinstance(target, (list, tuple)) and len(target) >= 2
            and source.get("target_confidence") is not None
        )
        rows.append({
            "segment_id": segment_id,
            "target_px": [target[0], target[1]] if confident else None,
            "target_confidence": source.get("target_confidence") if confident else None,
            "scale_px_per_ft": source.get("scale_px_per_ft",
                                            calibration.get("pixels_per_foot")),
            "mound_centerline": calibration.get("mound_centerline"),
        })
    return rows


def write_teacher_meta(metadata: Mapping[str, object], game_id: str, sport: str,
                       out_dir: str | Path) -> Path:
    """Write the minimal, declared teacher sidecar and return its path."""
    payload = {
        "sport": sport,
        "game_id": game_id,
        "adapter_module": "domains.baseball.tracking.adapter",
        "frames_processed": metadata.get("frames_processed", 0),
        "pitch_view_frames": metadata.get("pitch_view_frames", 0),
        "pitch_segments": metadata.get("pitch_segments", 0),
        "coordinate_space": "image_px",
        "calibration": "none",
        "coordinate_calibration_reason": metadata.get("coordinate_calibration_reason"),
        "segments": _segment_rows(metadata),
        "depth": probe_quality(metadata).as_dict(),
    }
    path = Path(out_dir) / "teacher_meta.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    return path
