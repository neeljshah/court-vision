"""A declaration of image_px must be checkable against the real frame."""
import pandas as pd
import pytest

from scripts.platformkit.tracking.image_px_containment import (
    NOT_APPLICABLE,
    containment,
)


def _rows(xs, ys, space="image_px"):
    frame = pd.DataFrame({"frame": range(len(xs)), "track_id": 1, "cls": "player",
                          "x": xs, "y": ys})
    if space is not None:
        frame["coordinate_space"] = space
    return frame


def test_points_inside_the_decoded_frame_pass():
    result = containment(_rows([0, 640, 1279], [0, 360, 719]), 1280, 720)
    assert (result.verdict, result.n_inside, result.inside_share) == ("PASS", 3, 1.0)


def test_points_on_a_derived_canvas_fail():
    """The measured basketball defect: x/y are map_2d canvas pixels, so they
    overflow a 1280x720 source frame and land on nothing in the image."""
    result = containment(_rows([1, 458, 1632], [25, 754, 1527]), 1280, 720)
    assert result.verdict == "FAIL"
    assert result.n_inside == 1 and result.n_rows == 3
    assert (result.max_x, result.max_y) == (1632.0, 1527.0)


def test_court_declared_and_undeclared_rows_are_not_scored_here():
    """This check only speaks about image_px; a court table is another gate's
    business and must not be silently graded against a pixel frame."""
    assert containment(_rows([1, 2], [1, 2], "court_feet"), 1280, 720).verdict == NOT_APPLICABLE
    assert containment(_rows([1, 2], [1, 2], None), 1280, 720).verdict == NOT_APPLICABLE


def test_mixed_table_scores_only_its_image_px_rows():
    mixed = _rows([10, 5000], [10, 10])
    mixed.loc[1, "coordinate_space"] = "court_feet"
    result = containment(mixed, 1280, 720)
    assert (result.n_rows, result.n_inside, result.verdict) == (1, 1, "PASS")


def test_a_resolution_must_be_measured_not_assumed():
    with pytest.raises(ValueError):
        containment(_rows([1], [1]), 0, 720)
