"""Focused regression coverage for the Wave 7 diagnostic summaries."""
import numpy as np

from scripts.platformkit.tennis_wave7_falsifiers import _axis_summary


def test_axis_summary_reports_component_jitter_and_step_count() -> None:
    result = _axis_summary([np.array((1.0, 2.0)), np.array((2.0, 4.0)),
                            np.array((4.0, 5.0))])
    assert result["n_steps"] == 2
    assert result["sd_x_ft"] is not None
    assert result["sd_y_ft"] is not None


def test_axis_summary_requires_a_pair() -> None:
    assert _axis_summary([np.array((1.0, 2.0))])["n_steps"] == 0
