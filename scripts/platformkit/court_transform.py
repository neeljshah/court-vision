"""Court-feet transform for NBA production tracking, via a persisted sidecar.

The NBA production writer emits ``x_position/y_position`` in ``map_2d`` pixel
space.  ``map_2d`` is a resize of the rectified panorama, whose extent is the
panorama's -- not the court's -- so the court occupies an unknown sub-quad of
it.  ``ft_x/ft_y`` in the CSV are a per-axis independent rescale of that pixel
space (``ft_x == 94 * x_norm`` to rounding, measured over 60 games), which is a
court coordinate only if ``map_2d`` spans exactly the 94x50 court.  It does
not, so those columns are not court feet and are not used here.

The missing anchor is the residual ``map_2d -> court feet`` homography.  It is
computable only at rectification time, from the detected court quad, and is
currently discarded.  This module reads it from a sidecar that the pipeline
must persist (see docs/research/organization-sprint/
PROPOSED-court-calibration-sidecar.md) and fails closed when it is absent or
not evidenced.

Zero sidecars exist on the 354-game local corpus as of 2026-09-01, so every
production game keeps failing closed today.  Only games re-run after the
proposed src/ change lands become eligible; the existing corpus cannot be
retro-fixed, because the detected corners were never persisted.

The court rectangle is NEVER inferred from player-position density.  That
produces plausible-looking coordinates that cannot be falsified, which is the
exact failure mode this contract exists to prevent.
"""
from __future__ import annotations

import json
import os
from typing import Any, Mapping

import numpy as np
import pandas as pd

from scripts.platformkit.tracking_schema import CoordinateTransformUnavailable

__all__ = [
    "COURT_CALIBRATION_FLOOR",
    "SIDECAR_NAME",
    "CoordinateTransformUnavailable",
    "load_court_calibration",
    "to_court_feet",
]

SIDECAR_NAME = "court_calibration.json"

#: Minimum ``calibrated_frames / total_frames`` accepted.
#:
#: Justified against the measured per-game frame-level ``homography_valid``
#: distribution on the local corpus (60 games sampled 2026-09-01): the mean
#: ranges 0.470 to 0.983 per game.  0.90 admits roughly the upper half of that
#: distribution and rejects games whose court plane was unresolved for a large
#: minority of frames.  It is a fail-closed floor on an as-yet-unpopulated
#: field, not a tuned threshold -- revisit once sidecars exist and the
#: calibrated-fraction distribution can be measured directly.
COURT_CALIBRATION_FLOOR = 0.90

#: Only this value is trusted.  Whitelist, not blacklist: an unknown or absent
#: source is rejected exactly like the known-bad "fallback_default", so a new
#: fallback branch added upstream cannot silently pass.
_TRUSTED_SOURCE = "detected"

#: Maximum accepted court-landmark reprojection error, in feet.
#:
#: This field is what makes the contract falsifiable, and it is required.
#: The detected quad is stretched to fill the whole map_2d rectangle by
#: construction (rectify_court.homography maps the four detected corners onto
#: the four corners of the destination rect), so a transform *derived from that
#: same quad* re-describes the data perfectly no matter how wrong the quad is:
#: every point lands inside 0..94 x 0..50 and the harness ``oob`` gate can never
#: fire.  That is exactly the tautological-gate shape this contract exists to
#: prevent.  The only way a sidecar can carry real evidence is an INDEPENDENT
#: check -- measured court landmarks (center circle, three-point arc, free-throw
#: line) reprojected through the transform and compared against their known
#: positions on a regulation floor.  A sidecar without that number is rejected.
#:
#: NOT MEASURED: no sidecar exists yet, so this bound is a declared engineering
#: limit, not a fitted one.  Revisit once real reprojection errors exist.
MAX_REPROJECTION_ERROR_FT = 2.0

_MATRIX_KEY = "map2d_to_feet"
_ERROR_KEY = "court_reprojection_error_ft"


def _sidecar_path(source: str) -> str:
    """Resolve a game id, game directory, or CSV path to the sidecar path."""
    if source.endswith(".json"):
        return source
    if os.path.isdir(source):
        return os.path.join(source, SIDECAR_NAME)
    if source.endswith(".csv"):
        return os.path.join(os.path.dirname(source), SIDECAR_NAME)
    # Bare game id, resolved against the standard corpus layout.
    return os.path.join("data", "tracking", source, SIDECAR_NAME)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CoordinateTransformUnavailable(message)


