"""Focused tests for the private broadcast tracking evidence renderer."""
from __future__ import annotations

import cv2
import pandas as pd

from scripts.platformkit.overlay_render import render_overlay


def _video(path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (160, 90))
    assert writer.isOpened()
    for frame in range(60):
        image = cv2.UMat(90, 160, cv2.CV_8UC3).get()
        image[:] = (frame, 20, 40)
        writer.write(image)
    writer.release()


def _rows(boxes: bool) -> list[dict[str, object]]:
    rows = []
    for frame in range(0, 60, 3):
        row = {"frame": frame, "track_id": 7, "cls": "player", "x": 30, "y": 20}
        if boxes:
            row.update({"bbox_x1": 20, "bbox_y1": 20, "bbox_x2": 60, "bbox_y2": 75})
        rows.append(row)
    return rows


def test_renders_synchronized_bboxes(tmp_path) -> None:
    video, csv_path, output = tmp_path / "source.mp4", tmp_path / "tracking.csv", tmp_path / "evidence.mp4"
    _video(video)
    pd.DataFrame(_rows(boxes=True)).to_csv(csv_path, index=False)
    assert render_overlay(video, csv_path, "basketball", output, max_seconds=2) == 60
    capture = cv2.VideoCapture(str(output))
    try:
        assert output.exists()
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 60
    finally:
        capture.release()


def test_missing_bboxes_is_graceful(tmp_path) -> None:
    video, csv_path, output = tmp_path / "source.mp4", tmp_path / "tracking.csv", tmp_path / "evidence.mp4"
    _video(video)
    pd.DataFrame(_rows(boxes=False)).to_csv(csv_path, index=False)
    assert render_overlay(video, csv_path, "basketball", output, max_seconds=2) == 60
    assert output.exists()
