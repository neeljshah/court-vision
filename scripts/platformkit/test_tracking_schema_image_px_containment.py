"""A declared image_px table is rejected when its points miss the frame.

The declaration check is magnitude-blind, so it passed 103,009 basketball rows
of map_2d minimap-canvas pixels labelled image_px. This gate is the independent
check: points must land inside the frame the producer says it decoded.
"""
import pandas as pd
import pytest

from scripts.platformkit.tracking_harness import evaluate
from scripts.platformkit.tracking_schema import (
    IMAGE_PX_CONTAINMENT_MIN,
    CoordinateTransformUnavailable,
    normalize_tracking_frame,
)


def _rows(xs, ys, width=1280, height=720, space="image_px"):
    frame = pd.DataFrame({"frame": range(len(xs)), "track_id": 1, "cls": "player",
                          "x": xs, "y": ys, "coordinate_space": space})
    if width is not None:
        frame["frame_width"], frame["frame_height"] = width, height
    return frame


def test_threshold_is_ninety_five_percent():
    assert IMAGE_PX_CONTAINMENT_MIN == 0.95


def test_in_frame_rows_clear_the_gate_and_still_fail_on_the_declaration():
    """Containment is a rejection, never a pass: image_px stays unscorable."""
    inside = _rows([0, 640, 1279] * 7, [0, 360, 719] * 7)
    with pytest.raises(CoordinateTransformUnavailable) as raised:
        normalize_tracking_frame(inside, sport="wnba")
    assert "image_px_containment" not in str(raised.value)
    assert "not accepted for sport wnba" in str(raised.value)


def test_off_frame_canvas_rows_are_rejected_for_containment():
    """The measured basketball defect: map_2d pixels overflow the source frame."""
    canvas = _rows([1, 458, 1632, 3396], [25, 754, 1527, 1710])
    with pytest.raises(CoordinateTransformUnavailable) as raised:
        normalize_tracking_frame(canvas, sport="wnba")
    assert str(raised.value).startswith("image_px_containment: 0.2500 of 4")


def test_the_harness_reports_the_containment_reason_and_does_not_pass():
    report = evaluate(_rows([5000, 5001], [10, 11]), "wnba")
    assert not report.passed
    assert report.failures == [
        "coordinate_contract: " + report.failures[0].split("coordinate_contract: ")[1]]
    assert "image_px_containment" in report.failures[0]


def test_a_missing_or_zero_dimension_counts_as_outside():
    """A point that cannot be checked has not been shown to be in the plane."""
    with pytest.raises(CoordinateTransformUnavailable) as raised:
        normalize_tracking_frame(_rows([10, 10], [10, 10], width=0, height=0),
                                 sport="wnba")
    assert "image_px_containment: 0.0000" in str(raised.value)


def test_a_table_without_declared_dimensions_keeps_the_old_rejection():
    """No dimensions means no gate: the declaration check still rejects it."""
    with pytest.raises(CoordinateTransformUnavailable) as raised:
        normalize_tracking_frame(_rows([9999], [9999], width=None), sport="wnba")
    assert "image_px_containment" not in str(raised.value)


def test_court_rows_are_not_graded_against_a_pixel_frame():
    court = _rows([10.0, 20.0], [10.0, 20.0], space="court_feet")
    assert normalize_tracking_frame(court, sport="wnba") is court
