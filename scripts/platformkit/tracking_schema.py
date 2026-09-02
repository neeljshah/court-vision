"""Fail-closed coordinate contract for tracking tables.

The canonical columns ``x`` and ``y`` are sport-surface coordinates in the
declared native unit: basketball uses feet on ``[0, 94] x [0, 50]``.  Other
adapters likewise emit their documented field/court units.  Pixel positions
are never accepted as normalized coordinates.

The NBA production writer emits image pixels in ``x_position/y_position`` and
image fractions in ``x_norm/y_norm``.  Its ``ft_x/ft_y`` are an affine image
scaling, not a court homography.  No per-frame image-to-court transform is
persisted, so this source must fail closed until one is supplied.

New scoring requires ``coordinate_space``: a numeric range cannot distinguish
court coordinates from pixels rescaled into that range. Historical court CSVs
without provenance remain readable only through the explicit
``allow_legacy_undeclared`` compatibility switch. That keeps an audited legacy
corpus usable without letting a new producer omit its declaration by accident.
Remove the switch only after the corpus is backfilled with recorded provenance
and every writer has emitted the full columns for one retention cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil

import pandas as pd

from scripts.platformkit.coordinate_provenance import (
    METRIC_LOCAL,
    METRIC_LOCAL_CALIBRATION,
    SPORT_COORDINATE_SPACES,
    SPORT_METRIC_LOCAL_SPACES,
)

NORMALIZED_COLUMNS = frozenset({"cls", "frame", "track_id", "x", "y"})
NBA_PRODUCTION_COLUMNS = frozenset(
    {"frame", "timestamp", "player_id", "team", "x_position", "y_position"}
)

# A declaration identifies what x/y are. Image pixels are a preserved corpus,
# never a scorable game.
COORDINATE_SPACE_COLUMN = "coordinate_space"
COURT_SPACES = frozenset().union(*SPORT_COORDINATE_SPACES.values())
IMAGE_SPACE = "image_px"

# The decoded frame size, written by the producer alongside the rows it decoded.
FRAME_WIDTH_COLUMN, FRAME_HEIGHT_COLUMN = "frame_width", "frame_height"
# Share of declared image_px points that must land inside the decoded frame.
IMAGE_PX_CONTAINMENT_MIN = 0.95


@dataclass(frozen=True)
class TrackingSchema:
    """Schema identity and whether ball coverage can be evaluated."""

    name: str
    ball_telemetry_available: bool | None
    ball_telemetry_rule: str


_NBA_PRODUCTION = TrackingSchema("nba_production_player_rows", False,
                                 "nba_production_schema")
_CAPABILITY_FILE = "tracking_capability.json"


class CoordinateTransformUnavailable(ValueError):
    """Raised when a recognized producer lacks an evidenced court transform."""


_NBA_NO_TRANSFORM = (
    "NBA production tracking uses image pixels in x_position/y_position; "
    "x_norm/y_norm and ft_x/ft_y are image-affine values, and no persisted "
    "per-frame homography or equivalent court anchor is available"
)


_UNDECLARED_SPACE = (
    "rows omit coordinate_space; coordinate declarations are required for scoring "
    "unless allow_legacy_undeclared=True is used for an audited historical corpus"
)


CANONICAL_COORDINATE_CONTRACT = {
    "columns": ("cls", "frame", "track_id", "x", "y"),
    "basketball": {"unit": "feet", "bounds": (0.0, 94.0, 0.0, 50.0)},
    "rule": "x/y must already be a declared sport-surface coordinate system",
    "coordinate_space": {
        "column": COORDINATE_SPACE_COLUMN,
        "scorable": tuple(sorted(COURT_SPACES)),
        "corpus_only": (IMAGE_SPACE,),
        "absent": "fails unless explicit audited legacy compatibility is requested",
        "rule": "any other value, including null, fails closed",
    },
}


def _validate_image_px_containment(df: pd.DataFrame) -> None:
    """A table declaring image_px must lie in the source image plane.

    The declaration check below is magnitude-blind on purpose, so it cannot see
    the difference between the decoded frame and a derived canvas.  That is how
    103,009 basketball rows shipped carrying map_2d minimap pixels under an
    ``image_px`` label: every contract check passed on the declaration alone
    while 76.8% of the points fell outside their own frame.

    Checkable only when the producer declares the frame size it decoded, which
    is why the fixed producer now writes ``frame_width``/``frame_height``.  A
    table without those columns is left to the declaration check, which already
    rejects image_px as unscorable -- this gate adds a rejection, never a pass.
    """
    if COORDINATE_SPACE_COLUMN not in df.columns:
        return
    declared = df[df[COORDINATE_SPACE_COLUMN] == IMAGE_SPACE]
    dimensions = {FRAME_WIDTH_COLUMN, FRAME_HEIGHT_COLUMN}
    if declared.empty or not dimensions <= set(df.columns):
        return
    numeric = {name: pd.to_numeric(declared[name], errors="coerce")
               for name in ("x", "y", FRAME_WIDTH_COLUMN, FRAME_HEIGHT_COLUMN)}
    width, height = numeric[FRAME_WIDTH_COLUMN], numeric[FRAME_HEIGHT_COLUMN]
    x, y = numeric["x"], numeric["y"]
    # An unusable or missing dimension counts as outside: a point that cannot be
    # checked has not been shown to be in the image plane.
    inside = ((width > 0) & (height > 0)
              & (x >= 0) & (x <= width - 1) & (y >= 0) & (y <= height - 1))
    share = float(inside.sum()) / len(declared)
    if share < IMAGE_PX_CONTAINMENT_MIN:
        raise CoordinateTransformUnavailable(
            "image_px_containment: {:.4f} of {} declared image_px points lie "
            "inside the decoded frame, below {:.2f}; x/y are not source-image "
            "pixels".format(share, len(declared), IMAGE_PX_CONTAINMENT_MIN))


def _validate_coordinate_space(df: pd.DataFrame, sport: str | None,
                               allow_legacy_undeclared: bool) -> None:
    """Fail closed unless a declared surface space belongs to this sport.

    Magnitude-independent by design: rescaling pixels into the sport bounds
    makes the harness bound checks pass, which is exactly how image-affine
    ft_x/ft_y were once read as court feet.  The declaration decides, not the
    numbers.
    """
    if COORDINATE_SPACE_COLUMN not in df.columns:
        if not allow_legacy_undeclared:
            raise CoordinateTransformUnavailable(_UNDECLARED_SPACE)
        return
    _validate_image_px_containment(df)
    declared = {"(null)" if pd.isna(value) else str(value)
                for value in df[COORDINATE_SPACE_COLUMN].unique()}
    accepted = (SPORT_COORDINATE_SPACES.get(sport, frozenset())
                | SPORT_METRIC_LOCAL_SPACES.get(sport, frozenset()))
    offending = sorted(declared - accepted)
    if offending:
        raise CoordinateTransformUnavailable(
            "rows declare coordinate_space {} not accepted for sport {}; "
            "a preserved detection corpus is never a scorable game".format(
                ", ".join(offending), sport or "(unspecified)"
            )
        )
    if declared == {METRIC_LOCAL}:
        calibrations = {"(null)" if pd.isna(value) else str(value)
                        for value in df.get("calibration", pd.Series(dtype="object")).unique()}
        if calibrations != {METRIC_LOCAL_CALIBRATION}:
            raise CoordinateTransformUnavailable(
                "metric_local rows require calibration {}; found {}".format(
                    METRIC_LOCAL_CALIBRATION, ", ".join(sorted(calibrations)) or "(absent)"
                )
            )


def write_ball_telemetry_declaration(output_path: str | Path, sport: str,
                                     available: bool) -> None:
    """Persist an adapter's ball-telemetry capability beside its tracking CSV."""
    if type(available) is not bool:
        raise ValueError("ball telemetry declaration must be boolean")
    destination = Path(output_path).parent / _CAPABILITY_FILE
    destination.write_text(json.dumps({"sport": sport,
                                       "ball_telemetry_available": available}, indent=2)
                           + "\n", encoding="utf-8")


