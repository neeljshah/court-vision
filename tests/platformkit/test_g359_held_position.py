"""Synthetic self-check for the G359 held-share, collapse and decision rules."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.liveness_metrics import compute_liveness_metrics
from scripts.platformkit.tracking.g358_gate_execution import arm_frozen
from scripts.platformkit.tracking.g359_held_position import (
    classify, collapse_held, denominators, held_share,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PREREG = (REPO_ROOT / "docs/evidence/tracking"
          / "g359_held_position_vs_threshold_2026-09-09/g359_prereg_2026-09-09.md")


def _production_csv(path: Path) -> Path:
    """Track 1 holds one position for 3 frames then moves; track 2 never holds."""
    rows = [
        {"frame": 0, "player_id": 1, "x_position": "100", "y_position": "200"},
        {"frame": 1, "player_id": 1, "x_position": "100", "y_position": "200"},
        {"frame": 2, "player_id": 1, "x_position": "100", "y_position": "200"},
        {"frame": 3, "player_id": 1, "x_position": "101", "y_position": "200"},
        {"frame": 0, "player_id": 2, "x_position": "300", "y_position": "400"},
        {"frame": 1, "player_id": 2, "x_position": "301", "y_position": "401"},
        {"frame": 2, "player_id": 2, "x_position": "302", "y_position": "402"},
    ]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _image_table() -> pd.DataFrame:
    """Player 1 held on frames 1-2; player 2 always moving; one ball row per frame."""
    rows = []
    positions = {1: [(5.0, 5.0), (5.0, 5.0), (5.0, 5.0), (9.0, 5.0)],
                 2: [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0), (4.0, 4.0)]}
    for track, points in positions.items():
        for frame, (x, y) in enumerate(points):
            rows.append({"cls": "player", "frame": frame, "track_id": track, "team": "home",
                         "x": x, "y": y})
    for frame in range(4):
        rows.append({"cls": "ball", "frame": frame, "track_id": -1, "team": "home",
                     "x": 7.0, "y": 7.0})
    return pd.DataFrame(rows)


def test_held_share_counts_byte_identical_repeats(tmp_path: Path) -> None:
    measured = held_share(_production_csv(tmp_path / "tracking_data.csv"))
    assert measured["rows"] == 7 and measured["tracks"] == 2
    assert measured["pairs_n"] == 5          # 7 rows - 2 tracks
    assert measured["held_n"] == 2           # only track 1, frames 1 and 2
    assert measured["held_share"] == 2 / 5
    assert measured["unique_frames"] == 4 and measured["modal_frame_step"] == 1


def test_collapse_keeps_first_row_of_each_run_and_leaves_others_untouched() -> None:
    table = _image_table()
    collapsed, dropped = collapse_held(table)
    assert dropped == 2
    track1 = collapsed.loc[collapsed["cls"].eq("player") & collapsed["track_id"].eq(1)]
    assert list(track1["frame"]) == [0, 3]           # first row of the run, then the move
    assert list(track1["x"]) == [5.0, 9.0]
    track2 = collapsed.loc[collapsed["cls"].eq("player") & collapsed["track_id"].eq(2)]
    assert track2.reset_index(drop=True).equals(
        table.loc[table["cls"].eq("player") & table["track_id"].eq(2)].reset_index(drop=True))
    balls = collapsed.loc[collapsed["cls"].eq("ball")]
    assert len(balls) == 4                            # ball rows are never collapsed


def test_collapse_is_a_no_op_when_no_position_repeats() -> None:
    table = _image_table()
    moving = table.loc[~(table["cls"].eq("player") & table["track_id"].eq(1))].reset_index(drop=True)
    collapsed, dropped = collapse_held(moving)
    assert dropped == 0 and collapsed.equals(moving)


def test_collapse_of_none_arm_is_none() -> None:
    assert collapse_held(None) == (None, 0)


def test_plant_before_collapse_survives_the_collapse() -> None:
    planted = arm_frozen(_image_table())
    collapsed, dropped = collapse_held(planted)
    players = collapsed.loc[collapsed["cls"].eq("player")]
    assert dropped == 6                                # 3 held rows per frozen track
    assert len(players) == 2                           # one surviving row per frozen track
    assert set(players["track_id"]) == {1, 2}          # no track is erased by the collapse


def test_stationary_track_share_is_invariant_under_the_collapse() -> None:
    table = _image_table()
    collapsed, _ = collapse_held(table)
    before = compute_liveness_metrics(table, "basketball")
    after = compute_liveness_metrics(collapsed, "basketball")
    assert before.stationary_track_share == after.stationary_track_share


def test_denominators_report_raw_and_collapsed_counts() -> None:
    table = _image_table()
    collapsed, dropped = collapse_held(table)
    raw = denominators(table, 0)
    coll = denominators(collapsed, dropped)
    assert raw["player_rows"] == "000008" and raw["steps_n"] == "000006"
    assert coll["player_rows"] == "000006" and coll["steps_n"] == "000004"
    assert coll["held_rows_dropped"] == "000002"
    assert raw["ball_rows"] == coll["ball_rows"] == "000004"
    assert denominators(None, 0)["rows_total"] == "000000"


def test_classification_rule_on_constructed_cases() -> None:
    # M1 clears every section while M0 clears none -> the schema artifact class.
    assert classify(0.0, 1.0) == "PRODUCTION_SCHEMA_ARTIFACT"
    # M1 still rejects more than a tenth of the sections -> the threshold class.
    assert classify(0.0, 0.5) == "THRESHOLD_MISCALIBRATED"
    # The sealed order puts the exact M1 boundary in the artifact class.
    assert classify(0.5, 0.90) == "PRODUCTION_SCHEMA_ARTIFACT"
    # Same M1 boundary, but M0 also clears at the bar, so rule 1 does not fire.
    assert classify(0.90, 0.90) == "THRESHOLD_MISCALIBRATED"
    # M0 already clears: the gate is not a live rejecter on this set.
    assert classify(1.0, 1.0) == "UNDECIDED"
    assert classify(0.95, 0.95) == "UNDECIDED"


def test_prereg_seal_matches_the_bytes_above_it() -> None:
    raw = PREREG.read_bytes().replace(b"\r\n", b"\n")
    body, seal = raw.rsplit(b"SEAL sha256 ", 1)
    assert seal.decode("ascii").strip() == hashlib.sha256(body).hexdigest()
