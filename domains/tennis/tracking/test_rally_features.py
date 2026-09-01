"""Synthetic-geometry checks for tennis rally features.

Run: python -m pytest domains/tennis/tracking/test_rally_features.py -q
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from domains.tennis.tracking.rally_features import (
    match_aggregates,
    rally_bucket,
    rally_features,
    rally_segments,
    shots_equivalent,
)


N_FRAMES = 120
FAST_P1 = (0.5, 0.1)
FAST_P2 = (-0.5, -0.2)
SLOW = (0.02, 0.0)
RALLY_ONE = (0, 19)
RALLY_TWO = (100, 119)
COLUMNS = ["frame", "track_id", "cls", "x", "y"]


def _steps(fast: tuple[float, float]) -> np.ndarray:
    """Steps into frames 1..119: fast during both rallies, a slow walk between."""
    steps = np.array([SLOW] * (N_FRAMES - 1), dtype=float)
    steps[0:19] = fast
    steps[100:119] = fast
    return steps


def _track(start: tuple[float, float], fast: tuple[float, float]) -> np.ndarray:
    origin = np.zeros((1, 2), dtype=float)
    return np.vstack((origin, np.cumsum(_steps(fast), axis=0))) + np.asarray(start)


def _match_df(with_ball: bool = True) -> pd.DataFrame:
    player_one = _track((30.0, -4.0), FAST_P1)
    player_two = _track((50.0, 40.0), FAST_P2)
    rows: list[dict[str, object]] = []
    for frame in range(N_FRAMES):
        for track_id, path in ((1, player_one), (2, player_two)):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": float(path[frame, 0]), "y": float(path[frame, 1])})
        if with_ball and (frame <= RALLY_ONE[1] or frame >= RALLY_TWO[0]):
            rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                         "x": 39.0, "y": 18.0})
    return pd.DataFrame(rows, columns=COLUMNS)


def test_ball_rows_split_the_match_into_two_rallies() -> None:
    assert rally_segments(_match_df()) == [RALLY_ONE, RALLY_TWO]


def test_motion_bursts_segment_when_no_ball_was_tracked() -> None:
    no_ball = _match_df(with_ball=False)
    assert (no_ball["cls"] == "ball").sum() == 0
    assert rally_segments(no_ball) == [RALLY_ONE, RALLY_TWO]


def test_short_windows_are_dropped() -> None:
    assert rally_segments(_match_df(), min_frames=25) == []


def test_first_rally_geometry_is_recovered_exactly() -> None:
    rally = rally_features(_match_df(), RALLY_ONE)
    assert rally["n_frames"] == 20
    assert rally["duration_s"] == pytest.approx(20.0 / 30.0)
    # Widest separation is on frame 0: 20 ft across, 44 ft apart end to end.
    assert rally["max_separation_ft"] == pytest.approx(math.hypot(20.0, 44.0))

    near = rally["players"][1]
    assert near["n_frames"] == 20
    # Near player walks from 4.0 ft behind his baseline to 2.1 ft behind it.
    assert near["mean_baseline_depth_ft"] == pytest.approx(3.05)
    assert near["median_baseline_depth_ft"] == pytest.approx(3.05)
    assert near["coverage_area_sqft"] == pytest.approx(9.5 * 1.9)
    assert near["distance_run_ft"] == pytest.approx(19.0 * math.hypot(0.5, 0.1))

    far = rally["players"][2]
    assert far["mean_baseline_depth_ft"] == pytest.approx(2.1)
    assert far["coverage_area_sqft"] == pytest.approx(9.5 * 3.8)
    assert far["distance_run_ft"] == pytest.approx(19.0 * math.hypot(0.5, 0.2))


def test_depth_is_negative_when_a_player_moves_inside_the_court() -> None:
    # In rally two the far player advances from 0.2 ft behind his baseline to
    # 3.6 ft inside the court, so mean depth must go negative.
    far = rally_features(_match_df(), RALLY_TWO)["players"][2]
    assert far["mean_baseline_depth_ft"] == pytest.approx(-1.7)


def test_match_aggregates_medians_and_buckets() -> None:
    summary = match_aggregates(_match_df())
    assert summary["n_rallies"] == 2
    assert summary["rally_length_buckets"] == {"1-4": 2, "5-8": 0, "9+": 0}
    assert summary["median_rally_seconds"] == pytest.approx(20.0 / 30.0)

    near = summary["players"][1]
    assert near["n_rallies"] == 2
    # Median over the two rallies of 3.05 ft and 1.15 ft behind the baseline.
    assert near["median_baseline_depth_ft"] == pytest.approx(2.1)
    assert near["median_coverage_area_sqft"] == pytest.approx(9.5 * 1.9)
    assert near["median_distance_run_ft"] == pytest.approx(19.0 * math.hypot(0.5, 0.1))
    assert summary["players"][2]["median_baseline_depth_ft"] == pytest.approx(0.2)


def test_long_rally_lands_in_the_middle_bucket() -> None:
    rows: list[dict[str, object]] = []
    for frame in range(300):
        rows.append({"frame": frame, "track_id": 1, "cls": "player",
                     "x": 30.0 + 0.1 * frame, "y": -2.0})
        rows.append({"frame": frame, "track_id": 2, "cls": "player",
                     "x": 50.0, "y": 38.0})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball",
                     "x": 39.0, "y": 18.0})
    summary = match_aggregates(pd.DataFrame(rows, columns=COLUMNS))
    assert summary["n_rallies"] == 1
    assert summary["rally_length_buckets"] == {"1-4": 0, "5-8": 1, "9+": 0}
    assert shots_equivalent(10.0) == 7
    assert (rally_bucket(4), rally_bucket(5), rally_bucket(9)) == ("1-4", "5-8", "9+")


def test_missing_columns_are_rejected() -> None:
    with pytest.raises(ValueError):
        rally_segments(pd.DataFrame({"frame": [0], "x": [1.0]}))
