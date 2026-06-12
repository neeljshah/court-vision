"""Tests for kernel.config.court.CourtConfig.

Hermetic and offline — stdlib + dataclasses only (no numpy, pandas, torch, nba_api).
Covers:
  (1) NBA instance round-trip: area() == 4700, control_grid() == (47, 25).
  (2) normalize_speed at fps=30 vs fps=25 for identical px_per_frame differs by
      EXACTLY 30/25 (the AUDIT gap-#7 regression — fps was previously hard-coded).
  (3) frozen-ness (FrozenInstanceError on mutation attempt).
"""
from __future__ import annotations

import dataclasses
import math

import pytest

from kernel.config.court import CourtConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def nba_court() -> CourtConfig:
    """Standard NBA court configuration — built from literals (no domain import)."""
    return CourtConfig(
        surface_w=94.0,
        surface_h=50.0,
        unit="ft",
        goal_x_left=0.045,
        goal_x_right=0.955,
        goal_y=0.5,
        key_zones={
            "paint_left": (0.0, 0.19, 0.19, 0.81),
            "paint_right": (0.81, 0.19, 1.0, 0.81),
        },
        rectified_px=(940, 500),
        fps_native=30.0,
        speed_tiers={"drive_min": 10.0, "cut_min": 14.0},
        three_pt_dist=23.75,
    )


# ---------------------------------------------------------------------------
# Case 1 — NBA instance round-trips
# ---------------------------------------------------------------------------

class TestNBAInstanceRoundTrip:
    """Verify that the NBA court instance produces the expected geometry values."""

    def test_area_equals_4700(self, nba_court: CourtConfig) -> None:
        """area() == 94.0 × 50.0 == 4700.0 ft²."""
        assert nba_court.area() == 4700.0

    def test_area_is_float(self, nba_court: CourtConfig) -> None:
        """area() must return a float."""
        assert isinstance(nba_court.area(), float)

    def test_control_grid_default_is_47_by_25(self, nba_court: CourtConfig) -> None:
        """control_grid() with default cells_per_unit=0.5 → (47, 25)."""
        assert nba_court.control_grid() == (47, 25)

    def test_control_grid_returns_tuple_of_two_ints(
        self, nba_court: CourtConfig
    ) -> None:
        """control_grid() must return a (int, int) tuple."""
        result = nba_court.control_grid()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert all(isinstance(v, int) for v in result)

    def test_control_grid_explicit_half_unit(self, nba_court: CourtConfig) -> None:
        """Explicitly passing cells_per_unit=0.5 must also produce (47, 25)."""
        assert nba_court.control_grid(cells_per_unit=0.5) == (47, 25)

    def test_surface_dimensions_stored(self, nba_court: CourtConfig) -> None:
        """Stored surface_w and surface_h match the NBA literal values."""
        assert nba_court.surface_w == 94.0
        assert nba_court.surface_h == 50.0

    def test_unit_is_ft(self, nba_court: CourtConfig) -> None:
        """unit field must be 'ft' for the NBA court."""
        assert nba_court.unit == "ft"

    def test_goal_anchors(self, nba_court: CourtConfig) -> None:
        """Basket anchors must equal the NBA literal values."""
        assert nba_court.goal_x_left == pytest.approx(0.045)
        assert nba_court.goal_x_right == pytest.approx(0.955)
        assert nba_court.goal_y == pytest.approx(0.5)

    def test_rectified_px_is_940_500(self, nba_court: CourtConfig) -> None:
        """rectified_px must be (940, 500)."""
        assert nba_court.rectified_px == (940, 500)

    def test_three_pt_dist_stored(self, nba_court: CourtConfig) -> None:
        """three_pt_dist must equal the NBA value 23.75 ft."""
        assert nba_court.three_pt_dist == pytest.approx(23.75)


# ---------------------------------------------------------------------------
# Case 2 — normalize_speed fps ratio contract (AUDIT gap #7 regression)
# ---------------------------------------------------------------------------

