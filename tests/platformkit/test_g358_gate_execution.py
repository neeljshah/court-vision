"""Synthetic self-check for the G358 fix 1b arm constructors and aggregation."""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.tracking.g358_gate_execution import (
    aggregate_gates, arm_ball_shift, arm_frozen, arm_id_merge, diagnosis_table, wilson_interval,
)


def _table() -> pd.DataFrame:
    rows = []
    for frame in range(3):
        rows.append({"cls": "player", "frame": frame, "track_id": 1, "team": "home",
                    "x": float(frame), "y": float(frame)})
        rows.append({"cls": "player", "frame": frame, "track_id": 2, "team": "home",
                    "x": 10.0 + frame, "y": 10.0 + frame})
        rows.append({"cls": "ball", "frame": frame, "track_id": -1, "team": "home",
                    "x": 5.0, "y": 5.0})
    return pd.DataFrame(rows)


def test_arm_frozen_holds_first_player_position() -> None:
    out = arm_frozen(_table())
    players = out.loc[out["cls"].eq("player") & out["track_id"].eq(1)]
    assert (players["x"] == 0.0).all() and (players["y"] == 0.0).all()


def test_arm_id_merge_folds_second_track_into_first() -> None:
    out = arm_id_merge(_table())
    assert out is not None
    assert set(out.loc[out["cls"].eq("player"), "track_id"]) == {1}


def test_arm_ball_shift_offsets_only_ball_frame() -> None:
    out = arm_ball_shift(_table())
    assert out is not None
    assert list(out.loc[out["cls"].eq("ball"), "frame"]) == [30, 31, 32]
    assert list(out.loc[out["cls"].eq("player"), "frame"].unique()) == [0, 1, 2]


def test_wilson_interval_bounds_and_zero_n() -> None:
    assert wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = wilson_interval(3, 6)
    assert 0.0 <= lo < 0.5 < hi <= 1.0


def test_aggregate_gates_counts_reject_share() -> None:
    records = [
        {"arm": "A0", "duration": "FULL", "gate": "g", "status": "PASS"},
        {"arm": "A0", "duration": "FULL", "gate": "g", "status": "REJECT"},
        {"arm": "A0", "duration": "FULL", "gate": "g", "status": "NOT_APPLICABLE"},
    ]
    rows = aggregate_gates(records)
    row = rows[0]
    assert row["evaluated_n"] == "000002"
    assert row["rejected_n"] == "000001"
    assert row["rejection_share"] == "0.500000"


def test_diagnosis_median_is_standard_not_select_by_index() -> None:
    # 4 measurements (even n): standard median averages the two middle values (2.5).
    # The prior values[len(values) // 2] selection returned values[2] == 3.0 -- wrong.
    records = [
        {"arm": "A0", "duration": "FULL", "gate": "zero_step_share", "status": "PASS",
         "measurement": 1.0, "threshold": 5.0},
        {"arm": "A0", "duration": "FULL", "gate": "zero_step_share", "status": "PASS",
         "measurement": 2.0, "threshold": 5.0},
        {"arm": "A0", "duration": "FULL", "gate": "zero_step_share", "status": "REJECT",
         "measurement": 3.0, "threshold": 5.0},
        {"arm": "A0", "duration": "FULL", "gate": "zero_step_share", "status": "PASS",
         "measurement": 4.0, "threshold": 5.0},
    ]
    rows = diagnosis_table(records)
    assert len(rows) == 1
    assert rows[0]["statistic_median"] == "2.500000"
    # numpy/pandas default (linear interpolation) quantile(0.9) on [1,2,3,4] -> 3.7
    assert rows[0]["statistic_p90"] == "3.700000"


def test_reached_n_counts_not_applicable_and_measured_no_bar() -> None:
    # A cell that never produced a PASS/REJECT (NOT_APPLICABLE / MEASURED_NO_BAR) was
    # actually reached by evaluate_image_space and must report reached_n > 0, distinct
    # from evaluated_n (the PASS/REJECT share denominator), which stays 0.
    records = [
        {"arm": "A0", "duration": "FULL", "gate": "g325_wholly_off_frame",
         "status": "NOT_APPLICABLE"},
        {"arm": "A0", "duration": "FULL", "gate": "g325_wholly_off_frame",
         "status": "MEASURED_NO_BAR"},
    ]
    rows = aggregate_gates(records)
    row = rows[0]
    assert row["reached_n"] == "000002"
    assert row["evaluated_n"] == "000000"
