"""Tests for shared coordinate-space provenance."""
import pandas as pd

from scripts.platformkit.coordinate_provenance import (
    ALLOWED_CALIBRATIONS, ALLOWED_COORDINATE_SPACES, ALLOWED_OBSERVATIONS,
    PROVENANCE_COLUMNS, output_columns, stamp_image_space_rows,
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
    assert output_columns(base, pd.DataFrame(columns=base + ("coordinate_space",))) == base + PROVENANCE_COLUMNS
