"""Tests for BUG1 fix: _court_zone() NBA-accurate thresholds.

Court orientation: x=0..94 ft (left→right), y=0..50 ft (top→bottom).
Left basket at x=5.25, y=25. Right basket at x=88.75, y=25.
"""
import pytest

unified = pytest.importorskip("src.pipeline.unified_pipeline")
_court_zone = unified.UnifiedPipeline._court_zone

# Synthetic map dims — large enough to give sub-foot rounding precision.
_W = 940
_H = 500


def _px(ft_x: float, ft_y: float):
    """Convert ft coordinates to pixels for a 940x500 map."""
    return int(ft_x / 94.0 * _W), int(ft_y / 50.0 * _H)


# --- ft_x / ft_y path (preferred) ---

def test_basket_at_origin_is_restricted_area():
    """Left basket position should be restricted_area (≤4 ft from basket)."""
    x, y = _px(5.25, 25.0)
    result = _court_zone(x, y, _W, _H, ft_x=5.25, ft_y=25.0)
    assert result == "restricted_area", f"Expected restricted_area, got {result}"


def test_paint_classification():
    """Position inside the 12×16 paint box should be paint."""
    # ft_x=10 (inside 19ft), ft_y=22 (between 19 and 31)
    x, y = _px(10.0, 22.0)
    result = _court_zone(x, y, _W, _H, ft_x=10.0, ft_y=22.0)
    assert result == "paint", f"Expected paint, got {result}"


def test_mid_range_classification():
    """Position inside the 3pt arc but outside paint: mid_range."""
    # ft_x=18, ft_y=25 — on the left side, at the free-throw line centre.
    # dist_from_basket = sqrt((18-5.25)^2 + 0^2) = 12.75 ft → inside 3pt arc.
    # ft_y=25 → not in paint (paint requires 19≤y≤31 only applies when ft_x_h≤19).
    # Actually ft_x_h=18 ≤ 19 and ft_y=25 is between 19 and 31 → paint.
    # Use ft_x=21 instead (just past free-throw line, still inside arc).
    x, y = _px(21.0, 25.0)
    result = _court_zone(x, y, _W, _H, ft_x=21.0, ft_y=25.0)
    assert result == "mid_range", f"Expected mid_range, got {result}"


def test_3pt_arc_top_classification():
    """Top of key at 24ft from basket → 3pt_arc."""
    # Basket at x=5.25; top-of-key at y=25, x=5.25+23.75=29 ft → just beyond 3pt line.
    ft_x = 5.25 + 23.75 + 0.5  # just past the arc
    x, y = _px(ft_x, 25.0)
    result = _court_zone(x, y, _W, _H, ft_x=ft_x, ft_y=25.0)
    assert result == "3pt_arc", f"Expected 3pt_arc, got {result}"


def test_corner_3_classification():
    """Corner 3: within 3ft of top sideline and within 22ft of basket."""
    # ft_y=2 (near sideline), ft_x=22 (22ft from baseline, within corner-3 zone)
    x, y = _px(22.0, 2.0)
    result = _court_zone(x, y, _W, _H, ft_x=22.0, ft_y=2.0)
    assert result == "corner_3", f"Expected corner_3, got {result}"


def test_corner_3_far_sideline():
    """Corner 3 on opposite side: y near 50ft sideline."""
    x, y = _px(22.0, 48.0)
    result = _court_zone(x, y, _W, _H, ft_x=22.0, ft_y=48.0)
    assert result == "corner_3", f"Expected corner_3, got {result}"


def test_backcourt():
    """Position at center-court (x=47ft) → backcourt (41.8ft from either basket)."""
    x, y = _px(47.0, 25.0)
    result = _court_zone(x, y, _W, _H, ft_x=47.0, ft_y=25.0)
    assert result == "backcourt", f"Expected backcourt at center-court, got {result}"


# --- normalised fallback path (no ft_x/ft_y) ---

def test_zone_handles_missing_ft_coords_via_norm_fallback():
    """When ft_x/ft_y are not supplied, function derives them from pixel coordinates."""
    # Use pixel coords for top-of-key 3pt shot (ft_x≈29.75 from left basket).
    ft_x = 5.25 + 23.75 + 1.0
    ft_y = 25.0
    x = int(ft_x / 94.0 * _W)
    y = int(ft_y / 50.0 * _H)
    # Call WITHOUT ft_x/ft_y — should fall back to normalised conversion.
    result = _court_zone(x, y, _W, _H)
    assert result in ("3pt_arc", "mid_range", "backcourt"), (
        f"Fallback path returned unexpected zone: {result}")
