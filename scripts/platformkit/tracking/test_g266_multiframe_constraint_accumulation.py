"""Focused checks for the G266 measurement helpers."""

import numpy as np

from scripts.platformkit.tracking.g266_multiframe_constraint_accumulation import dlt_condition, transform


def test_transform_and_dlt_condition_are_finite_for_a_rectangle() -> None:
    image = np.float32(((10, 10), (110, 10), (10, 210), (110, 210)))
    court = np.float32(((0, 0), (50, 0), (0, 94), (50, 94)))
    translated = transform(image, np.array(((1.0, 0.0, 3.0), (0.0, 1.0, -2.0), (0.0, 0.0, 1.0))))
    assert np.allclose(translated, image + np.array((3.0, -2.0)))
    assert np.isfinite(dlt_condition(image, court))
