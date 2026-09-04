"""Focused tests for the G233b distance-zero NCAA seed gate."""

from __future__ import annotations

import base64
import re

import numpy as np

from scripts.platformkit.tracking.g233b_ncaa_seed_gate import (
    LABEL_POINTS,
    SCALE_FACTOR,
    SPORT,
    render_seed,
    scaled_image_points,
)
from scripts.platformkit.tracking.g233b_pod_seed_gate import remote_script


def test_g233b_uses_exact_three_x_scale_and_twelve_foot_ncaa_lane() -> None:
    assert SCALE_FACTOR == 3.0
    assert scaled_image_points().tolist() == [[114.0, 669.0], [117.0, 867.0], [822.0, 672.0], [819.0, 846.0]]
    assert LABEL_POINTS.tolist() == [[38.0, 223.0], [39.0, 289.0], [274.0, 224.0], [273.0, 282.0]]
    image = np.zeros((1080, 1920, 3), dtype=np.uint8)
    rendered, homography, court_points = render_seed(image)
    assert SPORT == "ncaa_basketball"
    assert court_points.tolist() == [[19.0, 0.0], [31.0, 0.0], [19.0, 19.0], [31.0, 19.0]]
    assert rendered.shape == image.shape
    assert np.isfinite(homography).all()


def test_g233b_pod_wrapper_probes_before_writing_the_measurement_child() -> None:
    command = remote_script()
    assert "conv=fsync" in command
    assert 'mkdir -p "$ROOT"' in command
    encoded = re.search(r"printf '%s' '([A-Za-z0-9+/=]+)' \| base64", command)
    assert encoded is not None
    runner = base64.b64decode(encoded.group(1)).decode("ascii")
    assert '"--output-dir","/tmp/g233b_seed_gate/measurement"' in runner
