"""Tests for the observed-only soccer coverage-ceiling diagnostic."""
from __future__ import annotations

import pandas as pd

from domains.soccer.tracking.coverage_ceiling import measure


def test_measure_keeps_frames_without_rows_in_denominator() -> None:
    rows = pd.DataFrame([
        {"frame": 10, "track_id": 1, "cls": "player", "observation": "observed"},
        {"frame": 10, "track_id": 1, "cls": "player", "observation": "observed"},
        {"frame": 11, "track_id": 2, "cls": "player", "observation": "inferred"},
    ])
    report = measure(rows, 10, 12)
    assert report.sampled_frames == 3
    assert report.observed_rows == 2
    assert report.histogram == {0: 2, 1: 1}
    assert report.frames_at_least_14 == 0
    assert report.pct_at_least_14 == 0.0


def test_measure_counts_distinct_observed_players_per_frame() -> None:
    rows = pd.DataFrame([
        {"frame": 4, "track_id": track, "cls": "player", "observation": "observed"}
        for track in range(15)
    ])
    report = measure(rows, 4, 5)
    assert report.median_players == 7.5
    assert report.p90_players == 13.5
    assert report.max_players == 15
    assert report.frames_at_least_14 == 1
    assert report.pct_at_least_14 == 50.0
