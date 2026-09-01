"""Focused tests for the read-only tracking depth replay runner."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking.depth_replay import replay, sha256


def _write_game(root: Path, game_id: str) -> Path:
    game = root / game_id
    game.mkdir(parents=True)
    rows = []
    for frame in range(3):
        for track_id in range(8):
            rows.append({"frame": frame, "track_id": track_id, "cls": "player",
                         "x": float(track_id), "y": float(track_id),
                         "homography_valid": True, "team": "A" if track_id < 4 else "B"})
        rows.append({"frame": frame, "track_id": 99, "cls": "ball", "x": 5.0, "y": 5.0,
                     "homography_valid": True, "team": ""})
    path = game / "tracking_data.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def test_replay_handles_twenty_games_and_never_writes_source(tmp_path: Path) -> None:
    paths = [_write_game(tmp_path / "tracking", "game_%02d" % index) for index in range(20)]
    before_hashes = {path: sha256(path) for path in paths}

    output = replay(paths, "basketball", framing=True, transforms={"framing": lambda rows: rows},
                    output_dir=tmp_path / "reports")

    rows = json.loads(output.read_text(encoding="ascii"))
    assert len(rows) == 20
    assert all(sha256(path) == digest for path, digest in before_hashes.items())
    required = {
        "pct_frames_ge_8_players", "pct_frames_homography_valid", "ball_row_coverage",
        "jersey_number_fill_rate", "team_assignment_fill_rate", "median_track_length",
        "screen_candidates_per_minute", "coverage_pct", "jump_p95", "oob_pct",
    }
    assert all(required <= set(row["before"]) and set(row["before"]) == set(row["after"])
               for row in rows)


def test_missing_metric_is_omitted_from_both_sides(tmp_path: Path, monkeypatch) -> None:
    path = _write_game(tmp_path / "tracking", "only_game")
    from scripts.platformkit.tracking import depth_replay

    calls = iter((
        {"coverage_pct": 0.5, "jump_p95": 1.0},
        {"coverage_pct": 0.6, "jump_p95": 1.0, "oob_pct": 0.0},
    ))
    monkeypatch.setattr(depth_replay, "_report", lambda rows, sport: next(calls))

    output = depth_replay.replay([path], "basketball", output_dir=tmp_path / "reports")

    row = json.loads(output.read_text(encoding="ascii"))[0]
    assert row["before"] == {"coverage_pct": 0.5, "jump_p95": 1.0}
    assert row["after"] == {"coverage_pct": 0.6, "jump_p95": 1.0}
