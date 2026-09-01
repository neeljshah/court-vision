"""Regression test for the tennis line-correspondence solver."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SPEC = importlib.util.spec_from_file_location(
    "tennis_anchor_ab", Path(__file__).with_name("tennis_resolution_anchor_ab.py")
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_line_homography_recovers_exact_projective_mapping() -> None:
    homography = np.array(((0.08, -0.01, -30.0), (0.01, 0.09, -20.0),
                           (0.00002, -0.00003, 1.0)))
    court = [np.array((0.0, 1.0, -value)) for value in MODULE.COURT_ACROSS]
    court += [np.array((1.0, 0.0, -value)) for value in MODULE.COURT_DEPTH]
    inverse_transpose = np.linalg.inv(homography).T
    recovered = MODULE.line_homography(court, [inverse_transpose @ line for line in court])
    assert recovered is not None
    assert np.allclose(recovered, homography, atol=1e-9)
