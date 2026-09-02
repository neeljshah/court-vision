"""Shared CSV contract for tracking-coordinate provenance."""
from pathlib import Path
from typing import Sequence, Union

import pandas as pd

PROVENANCE_COLUMNS = ("coordinate_space", "observation", "calibration")
IMAGE_SCHEMA = ("frame", "track_id", "cls", "x", "y") + PROVENANCE_COLUMNS
COORDINATE_SPACE, OBSERVATION, CALIBRATION = PROVENANCE_COLUMNS
IMAGE_COORDINATE_SPACE, OBSERVED, NO_CALIBRATION = "image_px", "observed", "none"
# A court adapter that solved a real homography for the frame it is reporting.
HOMOGRAPHY = "homography"
COURT_FEET, PITCH_METRES, METRIC_LOCAL = "court_feet", "pitch_metres", "metric_local"
METRIC_LOCAL_CALIBRATION = "mound_lateral_px_per_ft"
ALLOWED_COORDINATE_SPACES = frozenset(
    (IMAGE_COORDINATE_SPACE, COURT_FEET, PITCH_METRES, METRIC_LOCAL)
)
ALLOWED_OBSERVATIONS = frozenset((OBSERVED,))
ALLOWED_CALIBRATIONS = frozenset((NO_CALIBRATION, HOMOGRAPHY, METRIC_LOCAL_CALIBRATION))
SPORT_COORDINATE_SPACES = {
    "basketball": frozenset((COURT_FEET,)), "wnba": frozenset((COURT_FEET,)),
    "tennis": frozenset((COURT_FEET,)), "soccer": frozenset((PITCH_METRES,)),
    "baseball": frozenset((COURT_FEET,)), "npb": frozenset((COURT_FEET,)),
    "kbo": frozenset((COURT_FEET,)), "football": frozenset((COURT_FEET,)),
}
# Metric-local rows are a distinct profile, never a court-coordinate alias.
SPORT_METRIC_LOCAL_SPACES = {
    sport: frozenset((METRIC_LOCAL,)) for sport in ("baseball", "npb", "kbo")
}


def _stamp(rows: pd.DataFrame, space: str, calibration: str) -> pd.DataFrame:
    """Attach the three provenance columns, including to an EMPTY frame.

    An empty result is a real and common outcome -- a clip where nothing was
    detected, or where calibration never solved. Assigning a scalar to a frame
    with no index raises, so an empty table would lose its declaration and then
    be rejected as undeclared rather than reported as legitimately empty.
    """
    result = rows.copy()
    if result.empty:
        for column, value in ((COORDINATE_SPACE, space), (OBSERVATION, OBSERVED),
                              (CALIBRATION, calibration)):
            result[column] = pd.Series(dtype="object")
        return result
    result.loc[:, COORDINATE_SPACE] = space
    result.loc[:, OBSERVATION] = OBSERVED
    result.loc[:, CALIBRATION] = calibration
    return result


def stamp_image_space_rows(rows: pd.DataFrame) -> pd.DataFrame:
    """Return rows with complete source-pixel provenance."""
    return _stamp(rows, IMAGE_COORDINATE_SPACE, NO_CALIBRATION)


def stamp_court_space_rows(rows: pd.DataFrame, sport: str) -> pd.DataFrame:
    """Declare rows as this sport's court coordinates.

    Court adapters must declare too, not just image ones. Scoring is strict
    about undeclared tables precisely because an omitted declaration is how
    pixels got laundered into court units; leaving legitimate court output
    undeclared would just move the ambiguity rather than remove it.
    """
    spaces = SPORT_COORDINATE_SPACES.get(sport)
    if not spaces:
        raise ValueError("no court coordinate space declared for sport: %s" % sport)
    return _stamp(rows, sorted(spaces)[0], HOMOGRAPHY)


def output_columns(base_columns: tuple[str, ...], rows: pd.DataFrame) -> tuple[str, ...]:
    """Select base schema or require its complete provenance extension."""
    declared = set(PROVENANCE_COLUMNS).intersection(rows.columns)
    if declared and declared != set(PROVENANCE_COLUMNS):
        missing = [column for column in PROVENANCE_COLUMNS if column not in rows.columns]
        raise ValueError("Tracking rows have partial provenance; missing columns: %s" %
                         ", ".join(missing))
    return base_columns + PROVENANCE_COLUMNS if declared else base_columns


def write_tracking_csv(rows: pd.DataFrame, path: Union[str, Path],
                       schema: Sequence[str]) -> None:
    """Write a tracking table without permitting partial provenance."""
    columns = output_columns(tuple(schema), rows)
    missing = [column for column in columns if column not in rows.columns]
    if missing:
        raise ValueError("Tracking rows missing columns: %s" % ", ".join(missing))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.loc[:, columns].to_csv(path, index=False)
