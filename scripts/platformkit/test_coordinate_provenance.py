"""Tests for shared coordinate-space provenance."""
import pandas as pd
import pytest

from scripts.platformkit.coordinate_provenance import (
    ALLOWED_CALIBRATIONS, ALLOWED_COORDINATE_SPACES, ALLOWED_OBSERVATIONS,
    PROVENANCE_COLUMNS, output_columns, stamp_image_space_rows, write_tracking_csv,
)


def test_stamp_image_space_rows_adds_complete_allowed_provenance() -> None:
    rows = stamp_image_space_rows(pd.DataFrame([[1, 7, "player", 12.0, 24.0]], columns=("frame", "track_id", "cls", "x", "y")))
    assert tuple(rows.columns[-3:]) == PROVENANCE_COLUMNS
    assert set(rows.coordinate_space) <= ALLOWED_COORDINATE_SPACES
    assert set(rows.observation) <= ALLOWED_OBSERVATIONS
    assert set(rows.calibration) <= ALLOWED_CALIBRATIONS


def test_output_columns_requires_complete_provenance_when_declared() -> None:
    base = ("frame", "track_id", "cls", "x", "y")
    assert output_columns(base, pd.DataFrame(columns=base)) == base
    with pytest.raises(ValueError, match="partial provenance"):
        output_columns(base, pd.DataFrame(columns=base + ("coordinate_space",)))


def test_writer_rejects_partial_provenance_instead_of_dropping_it(tmp_path) -> None:
    rows = pd.DataFrame([[1, 7, "player", 12.0, 24.0, "interpolated"]],
                        columns=("frame", "track_id", "cls", "x", "y", "observation"))

    with pytest.raises(ValueError, match="partial provenance"):
        write_tracking_csv(rows, tmp_path / "rows.csv", ("frame", "track_id", "cls", "x", "y"))


def test_empty_results_keep_their_declaration():
    """An empty result is a real outcome -- nothing detected, or calibration
    never solved. Assigning a scalar to a frame with no index raises, so an
    empty table would silently lose its declaration and then be rejected as
    undeclared rather than reported as legitimately empty."""
    import pandas as pd

    from scripts.platformkit.coordinate_provenance import (
        PROVENANCE_COLUMNS, stamp_court_space_rows, stamp_image_space_rows)

    empty = pd.DataFrame(columns=["frame", "track_id", "cls", "x", "y"])

    for stamped in (stamp_court_space_rows(empty, "tennis"),
                    stamp_image_space_rows(empty)):
        assert set(PROVENANCE_COLUMNS) <= set(stamped.columns)
        assert len(stamped) == 0


def test_court_space_is_per_sport():
    from scripts.platformkit.coordinate_provenance import stamp_court_space_rows
    import pandas as pd

    row = pd.DataFrame({"frame": [1], "track_id": [1], "cls": ["player"],
                        "x": [1.0], "y": [2.0]})

    assert stamp_court_space_rows(row, "tennis")["coordinate_space"][0] == "court_feet"
    assert stamp_court_space_rows(row, "soccer")["coordinate_space"][0] == "pitch_metres"
