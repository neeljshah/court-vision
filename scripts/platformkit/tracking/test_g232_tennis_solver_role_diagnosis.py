import numpy as np

from scripts.platformkit.tracking.g232_tennis_solver_role_diagnosis import analyze_frame, render


def test_blank_frame_reports_unchanged_solver_rejection_and_renders() -> None:
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    result = analyze_frame(frame)
    assert result["accepted"] is False
    assert result["solver_gate"] == "no_hough_lines"
    assert [stage["contrast"] for stage in result["stages"]] == [45, 60]
    assert render(frame, result).shape == frame.shape