class TestNormalizeSpeed:
    """The fps-ratio contract: same px_per_frame → speeds in exact fps ratio."""

    # Regression: before the fix fps was hard-coded to 30 in the spatial modules,
    # so passing fps=25 produced the SAME number as fps=30 — an 83% undercount.
    # Now the formula is: speed = (px_per_frame * fps) / px_per_unit
    # → the ratio normalise(x,30,k) / normalise(x,25,k) must equal EXACTLY 30/25.

    _PX_PER_FRAME = 5.0
    _PX_PER_UNIT = 10.0

    def test_fps_ratio_exact_30_over_25(self, nba_court: CourtConfig) -> None:
        """normalize_speed(x, 30, k) / normalize_speed(x, 25, k) == exactly 30/25."""
        speed_30 = nba_court.normalize_speed(
            self._PX_PER_FRAME, 30.0, self._PX_PER_UNIT
        )
        speed_25 = nba_court.normalize_speed(
            self._PX_PER_FRAME, 25.0, self._PX_PER_UNIT
        )
        # Exact float division — no tolerance needed; both operands share the
        # same px_per_frame and px_per_unit so the ratio is analytically exact.
        assert speed_30 / speed_25 == 30.0 / 25.0

    def test_fps_ratio_tight_tolerance(self, nba_court: CourtConfig) -> None:
        """Cross-check: ratio is within a very tight tolerance of 1.2."""
        speed_30 = nba_court.normalize_speed(
            self._PX_PER_FRAME, 30.0, self._PX_PER_UNIT
        )
        speed_25 = nba_court.normalize_speed(
            self._PX_PER_FRAME, 25.0, self._PX_PER_UNIT
        )
        assert math.isclose(speed_30 / speed_25, 30.0 / 25.0, rel_tol=1e-15)

    def test_speed_formula_values(self, nba_court: CourtConfig) -> None:
        """Spot-check the actual returned values for a concrete input."""
        # 5 px/frame at 30 fps with 10 px/ft → 15 ft/s
        speed = nba_court.normalize_speed(5.0, 30.0, 10.0)
        assert speed == pytest.approx(15.0)

    def test_speed_formula_25fps(self, nba_court: CourtConfig) -> None:
        """5 px/frame at 25 fps with 10 px/ft → 12.5 ft/s."""
        speed = nba_court.normalize_speed(5.0, 25.0, 10.0)
        assert speed == pytest.approx(12.5)

    def test_fps_ratio_with_fractional_fps(self, nba_court: CourtConfig) -> None:
        """The fps-ratio contract holds for non-integer fps values (29.97 vs 30)."""
        px_per_frame = 3.7
        px_per_unit = 9.4
        s_30 = nba_court.normalize_speed(px_per_frame, 30.0, px_per_unit)
        s_2997 = nba_court.normalize_speed(px_per_frame, 29.97, px_per_unit)
        expected_ratio = 30.0 / 29.97
        assert math.isclose(s_30 / s_2997, expected_ratio, rel_tol=1e-12)

    def test_fps_ratio_60_over_30(self, nba_court: CourtConfig) -> None:
        """normalize_speed at fps=60 is exactly 2× fps=30 for same input."""
        s_60 = nba_court.normalize_speed(2.0, 60.0, 8.0)
        s_30 = nba_court.normalize_speed(2.0, 30.0, 8.0)
        assert s_60 / s_30 == 60.0 / 30.0

    def test_different_court_same_ratio(self) -> None:
        """The fps-ratio contract holds for any court dimensions, not just NBA."""
        soccer = CourtConfig(
            surface_w=105.0,
            surface_h=68.0,
            unit="m",
            goal_x_left=0.0,
            goal_x_right=1.0,
            goal_y=0.5,
            key_zones={},
            rectified_px=(1050, 680),
            fps_native=25.0,
            speed_tiers={},
            three_pt_dist=0.0,
        )
        px = 4.0
        k = 12.0
        s_30 = soccer.normalize_speed(px, 30.0, k)
        s_25 = soccer.normalize_speed(px, 25.0, k)
        assert s_30 / s_25 == 30.0 / 25.0

    def test_linear_in_px_per_frame(self, nba_court: CourtConfig) -> None:
        """Speed scales linearly with px_per_frame (all else equal)."""
        s1 = nba_court.normalize_speed(3.0, 30.0, 10.0)
        s2 = nba_court.normalize_speed(6.0, 30.0, 10.0)
        assert s2 / s1 == pytest.approx(2.0)

    def test_inversely_proportional_to_px_per_unit(
        self, nba_court: CourtConfig
    ) -> None:
        """Speed halves when px_per_unit doubles (same px displacement = fewer units)."""
        s1 = nba_court.normalize_speed(4.0, 30.0, 10.0)
        s2 = nba_court.normalize_speed(4.0, 30.0, 20.0)
        assert s1 / s2 == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Case 3 — frozen-ness
