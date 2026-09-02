"""Regression coverage for the footage-cycle demo-render import.

Run: python -m pytest scripts/platformkit/test_footage_cycle_import.py -q
"""
from __future__ import annotations

import csv

import cv2

from scripts.platformkit import footage_cycle


def test_footage_cycle_render_path_accepts_three_csv_rows(tmp_path) -> None:
    csv_path = tmp_path / "tracking.csv"
    output_path = tmp_path / "demo.mp4"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=("frame", "track_id", "cls", "x", "y"))
        writer.writeheader()
        for frame in range(3):
            writer.writerow({"frame": frame, "track_id": "p1", "cls": "player", "x": 10 + frame, "y": 20})

    assert footage_cycle.render_csv(csv_path, "tennis", output_path, fps=30, max_seconds=1) == 3
    capture = cv2.VideoCapture(str(output_path))
    try:
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 3
    finally:
        capture.release()
