"""Court-transform contract: exact round-trip, and fail-closed on weak evidence."""
from __future__ import annotations

import json

import cv2
import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.court_transform import (
    COURT_CALIBRATION_FLOOR,
    MAX_REPROJECTION_ERROR_FT,
    CoordinateTransformUnavailable,
    load_court_calibration,
    to_court_feet,
)
from scripts.platformkit.tracking_schema import normalize_tracking_frame

# A deliberately non-court-shaped, perspective-warped quad in map_2d pixels,
# standing in for a real detected court inside a rectified panorama.
QUAD_MAP2D = np.array(
    [[412.0, 233.0], [3180.0, 190.0], [3301.0, 1502.0], [285.0, 1571.0]],
    dtype=np.float32,
)
COURT_FEET = np.array(
    [[0.0, 0.0], [94.0, 0.0], [94.0, 50.0], [0.0, 50.0]], dtype=np.float32
)


def _sidecar(tmp_path, **overrides):
    matrix = cv2.getPerspectiveTransform(QUAD_MAP2D, COURT_FEET)
    payload = {
        "schema_version": 1,
        "game_id": "0022400625",
        "calibration_source": "detected",
        "calibrated_frames": 980,
        "total_frames": 1000,
        "map_width": 3404,
        "map_height": 1711,
        "court_quad_map2d": QUAD_MAP2D.tolist(),
        "court_reprojection_error_ft": 0.6,
        "map2d_to_feet": matrix.tolist(),
    }
    payload.update(overrides)
    path = tmp_path / "court_calibration.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _rows(points):
    return pd.DataFrame({
        "frame": range(len(points)),
        "timestamp": [0.0] * len(points),
        "player_id": range(len(points)),
        "team": ["HOME"] * len(points),
        "x_position": [p[0] for p in points],
        "y_position": [p[1] for p in points],
    })


def test_known_corners_round_trip_to_exact_court_feet(tmp_path):
    calib = load_court_calibration(str(_sidecar(tmp_path)))
    out = to_court_feet(_rows(QUAD_MAP2D), calib)
    assert np.allclose(out[["x", "y"]].to_numpy(), COURT_FEET, atol=1e-6)


def test_projection_is_unclamped_so_out_of_bounds_stays_visible(tmp_path):
    """A point outside the detected quad must project outside 94x50, not clamp."""
    calib = load_court_calibration(str(_sidecar(tmp_path)))
    out = to_court_feet(_rows([(100.0, 100.0)]), calib)
    assert out["x"].iloc[0] < 0.0 or out["y"].iloc[0] < 0.0


def test_missing_sidecar_raises(tmp_path):
    with pytest.raises(CoordinateTransformUnavailable, match="no court calibration"):
        load_court_calibration(str(tmp_path / "0022400625"))


def test_fallback_default_source_raises(tmp_path):
    path = _sidecar(tmp_path, calibration_source="fallback_default")
    with pytest.raises(CoordinateTransformUnavailable, match="not 'detected'"):
        load_court_calibration(str(path))


def test_unknown_source_raises_like_a_known_bad_one(tmp_path):
    """Whitelist, not blacklist: a new upstream fallback cannot silently pass."""
    path = _sidecar(tmp_path, calibration_source="some_future_fallback")
    with pytest.raises(CoordinateTransformUnavailable, match="not 'detected'"):
        load_court_calibration(str(path))


def test_below_floor_calibrated_fraction_raises(tmp_path):
    below = int(1000 * COURT_CALIBRATION_FLOOR) - 1
    path = _sidecar(tmp_path, calibrated_frames=below, total_frames=1000)
    with pytest.raises(CoordinateTransformUnavailable, match="calibrated frame fraction"):
        load_court_calibration(str(path))


def test_at_floor_calibrated_fraction_is_accepted(tmp_path):
    path = _sidecar(tmp_path, calibrated_frames=900, total_frames=1000)
    assert load_court_calibration(str(path))["calibrated_fraction"] == pytest.approx(0.9)


def test_missing_reprojection_error_raises(tmp_path):
    """No independent evidence -> the transform re-describes its own quad."""
    path = _sidecar(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["court_reprojection_error_ft"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CoordinateTransformUnavailable, match="reprojection error"):
        load_court_calibration(str(path))


def test_reprojection_error_above_bound_raises(tmp_path):
    path = _sidecar(tmp_path,
                    court_reprojection_error_ft=MAX_REPROJECTION_ERROR_FT + 0.1)
    with pytest.raises(CoordinateTransformUnavailable, match="reprojection error"):
        load_court_calibration(str(path))


def test_singular_matrix_raises(tmp_path):
    path = _sidecar(tmp_path, map2d_to_feet=[[1, 2, 3], [2, 4, 6], [0, 0, 1]])
    with pytest.raises(CoordinateTransformUnavailable, match="singular"):
        load_court_calibration(str(path))


def test_normalize_without_source_still_fails_closed():
    """The default path is unchanged: no sidecar argument, no transform."""
    with pytest.raises(CoordinateTransformUnavailable, match="image pixels"):
        normalize_tracking_frame(_rows(QUAD_MAP2D))


def test_normalize_with_sidecar_yields_canonical_court_columns(tmp_path):
    _sidecar(tmp_path)
    out = normalize_tracking_frame(_rows(QUAD_MAP2D), str(tmp_path))
    assert np.allclose(out[["x", "y"]].to_numpy(), COURT_FEET, atol=1e-6)
    assert set(out["cls"]) == {"player"}
    assert out["track_id"].tolist() == out["player_id"].tolist()


def test_real_corpus_game_has_no_sidecar_and_fails_closed():
    """Provable statement about today's corpus: zero sidecars, so zero unblocked."""
    with pytest.raises(CoordinateTransformUnavailable):
        load_court_calibration("data/tracking/0022400625/tracking_data.csv")
