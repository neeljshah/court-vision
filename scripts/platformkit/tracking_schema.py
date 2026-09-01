"""Fail-closed coordinate contract for tracking tables.

The canonical columns ``x`` and ``y`` are sport-surface coordinates in the
declared native unit: basketball uses feet on ``[0, 94] x [0, 50]``.  Other
adapters likewise emit their documented field/court units.  Pixel positions
are never accepted as normalized coordinates.

The NBA production writer emits image pixels in ``x_position/y_position`` and
image fractions in ``x_norm/y_norm``.  Its ``ft_x/ft_y`` are an affine image
scaling, not a court homography.  No per-frame image-to-court transform is
persisted, so this source must fail closed until one is supplied.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

NORMALIZED_COLUMNS = frozenset({"cls", "frame", "track_id", "x", "y"})
NBA_PRODUCTION_COLUMNS = frozenset(
    {"frame", "timestamp", "player_id", "team", "x_position", "y_position"}
)


@dataclass(frozen=True)
class TrackingSchema:
    """Schema identity and whether ball coverage can be evaluated."""

    name: str
    ball_telemetry_available: bool


_NORMALIZED = TrackingSchema("normalized", True)
_NBA_PRODUCTION = TrackingSchema("nba_production_player_rows", False)


class CoordinateTransformUnavailable(ValueError):
    """Raised when a recognized producer lacks an evidenced court transform."""


_NBA_NO_TRANSFORM = (
    "NBA production tracking uses image pixels in x_position/y_position; "
    "x_norm/y_norm and ft_x/ft_y are image-affine values, and no persisted "
    "per-frame homography or equivalent court anchor is available"
)


CANONICAL_COORDINATE_CONTRACT = {
    "columns": ("cls", "frame", "track_id", "x", "y"),
    "basketball": {"unit": "feet", "bounds": (0.0, 94.0, 0.0, 50.0)},
    "rule": "x/y must already be a declared sport-surface coordinate system",
}


def identify_tracking_schema(df: pd.DataFrame) -> TrackingSchema:
    """Identify a supported schema or fail without inferring column meaning."""
    columns = frozenset(df.columns)
    if NORMALIZED_COLUMNS <= columns:
        return _NORMALIZED
    if NBA_PRODUCTION_COLUMNS <= columns:
        return _NBA_PRODUCTION
    found = ", ".join(sorted(columns)) or "(no columns)"
    raise ValueError(
        "unrecognized tracking schema; expected normalized columns "
        "{cls, frame, track_id, x, y} or NBA production columns "
        "{frame, timestamp, player_id, team, x_position, y_position}; found "
        + found
    )


def normalize_tracking_frame(df: pd.DataFrame,
                             source: str | None = None) -> pd.DataFrame:
    """Return canonical coordinates or reject a source with no valid transform.

    Declared transforms:
    - normalized schema: identity; domain adapters project detections before CSV.
    - NBA production schema: requires a persisted court-calibration sidecar
      resolved from ``source``.  Without one -- the state of every game in the
      corpus today -- this fails closed, because the persisted values are
      image-space only.

    Args:
        df: A recognized tracking table.
        source: Optional game id, game directory, or CSV path used to locate a
            ``court_calibration.json`` sidecar.  When omitted, the NBA
            production branch always fails closed.
    """
    schema = identify_tracking_schema(df)
    if schema is _NORMALIZED:
        return df
    if source is None:
        raise CoordinateTransformUnavailable(_NBA_NO_TRANSFORM)
    # Deferred import: court_transform imports this module's exception type.
    from scripts.platformkit.court_transform import (
        load_court_calibration,
        to_court_feet,
    )
    out = to_court_feet(df, load_court_calibration(source))
    # player_id is the track identity and every production row is a player
    # detection; the ball rides in ball_x2d/ball_y2d columns, which is why this
    # schema declares ball telemetry unavailable.
    out["track_id"] = out["player_id"]
    out["cls"] = "player"
    return out
