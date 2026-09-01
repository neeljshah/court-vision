"""The coordinate_space declaration decides scorability, not the magnitudes."""
import pandas as pd
import pytest

from scripts.platformkit.tracking_harness import evaluate
from scripts.platformkit.tracking_schema import (
    CoordinateTransformUnavailable,
    normalize_tracking_frame,
)


def _rows(space=None, scale=1.0):
    frame = pd.DataFrame({
        "frame": [1, 1, 2, 2],
        "track_id": [1, 2, 1, 2],
        "cls": ["player"] * 4,
        "x": [10.0 * scale, 20.0 * scale, 11.0 * scale, 21.0 * scale],
        "y": [10.0 * scale, 20.0 * scale, 11.0 * scale, 21.0 * scale],
    })
    if space is not None:
        frame["coordinate_space"] = space
    return frame


def test_image_space_rows_inside_the_sport_bounds_still_fail_closed():
    """The regression test for the ft_x/ft_y defect: pixels rescaled into the
    court bounds pass every magnitude gate, so only the declaration can stop
    them."""
    inside_bounds = _rows("image_px")
    assert inside_bounds["x"].between(0, 94).all()
    assert inside_bounds["y"].between(0, 50).all()
    with pytest.raises(CoordinateTransformUnavailable):
        normalize_tracking_frame(inside_bounds)
    report = evaluate(inside_bounds, "basketball")
    assert not report.passed
    assert len(report.failures) == 1
    assert report.failures[0].startswith("coordinate_contract: ")
    assert "image_px" in report.failures[0]


def test_absent_column_fails_closed_unless_legacy_switch_is_explicit():
    """An omitted declaration must NOT be read as "assume court coordinates"
    (commit de124527e). Only the explicit allow_legacy_undeclared switch may
    recover the declared-court-space behavior for an audited legacy corpus."""
    legacy = evaluate(_rows(), "basketball")
    declared = evaluate(_rows("court_feet"), "basketball")
    assert legacy.failures[0].startswith("coordinate_contract: rows omit coordinate_space")
    assert not any(f.startswith("coordinate_contract") for f in declared.failures)
    legacy_allowed = evaluate(_rows(), "basketball", allow_legacy_undeclared=True)
    assert legacy_allowed.failures == declared.failures


def test_unrecognized_and_null_declarations_fail_closed():
    for value in ("court_pixels", "", float("nan")):
        with pytest.raises(CoordinateTransformUnavailable):
            normalize_tracking_frame(_rows(value))
    mixed = _rows("court_feet")
    mixed.loc[0, "coordinate_space"] = "image_px"
    with pytest.raises(CoordinateTransformUnavailable):
        normalize_tracking_frame(mixed)
