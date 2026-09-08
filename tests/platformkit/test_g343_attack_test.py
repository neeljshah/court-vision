"""Per-file construct tests for the six G343 corruption arms."""
from __future__ import annotations

import pandas as pd

import scripts.platformkit.tracking.g343_attack_test as g343
from scripts.platformkit.tracking.g343_attack_test import apply_arm, cell_statuses


def _construct() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for frame in range(60):
        for ident, team in ((1, "A"), (2, "A"), (3, "B")):
            rows.append({"frame": frame, "track_id": ident, "team": team, "cls": "player",
                         "x": 10.0 * ident + frame, "y": 5.0 * ident + frame, "payload": "fixed"})
    ball = pd.DataFrame({"frame": range(60), "detected": [1] * 60, "payload": ["ball"] * 60})
    return pd.DataFrame(rows), ball


def test_g343_arms_change_only_the_declared_columns():
    tracking, ball = _construct()
    base_tracking, base_ball = apply_arm(tracking, ball, "A0", 100.0, 50.0)
    pd.testing.assert_frame_equal(base_tracking, tracking)
    pd.testing.assert_frame_equal(base_ball, ball)
    for arm in ("A1", "A2", "A3", "A4", "A5"):
        attacked, attacked_ball = apply_arm(tracking, ball, arm, 100.0, 50.0)
        assert len(attacked) == len(tracking) and len(attacked_ball) == len(ball)
        if arm == "A1":
            pd.testing.assert_frame_equal(attacked.drop(columns=["x", "y"]),
                                          tracking.drop(columns=["x", "y"]))
            assert attacked.groupby("track_id")[["x", "y"]].nunique().eq(1).all().all()
            pd.testing.assert_frame_equal(attacked_ball, ball)
        elif arm == "A2":
            pd.testing.assert_frame_equal(attacked.drop(columns=["track_id"]),
                                          tracking.drop(columns=["track_id"]))
            assert attacked["track_id"].nunique() == 2
            pd.testing.assert_frame_equal(attacked_ball, ball)
        elif arm == "A3":
            pd.testing.assert_frame_equal(attacked, tracking)
            pd.testing.assert_frame_equal(attacked_ball.drop(columns=["frame"]),
                                          ball.drop(columns=["frame"]))
            assert (attacked_ball["frame"] == ball["frame"] + 30).all()
        elif arm == "A4":
            pd.testing.assert_frame_equal(attacked.drop(columns=["x", "y"]),
                                          tracking.drop(columns=["x", "y"]))
            pd.testing.assert_frame_equal(attacked_ball, ball)
            assert not attacked[["x", "y"]].equals(tracking[["x", "y"]])
        else:
            pd.testing.assert_frame_equal(attacked.drop(columns=["x"]),
                                          tracking.drop(columns=["x"]))
            pd.testing.assert_frame_equal(attacked_ball, ball)
            assert not attacked["x"].equals(tracking["x"])


def test_a3_is_not_applicable_because_the_harness_reads_no_ball_table():
    """A3 only shifts the ball table; evaluate() takes one df and never
    reads a separate ball table for this schema, so every gate must be
    NOT_APPLICABLE with that reason, not routed into evaluate()."""
    tracking, ball = _construct()
    statuses = cell_statuses(tracking, ball, "A3", 100.0, 50.0, "unused")
    assert all(status == "NOT_APPLICABLE" for status, _ in statuses.values())
    assert all(reason == "harness reads no ball table" for _, reason in statuses.values())


def test_evaluate_valueerror_is_not_applicable_gate_error_not_construction_failure(monkeypatch):
    """A harness ValueError (e.g. identify_tracking_schema on a mangled arm
    output) must stay inside the sealed PASS/REJECT/NOT_APPLICABLE vocabulary
    -- NOT_APPLICABLE with a gate_error: reason, never a fourth status token,
    and never mislabeled as an arm-construction failure (the two
    except-clauses must stay separate)."""
    def _raise(*_args, **_kwargs):
        raise ValueError("boom")
    monkeypatch.setattr(g343, "evaluate", _raise)
    tracking, ball = _construct()
    statuses = cell_statuses(tracking, ball, "A1", 100.0, 50.0, "unused")
    assert all(status == "NOT_APPLICABLE" for status, _ in statuses.values())
    assert all(reason.startswith("gate_error:") and "boom" in reason and "construction" not in reason
               for _, reason in statuses.values())
