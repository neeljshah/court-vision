"""G43 + G50: the two additive harness metrics report what the gates cannot see.

Both are informational. Neither may change `passed`, and neither may move a
threshold -- these tests assert exactly that.
"""
import pandas as pd

from scripts.platformkit.tracking_harness import (
    MIN_FRAMES_FOR_METRICS, evaluate,
)


def _tennis_frame(n_frames: int, ball_x: float) -> pd.DataFrame:
    """Two players on the court every frame, plus one ball row at ball_x."""
    # The coordinate contract rejects undeclared rows before any quality metric
    # is computed, so a scorable fixture must declare court_feet.
    declared = {"coordinate_space": "court_feet", "observation": "measured",
                "calibration": "fresh"}
    rows = []
    for f in range(n_frames):
        rows.append(dict(frame=f, track_id="1", cls="player", x=20.0, y=10.0, **declared))
        rows.append(dict(frame=f, track_id="2", cls="player", x=20.0, y=30.0, **declared))
        rows.append(dict(frame=f, track_id="99", cls="ball", x=ball_x, y=20.0, **declared))
    return pd.DataFrame(rows)


def test_ball_in_bounds_separates_real_telemetry_from_blown_up_projections() -> None:
    """G43: ball_valid_pct cannot tell 39 ft from 106,853 ft. This can."""
    on_court = evaluate(_tennis_frame(60, 39.0), "tennis")
    blown_up = evaluate(_tennis_frame(60, 106853.7), "tennis")

    # ball_valid_pct is presence-only, so it is identical for both.
    assert on_court.ball_valid_pct == blown_up.ball_valid_pct
    # The new metric is what actually separates them.
    assert on_court.ball_in_bounds_pct == 1.0
    assert blown_up.ball_in_bounds_pct == 0.0


def test_insufficient_data_flags_a_table_too_small_to_mean_anything() -> None:
    """G50: coverage_pct 1.0 was published on a 2-frame table."""
    tiny = evaluate(_tennis_frame(2, 39.0), "tennis")
    assert tiny.insufficient_data is True
    # The tautological coverage is still reported unchanged -- the flag is the
    # only thing telling a reader not to trust it.
    assert tiny.coverage_pct == 1.0

    big = evaluate(_tennis_frame(MIN_FRAMES_FOR_METRICS + 1, 39.0), "tennis")
    assert big.insufficient_data is False


def test_neither_metric_changes_the_verdict() -> None:
    """Additive means additive: `passed` must not read either new field."""
    tiny_bad_ball = evaluate(_tennis_frame(2, 106853.7), "tennis")
    big_bad_ball = evaluate(_tennis_frame(60, 106853.7), "tennis")
    big_good_ball = evaluate(_tennis_frame(60, 39.0), "tennis")

    # A blown-up ball still passes the ball gate on presence alone, exactly as
    # before this change. That is the defect G43 documents, not a regression.
    assert big_bad_ball.passed == big_good_ball.passed
    # And the insufficient_data flag does not fail an otherwise-passing report.
    assert tiny_bad_ball.passed == big_bad_ball.passed


def test_ball_in_bounds_is_none_when_there_are_no_ball_rows() -> None:
    frame = _tennis_frame(60, 39.0)
    report = evaluate(frame[frame["cls"] != "ball"], "tennis")
    assert report.ball_in_bounds_pct is None
