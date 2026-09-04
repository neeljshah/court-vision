"""Focused tests for the honest image-space basketball adapter.

Run: python -m pytest domains/basketball/tracking/test_adapter.py -q
"""
import cv2
import numpy as np
import pandas as pd
import pytest

from domains.basketball.tracking.adapter import (
    SCHEMA,
    BallTrackingUnavailableError,
    BasketballAdapter,
    CalibrationUnavailableError,
)
from scripts.platformkit.tracking_harness import evaluate


def _video(path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    for _ in range(2):
        writer.write(np.zeros((72, 128, 3), dtype=np.uint8))
    writer.release()


def test_image_space_detections_use_bottom_centres_and_stable_ids():
    adapter = BasketballAdapter(detector=lambda frame: [[10, 20, 30, 60], [50, 5, 70, 45]])

    first = adapter.detect_players_image_space(np.zeros((72, 128, 3), dtype=np.uint8))
    second = adapter.detect_players_image_space(np.zeros((72, 128, 3), dtype=np.uint8))

    assert [item[0] for item in first] == [1, 2]
    assert [item[0] for item in second] == [1, 2]
    assert np.allclose(first[0][1], (20.0, 60.0))


def test_process_video_defaults_to_complete_honest_image_schema(tmp_path):
    path = tmp_path / "basketball.avi"
    _video(path)
    adapter = BasketballAdapter(detector=lambda frame: [[10, 20, 30, 60]])

    rows = adapter.process_video(path, player_only=True)

    assert tuple(rows.columns) == SCHEMA
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert set(rows["calibration_provenance"]) == {"unavailable"}
    assert set(rows["projection_status"]) == {"not_projected"}
    assert set(rows["projection_rejection_reason"]) == {"calibration_unavailable"}
    assert rows[["raw_projected_x_ft", "raw_projected_y_ft"]].isna().all().all()
    assert set(rows["source_height"]) == {72}
    assert set(rows["source_fps"]) == {25.0}


def test_adapter_refuses_ball_and_unjustified_court_output(tmp_path):
    path = tmp_path / "basketball.avi"
    _video(path)
    adapter = BasketballAdapter(detector=lambda frame: [])

    with pytest.raises(BallTrackingUnavailableError):
        adapter.process_video(path)
    with pytest.raises(CalibrationUnavailableError):
        adapter.process_video(path, player_only=True, image_space=False)
    with pytest.raises(CalibrationUnavailableError):
        adapter.detect_players(np.zeros((2, 2, 3), dtype=np.uint8), np.eye(3))


def test_write_csv_preserves_full_canonical_schema(tmp_path):
    adapter = BasketballAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame([{column: None for column in SCHEMA}])
    output = tmp_path / "tracking_data.csv"

    adapter.write_csv(output)

    assert tuple(pd.read_csv(output).columns) == SCHEMA


def test_image_rows_are_scorable_and_honestly_fail_coordinate_contract(tmp_path):
    path = tmp_path / "basketball.avi"
    _video(path)
    rows = BasketballAdapter(detector=lambda frame: [[10, 20, 30, 60]]).process_video(
        path, player_only=True
    )

    report = evaluate(rows, "basketball")

    assert report.verdict == "FAIL"
    assert report.failures[0].startswith("coordinate_contract:")
