"""Focused geometry checks for the CPU-only soccer SynthCal sampler.

Run: python -m pytest scripts/platformkit/synthcal/test_soccer_sampler.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.synthcal.renderer import render_soccer_samples
from scripts.platformkit.synthcal.soccer_sampler import (
    CAMERA_MEAN_M,
    CAMERA_SD_M,
    CENTRE_CIRCLE_RADIUS_M,
    FOCAL_PX,
    MIN_PITCH_SHARE,
    MIN_VISIBLE_LANDMARKS,
    PAN_DEG,
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    TILT_DEG,
    fifa_landmarks,
    geometry_metrics,
    sample_soccer_frame,
)


def test_fifa_landmarks_match_template_geometry() -> None:
    landmarks = fifa_landmarks()
    assert len(landmarks) == 24
    assert landmarks["centre_spot"] == (PITCH_LENGTH_M / 2, PITCH_WIDTH_M / 2)
    assert landmarks["left_penalty_spot"] == (11.0, PITCH_WIDTH_M / 2)
    assert landmarks["right_penalty_spot"] == (94.0, PITCH_WIDTH_M / 2)
    assert landmarks["left_penalty_top_inner"] == (16.5, 13.84)
    assert landmarks["right_goal_bottom_inner"] == (99.5, 43.16)
    assert CENTRE_CIRCLE_RADIUS_M == 9.15


def test_sampler_enforces_broadcast_geometry_distribution() -> None:
    """Regression guard against sky-heavy and pitch-fragment sampler poses."""
    metrics = np.array([geometry_metrics(seed) for seed in range(200)])
    shares, visible = metrics[:, 0], metrics[:, 1]
    assert np.median(shares) >= 0.55
    assert np.quantile(shares, 0.10) >= MIN_PITCH_SHARE
    assert np.median(visible) >= MIN_VISIBLE_LANDMARKS


def test_pose_prior_matches_sccvsd_ranges() -> None:
    assert PAN_DEG == (-35.0, 35.0)
    assert TILT_DEG == (-15.0, -5.0)
    assert FOCAL_PX == (1000.0, 6000.0)
    assert np.array_equal(CAMERA_MEAN_M, np.array([52.0, -45.0, 17.0]))
    assert np.array_equal(CAMERA_SD_M, np.array([2.0, 9.0, 3.0]))


def test_rendered_sample_labels_are_aligned() -> None:
    sample = sample_soccer_frame(seed=7)
    assert sample.image.shape == (720, 1280, 3)
    assert sample.names == tuple(fifa_landmarks())
    assert sample.points.shape == (len(sample.names), 2)
    assert sample.visible.shape == (len(sample.names),)
    assert sample.visible.dtype == bool
    assert np.isfinite(sample.points).all()


def test_renderer_writes_requested_cpu_samples(tmp_path) -> None:
    samples = render_soccer_samples(tmp_path, count=2, seed=11)
    assert len(samples) == 2
    assert sorted(path.name for path in tmp_path.glob("*.png")) == [
        "soccer_synthcal_00.png", "soccer_synthcal_01.png",
    ]
