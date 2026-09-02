"""Synthetic checks for basketball image-pixel teacher feature exclusions."""
from __future__ import annotations

import pytest

from scripts.platformkit.tracking.basketball_imagepx_features import extract_features


def _rows() -> list[dict]:
    rows: list[dict] = []
    points = {
        0: ((20, 30), (30, 30)), 1: ((24, 30), (34, 30)),
        2: ((28, 30), (38, 30)), 3: ((24, 30), (34, 30)),
        4: ((20, 30), (30, 30)), 5: ((70, 30), (80, 30)),
        6: ((90, 30), (100, 30)), 7: ((90, 30), (100, 30)),
    }
    for frame, pair in points.items():
        for index, (x, y) in enumerate(pair, start=1):
            rows.append({"frame": frame, "track_id": "t{}".format(index), "x": x, "y": y,
                         "frame_width": 100, "frame_height": 60,
                         "coordinate_space": "image_px",
                         "observation": "coasted" if frame == 2 and index == 1 else "observed"})
    return rows


def test_imagepx_proxies_exclude_coasts_and_global_pan() -> None:
    import pandas as pd

    result = extract_features(pd.DataFrame(_rows()), "synthetic", fps=1.0)
    assert result["coordinate_space"] == "image_px"
    assert result["decoded_frames"] == 8
    assert result["players_on_floor"]["median_observed_rows_per_frame"] == 2.0
    assert result["players_on_floor"]["share_frames_count_8_to_10"] == 0.0
    assert result["exclusions"]["n_rows_excluded_coasted"] == 1
    assert result["camera_motion"]["flagged_frame_share"] == pytest.approx(2 / 8)
    assert result["pace_proxy"]["median_foot_point_displacement_per_second_per_frame_width"] == 0.04
    assert result["pace_proxy"]["n_excluded"]["camera_pan_pairs"] == 4
    assert result["possession_change_proxy"]["centroid_x_direction_reversals_per_minute"] == 7.5
    assert result["spread_proxy"]["median_x_foot_point_std_per_frame_width"] == 0.05
    assert result["spread_proxy"]["n_frames_used"] == 6
