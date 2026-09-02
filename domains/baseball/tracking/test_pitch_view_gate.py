"""Per-file tests for the first-versioned baseball pitch-view gate.

Run: python -m pytest domains/baseball/tracking/test_pitch_view_gate.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from domains.baseball.tracking.pitch_view_gate import classify_pitch_view


def test_dominant_green_mode_accepts_and_rejects_constructed_frames() -> None:
    green = np.full((100, 160, 3), (45, 130, 45), dtype=np.uint8)
    gray = np.full((100, 160, 3), 128, dtype=np.uint8)

    accepted = classify_pitch_view(green)
    rejected = classify_pitch_view(gray)

    assert accepted.is_pitch_view
    assert accepted.score == 1.0
    assert not rejected.is_pitch_view
    assert rejected.score == 0.0


def test_unknown_mode_is_rejected_explicitly() -> None:
    frame = np.zeros((20, 20, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="unknown pitch-view gate mode"):
        classify_pitch_view(frame, "unknown")  # type: ignore[arg-type]
