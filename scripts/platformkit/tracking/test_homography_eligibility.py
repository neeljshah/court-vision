"""Focused tests for frame-level court-calibration diagnostics."""
from __future__ import annotations

import cv2
import numpy as np

from domains.tennis.tracking.test_adapter import COURT, _court_image
from scripts.platformkit.tracking.homography_eligibility import LineConfig, PropagationGate, _corners, eligibility_summary


def test_court_frame_is_solved_with_feature_counts() -> None:
    homography, result = _corners(_court_image(), LineConfig())
    assert homography is not None
    assert result.status == "solved"
    assert result.horizontal_lines >= 2 and result.vertical_lines >= 2


def test_blank_frame_is_non_court_not_a_solver_failure() -> None:
    homography, result = _corners(np.zeros((720, 1280, 3), dtype=np.uint8), LineConfig())
    assert homography is None
    assert result.cause == "non_court_scene"


def test_propagation_is_short_static_and_explicit() -> None:
    frame = _court_image()
    homography, _ = _corners(frame, LineConfig())
    assert homography is not None
    gate = PropagationGate(max_gap=1)
    assert gate.update(homography, frame)[1] == "solved"
    assert gate.update(None, frame)[1] == "propagated"
    assert gate.update(None, frame)[1] == "unavailable"


def test_skip_non_court_changes_denominator_not_eligibility_count() -> None:
    report = {"frame_diagnostics": [{"status": "solved", "cause": "solved"},
                                    {"status": "unavailable", "cause": "non_court_scene"}]}
    assert eligibility_summary(report, skip_non_court=True) == {"eligible_frames": 1,
        "denominator_frames": 1, "eligibility_pct": 100.0, "non_court_skipped": 1}
