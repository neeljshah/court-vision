"""Focused contract tests for TransNetV2 baseball shot-boundary inference.

Run: python -m pytest domains/baseball/tracking/test_transnet.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.baseball.tracking.transnet import (
    TransNetV2BoundaryDetector,
    TransNetV2UnavailableError,
    _padded_windows,
    _to_model_frames,
)


def test_frame_conversion_is_rgb_and_model_sized() -> None:
    bgr = np.zeros((54, 96, 3), dtype=np.uint8)
    bgr[:, :, 0] = 17
    frames = _to_model_frames([bgr])

    assert frames.shape == (1, 27, 48, 3)
    assert frames[0, 0, 0].tolist() == [0, 0, 17]


def test_windows_cover_all_frames_with_upstream_context_shape() -> None:
    frames = np.zeros((73, 27, 48, 3), dtype=np.uint8)
    windows = _padded_windows(frames)

    assert len(windows) == 2
    assert all(window.shape == (100, 27, 48, 3) for window in windows)


def test_missing_model_is_not_silently_replaced_by_histogram(tmp_path) -> None:
    detector = TransNetV2BoundaryDetector(tmp_path / "missing")
    frame = np.zeros((36, 64, 3), dtype=np.uint8)

    with pytest.raises(TransNetV2UnavailableError, match="directory is missing"):
        detector.boundaries([frame])


def test_rejects_invalid_threshold(tmp_path) -> None:
    with pytest.raises(ValueError, match="strictly"):
        TransNetV2BoundaryDetector(tmp_path, threshold=1.0)


def test_boundary_runs_are_not_counted_as_multiple_cuts(monkeypatch, tmp_path) -> None:
    detector = TransNetV2BoundaryDetector(tmp_path, threshold=0.5)
    monkeypatch.setattr(detector, "_predict_frames",
                        lambda frames: np.array([0.1, 0.7, 0.9, 0.2, 0.8]))
    frame = np.zeros((36, 64, 3), dtype=np.uint8)

    assert detector.boundaries([frame] * 5).tolist() == [1, 4]
