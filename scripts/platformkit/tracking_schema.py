"""Closed-world adapters for tracking tables accepted by the quality harness.

The normalized contract is ``cls, frame, track_id, x, y``. NBA production CSVs
contain one row per detected player, so their rows become ``cls=player``. Their
``ball_x2d``/``ball_y2d`` fields are per-player auxiliary values, not ball
observations, and therefore are deliberately not converted into ball rows.
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


def normalize_tracking_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a normalized tracking table for one explicitly recognized schema."""
    schema = identify_tracking_schema(df)
    if schema is _NORMALIZED:
        return df
    return pd.DataFrame({
        "cls": "player",
        "frame": df["frame"],
        "track_id": df["player_id"],
        "x": df["x_position"],
        "y": df["y_position"],
    })