def load_court_calibration(source: str) -> dict[str, Any]:
    """Load and validate a court-calibration sidecar, or fail closed.

    Args:
        source: A game id, a game directory, a ``tracking_data.csv`` path, or a
            direct path to the sidecar JSON.

    Returns:
        The validated sidecar mapping, with ``map2d_to_feet`` as a 3x3 array.

    Raises:
        CoordinateTransformUnavailable: The sidecar is absent, unreadable, not
            produced by real court detection, below the calibrated-frame floor,
            or carries a malformed transform.
    """
    path = _sidecar_path(source)
    if not os.path.exists(path):
        raise CoordinateTransformUnavailable(
            "no court calibration sidecar at {}; NBA production x_position/"
            "y_position are map_2d pixels and ft_x/ft_y are an image-affine "
            "rescale, so no court anchor is available".format(path)
        )
    try:
        with open(path, "r", encoding="utf-8") as handle:
            calib = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CoordinateTransformUnavailable(
            "unreadable court calibration sidecar {}: {}".format(path, exc)
        ) from exc
    _require(isinstance(calib, Mapping),
             "court calibration sidecar {} is not a JSON object".format(path))

    calibration_source = calib.get("calibration_source")
    _require(
        calibration_source == _TRUSTED_SOURCE,
        "court calibration_source is {!r}, not {!r}; the transform is not "
        "evidenced by real court-corner detection".format(
            calibration_source, _TRUSTED_SOURCE),
    )

    total = calib.get("total_frames")
    calibrated = calib.get("calibrated_frames")
    _require(
        isinstance(total, (int, float)) and isinstance(calibrated, (int, float))
        and total > 0,
        "court calibration sidecar {} lacks a usable calibrated_frames/"
        "total_frames pair".format(path),
    )
    fraction = float(calibrated) / float(total)
    _require(
        fraction >= COURT_CALIBRATION_FLOOR,
        "calibrated frame fraction {:.4f} < floor {:.2f}".format(
            fraction, COURT_CALIBRATION_FLOOR),
    )

    error_ft = calib.get(_ERROR_KEY)
    _require(
        isinstance(error_ft, (int, float)) and np.isfinite(float(error_ft))
        and float(error_ft) >= 0.0,
        "court calibration sidecar {} lacks a numeric {}; without an "
        "independent landmark reprojection error the transform re-describes "
        "its own quad and cannot be falsified".format(path, _ERROR_KEY),
    )
    _require(
        float(error_ft) <= MAX_REPROJECTION_ERROR_FT,
        "court landmark reprojection error {:.2f} ft > max {:.2f} ft".format(
            float(error_ft), MAX_REPROJECTION_ERROR_FT),
    )

    matrix = np.asarray(calib.get(_MATRIX_KEY), dtype=float)
    _require(matrix.shape == (3, 3),
             "court calibration {} must be a 3x3 matrix, got shape {}".format(
                 _MATRIX_KEY, matrix.shape))
    _require(bool(np.all(np.isfinite(matrix))),
             "court calibration {} contains non-finite values".format(_MATRIX_KEY))
    _require(abs(float(np.linalg.det(matrix))) > 1e-12,
             "court calibration {} is singular".format(_MATRIX_KEY))

    validated = dict(calib)
    validated[_MATRIX_KEY] = matrix
    validated["calibrated_fraction"] = fraction
    validated["sidecar_path"] = path
    return validated


def to_court_feet(df: pd.DataFrame, calib: Mapping[str, Any]) -> pd.DataFrame:
    """Project ``x_position/y_position`` (map_2d pixels) to court feet.

    Args:
        df: NBA production tracking rows.
        calib: A mapping from :func:`load_court_calibration`.

    Returns:
        A copy of ``df`` with canonical ``x``/``y`` columns in feet on the
        94x50 court.  Values are NOT clamped: an out-of-bounds projection is
        real evidence of a bad transform and must stay visible to the harness.

    Raises:
        CoordinateTransformUnavailable: Required columns are missing, or the
            transform sends points to the line at infinity.
    """
    missing = {"x_position", "y_position"} - set(df.columns)
    _require(not missing,
             "cannot project to court feet without {}".format(sorted(missing)))

    matrix = np.asarray(calib[_MATRIX_KEY], dtype=float)
    points = np.column_stack((
        df["x_position"].to_numpy(dtype=float),
        df["y_position"].to_numpy(dtype=float),
        np.ones(len(df)),
    ))
    projected = points @ matrix.T
    w = projected[:, 2]
    _require(bool(np.all(np.isfinite(w))) and not bool(np.any(np.isclose(w, 0.0))),
             "court transform maps rows to the line at infinity")

    out = df.copy()
    out["x"] = projected[:, 0] / w
    out["y"] = projected[:, 1] / w
    return out