# ---------------------------------------------------------------------------

class TestFrozenness:
    """CourtConfig must be a frozen dataclass — mutation raises FrozenInstanceError."""

    def test_cannot_mutate_surface_w(self, nba_court: CourtConfig) -> None:
        """Assigning to surface_w must raise FrozenInstanceError or AttributeError."""
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_court.surface_w = 100.0  # type: ignore[misc]

    def test_cannot_mutate_surface_h(self, nba_court: CourtConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_court.surface_h = 55.0  # type: ignore[misc]

    def test_cannot_mutate_unit(self, nba_court: CourtConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_court.unit = "m"  # type: ignore[misc]

    def test_cannot_mutate_fps_native(self, nba_court: CourtConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_court.fps_native = 60.0  # type: ignore[misc]

    def test_cannot_mutate_rectified_px(self, nba_court: CourtConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_court.rectified_px = (1280, 720)  # type: ignore[misc]

    def test_is_frozen_dataclass(self, nba_court: CourtConfig) -> None:
        """Confirm __dataclass_params__.frozen is True."""
        fields = dataclasses.fields(nba_court)
        assert len(fields) > 0, "CourtConfig must be a dataclass with fields"
        params = nba_court.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen is True, "CourtConfig must have frozen=True"


# ---------------------------------------------------------------------------
# Extra — area / control_grid for non-NBA instances
# ---------------------------------------------------------------------------

class TestNonNBAInstances:
    """Verify that area() and control_grid() are generic across sports."""

    def test_area_soccer(self) -> None:
        """Soccer: ~105 m × ~68 m = 7140 m²."""
        cfg = CourtConfig(
            surface_w=105.0,
            surface_h=68.0,
            unit="m",
            goal_x_left=0.0,
            goal_x_right=1.0,
            goal_y=0.5,
            key_zones={},
            rectified_px=(1050, 680),
            fps_native=25.0,
            speed_tiers={},
            three_pt_dist=0.0,
        )
        assert cfg.area() == pytest.approx(7140.0)

    def test_control_grid_custom_cells_per_unit(self) -> None:
        """Custom cells_per_unit produces the expected grid dimensions."""
        cfg = CourtConfig(
            surface_w=120.0,
            surface_h=53.3,
            unit="yd",
            goal_x_left=0.0,
            goal_x_right=1.0,
            goal_y=0.5,
            key_zones={},
            rectified_px=(1200, 533),
            fps_native=30.0,
            speed_tiers={},
            three_pt_dist=0.0,
        )
        # cells_per_unit=1 → cols=120, rows=53
        cols, rows = cfg.control_grid(cells_per_unit=1.0)
        assert cols == 120
        assert rows == 53

    def test_default_key_zones_empty(self) -> None:
        """A CourtConfig with an empty key_zones dict is valid."""
        cfg = CourtConfig(
            surface_w=50.0,
            surface_h=25.0,
            unit="m",
            goal_x_left=0.05,
            goal_x_right=0.95,
            goal_y=0.5,
            key_zones={},
            rectified_px=(500, 250),
        )
        assert cfg.key_zones == {}
        assert cfg.area() == pytest.approx(1250.0)
