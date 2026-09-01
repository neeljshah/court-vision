"""Focused tests for football's pre-snap-aware depth probe.

Run: python -m pytest domains/football/tracking/test_quality_probe.py -q
"""
from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from domains.football.tracking.presnap_features import MIN_PLAYERS_FOR_LOS
from domains.football.tracking.quality_probe import measure_dataframe


def _clip(frames: int = 100, players: int = 22) -> pd.DataFrame:
    rows = []
    for frame in range(frames):
        shift = 0.0 if frame < 40 else 5.0 * (frame - 39)
        for track_id in range(players):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": 50.0 + (track_id % 6) + shift,
                         "y": float(track_id * 7)})
    return pd.DataFrame(rows)


def test_presnap_gate_excludes_moving_frames_and_resolves_los() -> None:
    report = measure_dataframe(_clip())

    assert report.pct_frames_presnap_view == 0.40
    assert report.pct_frames_los_resolved == 1.0
    assert report.median_players_per_presnap_frame == 22.0
    assert report.pct_frames_presnap_coverage == 1.0
    assert report.ungated_harness_coverage == 1.0


def test_too_few_players_never_emit_none_or_coverage() -> None:
    report = measure_dataframe(_clip(frames=10, players=MIN_PLAYERS_FOR_LOS - 1))

    assert report.pct_frames_presnap_view == 0.0
    assert report.pct_frames_los_resolved == 0.0
    assert report.pct_frames_presnap_coverage == 0.0
    assert None not in asdict(report).values()


def test_harness_bar_is_reported_alongside_presnap_coverage() -> None:
    report = measure_dataframe(_clip())

    assert report.pct_frames_presnap_coverage == 1.0
    assert report.ungated_harness_coverage == 1.0
