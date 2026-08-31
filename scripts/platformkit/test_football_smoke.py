"""Synthetic test for the bounded football tracking smoke report."""
from __future__ import annotations

import json

import cv2

from domains.football.tracking.test_adapter import _field
from scripts.platformkit.football_smoke import run_smoke


def test_smoke_writes_required_report_fields(tmp_path) -> None:
    video = tmp_path / "field.avi"
    frame = _field()
    writer = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10, (720, 360))
    assert writer.isOpened()
    for _ in range(4):
        writer.write(frame)
    writer.release()
    boxes = [[90 + index * 20, 150, 100 + index * 20, 180] for index in range(14)]

    report = run_smoke(video, "fb_test", detector=lambda image: boxes, max_frames=4,
                       report_dir=tmp_path / "reports")

    saved = json.loads((tmp_path / "reports/fb_test_smoke.json").read_text(encoding="utf-8"))
    assert set(("n_presnap_frames", "n_player_rows", "homography_acceptance_rate")) <= saved.keys()
    assert saved == report
    assert report["n_presnap_frames"] == 3
    assert report["n_player_rows"] == 42
    assert report["homography_acceptance_rate"] > 0.0
