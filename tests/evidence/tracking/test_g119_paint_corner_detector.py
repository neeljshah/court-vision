"""Focused checks for G119's direct local proposal and fail-closed scorer."""
import numpy as np
import pytest

from scripts.platformkit.g119_paint_corner_detector import _matches, _propose, _score


def test_g119_detects_a_local_corner_and_rejects_unlocated_truth() -> None:
    image = np.zeros((80, 80, 3), dtype=np.uint8)
    image[20:61, 20:24] = 255
    image[57:61, 20:61] = 255
    proposals = _propose(image)
    assert _matches(proposals, (22.0, 59.0))
    labels = [{
        "clip": "clip", "source_frame": "1", "slot": "0",
        "point_features": "paint_near_baseline_left_corner",
    }]
    with pytest.raises(ValueError, match="lacks committed coordinate"):
        _score(labels, {("clip", "1", "0"): proposals})
