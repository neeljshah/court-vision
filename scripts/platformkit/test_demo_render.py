"""Focused tests for the rights-safe tracking demo renderer.

Run: python -m pytest scripts/platformkit/test_demo_render.py -q
"""
from __future__ import annotations

import cv2
import pandas as pd

from scripts.platformkit.demo_render import render_csv


def _tracking_rows(include_ball: bool = True) -> list[dict[str, object]]:
    rows = []
    for frame in range(100):
        for track_id in range(3):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player", "x": 15 + track_id * 15 + frame * 0.1, "y": 15 + track_id * 8, "game_id": "synthetic"})
        if include_ball:
            rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 47, "y": 25, "game_id": "synthetic"})
    return rows


def test_renders_all_present_tracking_frames(tmp_path) -> None:
    csv_path = tmp_path / "tracking.csv"
    mp4_path = tmp_path / "demo.mp4"
    pd.DataFrame(_tracking_rows()).to_csv(csv_path, index=False)

    assert render_csv(csv_path, "basketball", mp4_path, fps=30, max_seconds=20) == 100
    capture = cv2.VideoCapture(str(mp4_path))
    try:
        assert mp4_path.exists()
        assert int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) == 100
    finally:
        capture.release()


def test_missing_ball_rows_do_not_raise(tmp_path) -> None:
    csv_path = tmp_path / "no_ball.csv"
    mp4_path = tmp_path / "no_ball.mp4"
    pd.DataFrame(_tracking_rows(include_ball=False)).to_csv(csv_path, index=False)

    assert render_csv(csv_path, "basketball", mp4_path) == 100
    assert mp4_path.exists()


def test_sparse_frame_numbers_render_only_present_frames(tmp_path) -> None:
    csv_path = tmp_path / "sparse.csv"
    mp4_path = tmp_path / "sparse.mp4"
    rows = _tracking_rows()
    pd.DataFrame(rows)[lambda frame: frame["frame"] % 2 == 0].to_csv(csv_path, index=False)

    assert render_csv(csv_path, "basketball", mp4_path) == 50
