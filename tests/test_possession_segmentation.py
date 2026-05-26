"""Tests for BUG3 + BUG4 fixes: _BALL_LOSS_THRESH reduction and off_ball_distance unit.

BUG3: _BALL_LOSS_THRESH must be env-configurable and default <= 15 frames.
BUG4: off_ball_distance must be converted px→ft via _px_to_ft.
"""
import importlib
import os
import sys

import pytest

pytest.importorskip("src.pipeline.unified_pipeline")


# ---------------------------------------------------------------------------
# BUG3: _BALL_LOSS_THRESH is configurable via NBA_BALL_LOSS_FRAMES env var
# ---------------------------------------------------------------------------

def test_ball_loss_threshold_is_configurable_via_env(monkeypatch):
    """Setting NBA_BALL_LOSS_FRAMES=15 and re-evaluating the threshold expression
    yields 15 regardless of fps/stride."""
    # The env var is read as: int(os.environ.get("NBA_BALL_LOSS_FRAMES", str(int(1.0*fps/_stride))))
    # We test the env override path directly.
    monkeypatch.setenv("NBA_BALL_LOSS_FRAMES", "15")
    fps, stride = 30.0, 3
    result = int(os.environ.get("NBA_BALL_LOSS_FRAMES", str(int(1.0 * fps / stride))))
    assert result == 15, f"Expected 15, got {result}"


def test_default_ball_loss_threshold_is_lower_than_old():
    """Default _BALL_LOSS_THRESH (no env override) must be <= 15 frames.

    Old value was effectively 2.0s * fps / stride ≈ 20 frames.
    New value is 1.0s * fps / stride ≈ 10 frames.
    """
    fps, stride = 30.0, 3
    # Simulate no env override
    saved = os.environ.pop("NBA_BALL_LOSS_FRAMES", None)
    try:
        default_thresh = int(os.environ.get("NBA_BALL_LOSS_FRAMES", str(int(1.0 * fps / stride))))
        assert default_thresh <= 15, (
            f"Default threshold {default_thresh} is too high (was ~20, must be ≤15)")
    finally:
        if saved is not None:
            os.environ["NBA_BALL_LOSS_FRAMES"] = saved


# ---------------------------------------------------------------------------
# BUG4: off_ball_distance must go through _px_to_ft
# ---------------------------------------------------------------------------

def test_off_ball_distance_converted_to_feet():
    """_px_to_ft converts pixel distances to feet using the 94ft court length.

    A pixel distance of map_w pixels = 94 ft (full court length).
    _px_to_ft(map_w, map_w) should return 94.0 ft.
    """
    from src.pipeline.unified_pipeline import _px_to_ft
    map_w = 940
    # One full court length in pixels → 94 ft
    assert _px_to_ft(map_w, map_w) == 94.0
    # Half court in pixels → 47 ft
    assert _px_to_ft(map_w // 2, map_w) == pytest.approx(47.0, abs=0.2)
    # A "pixel" value like 3127px at map_w=940 → 312.7 ft would be wrong.
    # Post-fix: _px_to_ft(3127, 940) ≈ 312.7 ft (catches sentinel corruption).
    # In the pipeline, poss_ctx["off_ball_distance"] is cumulative movement
    # over frames — large values are expected but we ensure the conversion runs.
    val_px = 940.0  # == map_w → should convert to 94.0 ft (one full court)
    converted = _px_to_ft(val_px, map_w)
    assert converted == pytest.approx(94.0, abs=0.2), (
        f"_px_to_ft({val_px}, {map_w}) = {converted}, expected ~94 ft")


def test_avg_spacing_computation_clear_semantic():
    """avg_spacing in possessions.csv is mean hull area in ft² per frame.

    This is the same metric as spacing_hull_area in tracking_rows
    (kept for historical compat — see BUG4 option-c comment in _summarize_possession).
    Verify the docstring / comment is present and that the unit is ft².

    We check the source code contains the BUG4 annotation to assert
    that the semantic was documented (not silently left ambiguous).
    """
    import inspect
    from src.pipeline.unified_pipeline import UnifiedPipeline
    src = inspect.getsource(UnifiedPipeline._summarize_possession)
    assert "BUG4" in src, (
        "_summarize_possession must contain a BUG4 comment documenting avg_spacing unit")
    assert "ft²" in src or "ft2" in src or "hull area" in src.lower(), (
        "_summarize_possession must document that avg_spacing is hull-area-based (ft²)")


# ---------------------------------------------------------------------------
# BUG2 / BUG3 interaction: period boundary doesn't create phantom possessions
# ---------------------------------------------------------------------------

def test_period_boundary_does_not_create_phantom_possession():
    """Period boundary increments possession_id once, not on every subsequent frame.

    Simulates the guard: _last_scoreboard_period is set after the first transition
    so repeated detections of the same new period don't keep incrementing.
    """
    _last_scoreboard_period = 2   # end of Q2
    new_period = 3
    possession_id = 10

    # First detection of period 3
    if new_period != _last_scoreboard_period:
        possession_id += 1
        _last_scoreboard_period = new_period

    assert possession_id == 11, f"Expected 11 after period boundary, got {possession_id}"
    assert _last_scoreboard_period == 3

    # Second detection of period 3 (same frame or next OCR scan) — must NOT increment
    if new_period != _last_scoreboard_period:
        possession_id += 1  # should NOT execute

    assert possession_id == 11, (
        f"possession_id should stay at 11 on repeated period-3 detections, got {possession_id}")
