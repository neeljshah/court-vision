"""Tests for offline recovery; all synthetic rows are deliberately small."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.coverage_recovery import (
    frame_completeness_report,
    occlusion_infill,
    track_bridging,
)


def _rows() -> pd.DataFrame:
    return pd.DataFrame([
        {"frame": 0, "track_id": "a", "cls": "player", "x": 0.0, "y": 0.0, "team": "home", "jersey_number": 4},
        {"frame": 1, "track_id": "a", "cls": "player", "x": 1.0, "y": 0.0, "team": "home", "jersey_number": 4},
        {"frame": 4, "track_id": "b", "cls": "player", "x": 4.0, "y": 0.0, "team": "home", "jersey_number": 4},
        {"frame": 5, "track_id": "b", "cls": "player", "x": 5.0, "y": 0.0, "team": "home", "jersey_number": 4},
        {"frame": 0, "track_id": "other", "cls": "player", "x": 90.0, "y": 0.0, "team": "away", "jersey_number": 8},
        {"frame": 4, "track_id": "other", "cls": "player", "x": 0.0, "y": 0.0, "team": "away", "jersey_number": 8},
    ])


def test_bridging_and_infill_recover_one_existing_identity() -> None:
    before = _rows()
    bridge_map = track_bridging(before, fps=1, max_speed_ft_per_sec=3)
    assert bridge_map["b"] == "a"
    assert bridge_map["other"] == "other"
    after = occlusion_infill(before, bridge_map, fps=1, max_speed_ft_per_sec=3)
    inferred = after.loc[after["inferred"].eq(1)]
    assert inferred[["frame", "track_id", "x", "y"]].to_dict("records") == [
        {"frame": 2, "track_id": "a", "x": 2.0, "y": 0.0},
        {"frame": 3, "track_id": "a", "x": 3.0, "y": 0.0},
    ]
    assert set(after["track_id"]) == {"a", "other"}
    assert after.loc[after["inferred"].eq(1), "source_track_id"].isna().all()


def test_infill_respects_speed_and_gap_caps_without_new_tracks() -> None:
    before = pd.DataFrame([
        {"frame": 0, "track_id": 1, "cls": "player", "x": 0.0, "y": 0.0},
        {"frame": 2, "track_id": 2, "cls": "player", "x": 100.0, "y": 0.0},
        {"frame": 20, "track_id": 3, "cls": "player", "x": 20.0, "y": 0.0},
    ])
    after = occlusion_infill(before, {1: 1, 2: 1, 3: 1}, fps=1, max_gap_frames=15, max_speed_ft_per_sec=24)
    assert after["inferred"].sum() == 0
    assert len(after) == len(before)
    assert set(after["track_id"]) == {1}


def test_completeness_report_math_is_exact_and_counts_no_fabricated_identity() -> None:
    before = pd.DataFrame([
        {"frame": 0, "track_id": "left", "cls": "player", "x": 0.0, "y": 0.0},
        {"frame": 2, "track_id": "right", "cls": "player", "x": 2.0, "y": 0.0},
    ])
    after = occlusion_infill(before, {"left": "left", "right": "left"}, fps=1, max_speed_ft_per_sec=3)
    report = frame_completeness_report(before, after, minimum_players=1)
    assert report == {"pct_frames_with_at_least_n_before": 66.666667,
                      "pct_frames_with_at_least_n_after": 100.0,
                      "id_fragment_count_before": 2, "id_fragment_count_after": 1,
                      "inferred_row_share": 33.333333}
