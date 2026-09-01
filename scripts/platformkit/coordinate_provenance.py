"""Shared CSV contract for preserved image-space tracking observations."""
from pathlib import Path
from typing import Sequence, Union

import pandas as pd

PROVENANCE_COLUMNS = ("coordinate_space", "observation", "calibration")
IMAGE_SCHEMA = ("frame", "track_id", "cls", "x", "y") + PROVENANCE_COLUMNS
COORDINATE_SPACE, OBSERVATION, CALIBRATION = PROVENANCE_COLUMNS
IMAGE_COORDINATE_SPACE, OBSERVED, NO_CALIBRATION = "image_px", "observed", "none"
ALLOWED_COORDINATE_SPACES = frozenset((IMAGE_COORDINATE_SPACE,))
ALLOWED_OBSERVATIONS = frozenset((OBSERVED,))
ALLOWED_CALIBRATIONS = frozenset((NO_CALIBRATION,))


def stamp_image_space_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Return rows with complete source-pixel provenance."""
    result = rows.copy()
    result.loc[:, COORDINATE_SPACE] = IMAGE_COORDINATE_SPACE
    result.loc[:, OBSERVATION] = OBSERVED
    result.loc[:, CALIBRATION] = NO_CALIBRATION
    return result


def output_columns(base_columns: tuple[str, ...], rows: pd.DataFrame) -> tuple[str, ...]:
    """Select base schema or its complete provenance extension."""
    return base_columns + PROVENANCE_COLUMNS if COORDINATE_SPACE in rows.columns else base_columns


def write_tracking_csv(rows: pd.DataFrame, path: Union[str, Path],
                       schema: Sequence[str]) -> None:
    """Write a tracking table without permitting partial provenance."""
    columns = IMAGE_SCHEMA if "coordinate_space" in rows.columns else tuple(schema)
    missing = [column for column in columns if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, columns].to_csv(path, index=False)
