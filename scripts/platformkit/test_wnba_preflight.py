"""Synthetic-video tests for the WNBA pre-tracking court gate."""
import json

import cv2
import numpy as np
import pytest

from scripts.platformkit import wnba_preflight


def _write_court_video(path, background, line):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 20, (240, 160))
    if not writer.isOpened():
        pytest.skip("MJPG VideoWriter unavailable")
    for _ in range(30):
        frame = np.full((160, 240, 3), background, dtype=np.uint8)
        cv2.line(frame, (20, 80), (220, 80), line, 5)
        cv2.line(frame, (120, 20), (120, 140), line, 5)
        writer.write(frame)
    writer.release()


def test_dark_and_light_court_video_verdicts(monkeypatch, tmp_path):
    monkeypatch.setattr(wnba_preflight, "REPORT_DIR", tmp_path / "reports")
    dark = tmp_path / "dark_game.avi"
    light = tmp_path / "light_game.avi"
    _write_court_video(dark, (8, 8, 8), (0, 255, 0))
    _write_court_video(light, (170, 195, 210), (255, 255, 255))

    dark_report = wnba_preflight.preflight(dark)
    light_report = wnba_preflight.preflight(light)

    assert dark_report["verdict"] == "DARK_COURT_FALLBACK"
    assert light_report["verdict"] == "OK"
    assert dark_report["line_coverage_pct"] > 0
    assert json.loads((tmp_path / "reports" / "light_game.json").read_text())["verdict"] == "OK"
