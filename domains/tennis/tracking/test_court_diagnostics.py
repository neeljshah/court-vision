"""Tests for the observational tennis court-registration gate trace."""
from __future__ import annotations

import numpy as np

from domains.tennis.tracking.court_diagnostics import held_out_service_t_error, rejection_gate
from domains.tennis.tracking.test_adapter import _court_image


def test_gate_trace_accepts_the_same_synthetic_court_as_the_adapter() -> None:
    assert rejection_gate(_court_image()) == "accepted"
    assert held_out_service_t_error(_court_image()) is not None


def test_gate_trace_names_the_first_missing_line_rejection() -> None:
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert rejection_gate(image) == "no_hough_lines"
