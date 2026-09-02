"""Regression tests for baseball geometry field-precondition selection.

Run: python -m pytest domains/baseball/tracking/test_geometry.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from domains.baseball.tracking import geometry


def _pitch_view() -> np.ndarray:
    image = np.full((720, 1280, 3), (45, 130, 45), dtype=np.uint8)
    cv2.rectangle(image, (0, 300), (1280, 450), (70, 76, 120), -1)
    cv2.ellipse(image, (506, 604), (456, 55), 0, 0, 360, (70, 76, 120), -1)
    return image


def _legacy_default(frame: np.ndarray):
    if not geometry.dominant_green(geometry.center_crop(frame)):
        return None
    chord = geometry.mound_chord(frame, geometry.MIN_CHORD_FRACTION)
    if chord is None or not geometry.infield_band_present(frame, chord.row):
        return None
    mound = np.array((chord.center_x, float(chord.row)), dtype=np.float32)
    return geometry.PitchGeometry(mound, chord.width,
                                  chord.pixels_per_foot_lateral,
                                  chord.near_edge_occluded)


def test_default_mode_calls_dominant_green_and_matches_legacy_output(monkeypatch) -> None:
    frame = _pitch_view()
    expected = _legacy_default(frame)
    calls = []
    original = geometry.dominant_green

    def spy(crop: np.ndarray) -> bool:
        calls.append(crop.copy())
        return original(crop)

    monkeypatch.setattr(geometry, "dominant_green", spy)
    monkeypatch.setattr(
        geometry, "classify_pitch_view",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("default called opt-in gate")),
    )

    actual = geometry.detect_pitch_geometry(frame)

    assert len(calls) == 1
    assert np.array_equal(calls[0], geometry.center_crop(frame))
    assert actual is not None
    assert expected is not None
    assert actual.mound_chord_px == expected.mound_chord_px
    assert actual.pixels_per_foot == expected.pixels_per_foot
    assert actual.near_edge_occluded == expected.near_edge_occluded
    assert np.array_equal(actual.mound, expected.mound)
