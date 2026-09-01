"""Focused geometry checks for the CPU-only basketball SynthCal sampler.

Run: python -m pytest scripts/platformkit/synthcal/test_basketball_sampler.py -q
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.synthcal.basketball_sampler import (
    CAMERA_HEIGHT_FT, CAMERA_X_FT, CAMERA_Y_FT, COURT_LENGTH_FT, COURT_WIDTH_FT,
    FREE_THROW_CIRCLE_RADIUS_FT, LANE_DEPTH_FT, LANE_WIDTH_FT, MIN_COURT_SHARE,
    MIN_VISIBLE_LANDMARKS, THREE_POINT_ARC_RADIUS_FT, THREE_POINT_CORNER_DISTANCE_FT,
    geometry_metrics, nba_landmarks, sample_basketball_frame,
)
from scripts.platformkit.synthcal.renderer import render_basketball_samples


def test_nba_landmarks_match_rule_template() -> None:
    landmarks = nba_landmarks()
    assert COURT_LENGTH_FT == 94.0 and COURT_WIDTH_FT == 50.0
    assert LANE_WIDTH_FT == 16.0 and LANE_DEPTH_FT == 19.0
    assert FREE_THROW_CIRCLE_RADIUS_FT == 6.0
    assert THREE_POINT_ARC_RADIUS_FT == 23.75 and THREE_POINT_CORNER_DISTANCE_FT == 22.0
    assert landmarks["centre_spot"] == (47.0, 25.0)
    assert landmarks["left_lane_top_ft"] == (19.0, 17.0)
    assert landmarks["right_lane_bottom_ft"] == (75.0, 33.0)


def test_sampler_enforces_quantitative_broadcast_geometry_guard() -> None:
    metrics = np.array([geometry_metrics(seed) for seed in range(200)])
    shares, visible = metrics[:, 0], metrics[:, 1]
    assert np.median(shares) >= 0.55
    assert np.quantile(shares, 0.10) >= MIN_COURT_SHARE
    assert np.median(visible) >= MIN_VISIBLE_LANDMARKS


def test_high_sideline_prior_is_documented_as_plausible_ranges() -> None:
    assert CAMERA_X_FT == (39.0, 55.0)
    assert CAMERA_Y_FT == (-48.0, -30.0)
    assert CAMERA_HEIGHT_FT == (24.0, 38.0)


def test_rendered_sample_labels_are_aligned() -> None:
    sample = sample_basketball_frame(seed=7)
    assert sample.image.shape == (720, 1280, 3)
    assert sample.names == tuple(nba_landmarks())
    assert sample.points.shape == (len(sample.names), 2)
    assert sample.visible.dtype == bool
    assert np.isfinite(sample.points).all()


def test_renderer_writes_requested_cpu_samples(tmp_path) -> None:
    samples = render_basketball_samples(tmp_path, count=2, seed=11)
    assert len(samples) == 2
    assert sorted(path.name for path in tmp_path.glob("*.png")) == [
        "basketball_synthcal_00.png", "basketball_synthcal_01.png",
    ]
