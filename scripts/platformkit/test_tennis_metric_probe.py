"""Synthetic tests for the tennis metric probe.

Run: python -m pytest scripts/platformkit/test_tennis_metric_probe.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.tennis_metric_probe import (
    REFERENCE_QUAD, reference_homography, summarize, validate_reference,
)


def _rows(scale: float) -> pd.DataFrame:
    """Boxes whose adapter x is a pure scale of the reference x."""
    x = np.linspace(0.0, 78.0, 40)
    return pd.DataFrame({
        "frame": range(len(x)), "x_adapter": x * scale, "y_adapter": np.full(len(x), 18.0),
        "x_reference": x, "y_reference": np.full(len(x), 18.0), "accepted": True,
    })


def test_summarize_reports_unit_scale_for_a_metric_plane() -> None:
    out = summarize(_rows(1.0))
    assert abs(out["length_scale"] - 1.0) < 1e-6
    assert abs(out["length_median_error_ft"]) < 1e-6
    assert out["far_placed_in_near_half"] == 0.0


def test_summarize_detects_a_compressed_length_axis() -> None:
    out = summarize(_rows(0.4))
    assert abs(out["length_scale"] - 0.4) < 1e-6
    # A player at the far baseline reads about half its true distance, so the
    # adapter puts far-court players on the near side of the 39-foot net split.
    assert out["far_placed_in_near_half"] == out["far_players"]


def test_summarize_survives_an_empty_table() -> None:
    empty = pd.DataFrame(columns=("frame", "x_adapter", "y_adapter",
                                  "x_reference", "y_reference", "accepted"))
    assert summarize(empty) == {"n_boxes": 0.0}


def test_reference_homography_maps_the_quad_onto_the_doubles_court() -> None:
    mapped = cv2.perspectiveTransform(
        REFERENCE_QUAD.reshape(1, -1, 2), reference_homography())[0]
    assert np.max(np.abs(mapped - np.float32(((0, 0), (0, 36), (78, 0), (78, 36))))) < 0.01


def test_validate_reference_returns_none_without_court_lines() -> None:
    assert validate_reference(np.zeros((360, 640, 3), dtype=np.uint8)) is None
