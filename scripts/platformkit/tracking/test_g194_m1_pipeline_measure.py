"""Focused unit tests for the G194 non-production measurement harness."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking.g194_m1_pipeline_measure import matrix_comparison, matrix_values


def test_matrix_serialization_and_elementwise_comparison() -> None:
    static = np.eye(3, dtype=np.float64)
    assert matrix_values(static) == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    same = matrix_comparison(static.copy(), static)
    assert same == {"available": True, "equal_elementwise": True, "max_abs_delta": 0.0}
    changed = static.copy()
    changed[0, 2] = 1.25
    assert matrix_comparison(changed, static)["equal_elementwise"] is False
    assert matrix_comparison(changed, static)["max_abs_delta"] == 1.25
