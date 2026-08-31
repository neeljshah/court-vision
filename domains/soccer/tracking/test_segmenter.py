"""Tests for soccer pitch-view segmentation.

Run: python -m pytest domains/soccer/tracking/test_segmenter.py -q
"""
from __future__ import annotations

import json

import cv2
import numpy as np

from domains.soccer.tracking.segmenter import segment_frames, segment_video, segments_to_json


def _pitch_frame() -> np.ndarray:
    return np.full((72, 128, 3), (40, 140, 40), dtype=np.uint8)


def _crowd_frame() -> np.ndarray:
    image = np.full((72, 128, 3), (50, 50, 120), dtype=np.uint8)
    image[:, ::4] = (180, 80, 60)
    return image


def test_segment_frames_finds_only_long_pitch_intervals_and_writes_json(tmp_path) -> None:
    frames = [_crowd_frame()] * 8 + [_pitch_frame()] * 65 + [_crowd_frame()] * 8 + [_pitch_frame()] * 59
    segments = segment_frames(frames)
    assert len(segments) == 1
    assert abs(segments[0].start_frame - 8) <= 1
    assert abs(segments[0].end_frame - 72) <= 1
    output = tmp_path / "segments.json"
    segments_to_json(segments, output)
    assert json.loads(output.read_text(encoding="utf-8")) == [{"start_frame": 8, "end_frame": 72}]


def test_segment_video_uses_stride_for_source_frame_boundaries(tmp_path) -> None:
    path = tmp_path / "views.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    for frame in [_crowd_frame()] * 8 + [_pitch_frame()] * 64 + [_crowd_frame()] * 8:
        writer.write(frame)
    writer.release()
    segments = segment_video(path, stride=2, min_frames=60)
    assert len(segments) == 1
    assert abs(segments[0].start_frame - 8) <= 2
    assert abs(segments[0].end_frame - 70) <= 2
