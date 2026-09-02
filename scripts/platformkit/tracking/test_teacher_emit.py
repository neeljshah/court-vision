"""Focused checks for baseball teacher-sidecar persistence."""
from __future__ import annotations

import json
import math

import pytest

from scripts.platformkit.tracking.teacher_emit import write_teacher_meta


def _metadata(target=(10.0, 20.0, 0.8), scale=40.0):
    return {
        "frames_processed": 20, "pitch_view_frames": 10, "pitch_segments": 1,
        "coordinate_calibration_reason": "measured reason",
        "command_events": [{"target_px": target, "target_confidence": target[2]
                            if target else None, "scale_px_per_ft": scale}],
        "calibrations": [{"segment_id": 1, "pixels_per_foot": scale,
                            "mound_centerline": 640.0}],
        "raw_calibrations": [], "command_series": None,
    }


def test_target_round_trips(tmp_path) -> None:
    path = write_teacher_meta(_metadata(), "game", "baseball", tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert set(saved) == {
        "sport", "game_id", "adapter_module", "frames_processed",
        "pitch_view_frames", "pitch_segments", "coordinate_space", "calibration",
        "coordinate_calibration_reason", "segments", "depth",
    }
    segment = saved["segments"][0]
    assert set(segment) == {
        "segment_id", "target_px", "target_confidence", "scale_px_per_ft",
        "scale_status", "mound_centerline",
    }
    assert segment["scale_status"] is None  # absent upstream, carried as unknown
    assert segment["target_px"] == [10.0, 20.0]
    assert segment["target_confidence"] == 0.8


def test_missing_target_writes_null_without_crashing(tmp_path) -> None:
    path = write_teacher_meta(_metadata(target=None), "game", "baseball", tmp_path)
    segment = json.loads(path.read_text(encoding="utf-8"))["segments"][0]
    assert segment["target_px"] is None
    assert segment["target_confidence"] is None


def test_calibration_reason_survives_verbatim(tmp_path) -> None:
    metadata = _metadata()
    metadata["coordinate_calibration_reason"] = "verbatim measured refusal"
    saved = json.loads(write_teacher_meta(metadata, "game", "baseball", tmp_path).read_text())
    assert saved["coordinate_calibration_reason"] == "verbatim measured refusal"


def test_nan_scale_raises_instead_of_serializing(tmp_path) -> None:
    with pytest.raises(ValueError):
        write_teacher_meta(_metadata(scale=math.nan), "game", "baseball", tmp_path)