def copy_ball_telemetry_declaration(source_path: str | Path,
                                    output_path: str | Path) -> bool:
    """Copy an existing tracking capability sidecar to a re-emitted CSV."""
    source = Path(source_path).parent / _CAPABILITY_FILE
    if not source.is_file():
        return False
    destination = Path(output_path).parent / _CAPABILITY_FILE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


def _producer_ball_telemetry(source: str | None) -> bool | None:
    if source is None:
        return None
    source_path = Path(source)
    capability_path = (source_path.parent if source_path.suffix else source_path) / _CAPABILITY_FILE
    if not capability_path.is_file():
        return None
    payload = json.loads(capability_path.read_text(encoding="utf-8"))
    available = payload.get("ball_telemetry_available")
    if type(available) is not bool:
        raise ValueError("producer ball_telemetry_available must be boolean")
    return available


def identify_tracking_schema(df: pd.DataFrame,
                             source: str | None = None) -> TrackingSchema:
    """Identify a supported schema or fail without inferring column meaning."""
    columns = frozenset(df.columns)
    if NORMALIZED_COLUMNS <= columns:
        declared = _producer_ball_telemetry(source)
        if declared is not None:
            return TrackingSchema("normalized", declared, "producer_declaration")
        return TrackingSchema("normalized", None, "unknown_no_sidecar")
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
                             source: str | None = None,
                             sport: str | None = None,
                             allow_legacy_undeclared: bool = False) -> pd.DataFrame:
    """Return canonical coordinates or reject a source with no valid transform.

    Coordinate contract:
    - normalized rows require a coordinate space accepted for ``sport``. An
      undeclared historical corpus requires the explicit compatibility switch.
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
        sport: Sport whose declared coordinate space is being scored.
        allow_legacy_undeclared: Permit only an audited historical corpus that
            predates coordinate provenance.
    """
    schema = identify_tracking_schema(df, source)
    if schema.name == "normalized":
        _validate_coordinate_space(df, sport, allow_legacy_undeclared)
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
