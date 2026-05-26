"""Tests for the directional gate added in unified_pipeline.py.

The gate computes cosine similarity between the ball's velocity vector and the
direction toward the nearest basket.  Real shots have cos_sim >= threshold;
pass arcs and lob-handoffs aimed at teammates score near 0 or negative.

These tests exercise the gate logic directly without running the full pipeline.
All geometry is in pixel space (same as the live code) with a synthetic map_w.
"""
import importlib
import math
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# Helpers that replicate the gate logic from unified_pipeline.py
# ---------------------------------------------------------------------------
_BASKET_L_NORM = (0.045, 0.5)
_BASKET_R_NORM = (0.955, 0.5)


def _directional_gate(
    ball_hist,  # list of (x_px, y_px), oldest first
    map_w: int,
    map_h: int,
    cos_min: float = 0.3,
) -> bool:
    """Pure-Python replica of the directional gate in unified_pipeline.py.

    Returns True (shot allowed) or False (blocked).
    Falls back to True when velocity is near-zero or history is too short.
    """
    import numpy as np  # noqa: PLC0415

    if len(ball_hist) < 2:
        return True  # not enough history — don't block

    bh_old = ball_hist[0]
    bh_now = ball_hist[-1]
    vx = float(bh_now[0] - bh_old[0])
    vy = float(bh_now[1] - bh_old[1])
    v_mag = float(np.hypot(vx, vy))

    if v_mag <= 0.5:
        return True  # near-zero velocity — don't block

    bl = (_BASKET_L_NORM[0] * map_w, _BASKET_L_NORM[1] * map_h)
    br = (_BASKET_R_NORM[0] * map_w, _BASKET_R_NORM[1] * map_h)
    dl = float(np.hypot(bh_now[0] - bl[0], bh_now[1] - bl[1]))
    dr = float(np.hypot(bh_now[0] - br[0], bh_now[1] - br[1]))
    tbx, tby = bl if dl <= dr else br
    b_mag = min(dl, dr)

    if b_mag <= 1e-6:
        return True  # ball is at the basket — don't block

    cos_sim = (
        vx * (tbx - bh_now[0]) + vy * (tby - bh_now[1])
    ) / (v_mag * b_mag)

    return cos_sim >= cos_min


# ---------------------------------------------------------------------------
# Test 1: real shot pointed at the left basket should be ALLOWED
# ---------------------------------------------------------------------------
def test_directional_gate_allows_shot_pointed_at_basket():
    """Ball at (150, 200), left basket ~(43, 240).  Velocity (-30, 10) moves
    toward the left baseline — cosine should be clearly positive → allowed."""
    map_w, map_h = 940, 500
    # Ball is 5 frames of history ending at x=150 (moving left → toward basket)
    hist = [(180, 210), (175, 208), (170, 205), (160, 202), (150, 200)]
    result = _directional_gate(hist, map_w, map_h, cos_min=0.3)
    assert result is True, "Shot pointing at basket should pass the directional gate"


# ---------------------------------------------------------------------------
# Test 2: horizontal pass aimed at midcourt should be BLOCKED
# ---------------------------------------------------------------------------
def test_directional_gate_blocks_horizontal_pass():
    """Ball near left basket (x~150), velocity strongly rightward (+50, 0) —
    heading toward midcourt, away from both baskets → cos_sim negative → blocked."""
    map_w, map_h = 940, 500
    # Ball moves from x=100 → x=350: fast rightward pass
    hist = [(100, 250), (163, 250), (225, 250), (288, 250), (350, 250)]
    result = _directional_gate(hist, map_w, map_h, cos_min=0.3)
    assert result is False, "Rightward pass near left basket should be blocked"


# ---------------------------------------------------------------------------
# Test 3: lob to a corner teammate (upward pixel velocity, wrong direction)
# ---------------------------------------------------------------------------
def test_directional_gate_blocks_lob_to_teammate():
    """Ball at (200, 50) moves toward top corner (200, 5) — strong upward
    pixel velocity but basket is at y=250 (midcourt height).  Velocity is
    perpendicular/away from basket → cos_sim near 0 or negative → blocked."""
    map_w, map_h = 940, 500
    # Lob going toward top of frame (y decreasing) while basket is at y=250
    hist = [(200, 50), (200, 38), (200, 26), (200, 14), (200, 5)]
    result = _directional_gate(hist, map_w, map_h, cos_min=0.3)
    assert result is False, "Lob toward corner (away from basket) should be blocked"


# ---------------------------------------------------------------------------
# Test 4: threshold tunable via env var (module-level constant reacts to env)
# ---------------------------------------------------------------------------
def test_directional_gate_threshold_via_env_var():
    """_SHOT_DIRECTIONAL_COS_MIN should reflect NBA_SHOT_DIRECTIONAL_COS_MIN env var."""
    import importlib

    os.environ["NBA_SHOT_DIRECTIONAL_COS_MIN"] = "0.55"
    try:
        # Force reload so module-level float() call re-reads the env var.
        if "src.pipeline.unified_pipeline" in sys.modules:
            mod = importlib.reload(sys.modules["src.pipeline.unified_pipeline"])
        else:
            mod = importlib.import_module("src.pipeline.unified_pipeline")
        assert abs(mod._SHOT_DIRECTIONAL_COS_MIN - 0.55) < 1e-9, (
            f"Expected 0.55, got {mod._SHOT_DIRECTIONAL_COS_MIN}"
        )
    finally:
        os.environ.pop("NBA_SHOT_DIRECTIONAL_COS_MIN", None)
        # Reload again to restore default so other tests aren't affected.
        if "src.pipeline.unified_pipeline" in sys.modules:
            importlib.reload(sys.modules["src.pipeline.unified_pipeline"])


# ---------------------------------------------------------------------------
# Test 5: fallback to True when ball velocity is near-zero
# ---------------------------------------------------------------------------
def test_directional_gate_passes_when_velocity_zero():
    """Ball stationary (tracker jitter) — v_mag < 0.5 → gate returns True,
    deferring the decision to other gates (don't block on held-ball frames)."""
    map_w, map_h = 940, 500
    # Ball essentially stationary near the left basket
    hist = [(44, 250), (44, 251), (44, 250), (45, 250), (44, 250)]
    result = _directional_gate(hist, map_w, map_h, cos_min=0.3)
    assert result is True, "Near-zero velocity should not block (fallback to True)"


# ---------------------------------------------------------------------------
# Test 6: fallback to True when ball position history is unavailable
# ---------------------------------------------------------------------------
def test_directional_gate_passes_when_ball_pos_unavailable():
    """Empty history (ball lost / first frame) → gate returns True so other
    gates (proximity, global) remain the authority."""
    map_w, map_h = 940, 500
    result = _directional_gate([], map_w, map_h, cos_min=0.3)
    assert result is True, "Empty ball history should not block"

    result_single = _directional_gate([(300, 250)], map_w, map_h, cos_min=0.3)
    assert result_single is True, "Single-frame history should not block"
