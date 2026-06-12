"""Tests for kernel.config.speed.SpeedConfig.

Hermetic and offline — stdlib + dataclasses only (no numpy, pandas, torch,
nba_api).

Covers:
  (1) per_frame() conversion is correct at NBA values
      (drive_min 10 ft/s at 30 fps → 10/30 ft/frame)
  (2) thresholds_ft_s carries drive_min=10.0 and cut_min=14.0;
      screen_dist_ft=6.0 is accessible on the instance
  (3) frozen-ness (FrozenInstanceError / AttributeError on mutation attempt)
"""
from __future__ import annotations

import dataclasses

import pytest

from kernel.config.speed import SpeedConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def nba_speed() -> SpeedConfig:
    """Canonical NBA SpeedConfig built from spec literals."""
    return SpeedConfig(
        video_fps=30.0,
        thresholds_ft_s={"drive_min": 10.0, "cut_min": 14.0},
        screen_dist_ft=6.0,
    )


# ---------------------------------------------------------------------------
# Case 1 — per_frame() conversion correctness
# ---------------------------------------------------------------------------

class TestPerFrame:
    """per_frame(threshold_ft_s) == threshold_ft_s / video_fps."""

    def test_drive_min_nba(self, nba_speed: SpeedConfig) -> None:
        """drive_min 10 ft/s at 30 fps → 10/30 ft/frame (≈ 0.3333…)."""
        expected = 10.0 / 30.0
        assert nba_speed.per_frame(10.0) == pytest.approx(expected)

    def test_cut_min_nba(self, nba_speed: SpeedConfig) -> None:
        """cut_min 14 ft/s at 30 fps → 14/30 ft/frame."""
        expected = 14.0 / 30.0
        assert nba_speed.per_frame(14.0) == pytest.approx(expected)

    def test_screen_dist_round_trip(self, nba_speed: SpeedConfig) -> None:
        """screen_dist_ft / video_fps round-trip is consistent."""
        expected = 6.0 / 30.0
        assert nba_speed.per_frame(6.0) == pytest.approx(expected)

    def test_formula_at_60_fps(self) -> None:
        """Formula holds at a different fps (60 fps)."""
        cfg = SpeedConfig(video_fps=60.0, thresholds_ft_s={"sprint_min": 20.0})
        expected = 20.0 / 60.0
        assert cfg.per_frame(20.0) == pytest.approx(expected)

    def test_formula_at_25_fps(self) -> None:
        """Formula holds at 25 fps (PAL broadcast rate)."""
        cfg = SpeedConfig(video_fps=25.0, thresholds_ft_s={"jog_min": 5.0})
        expected = 5.0 / 25.0
        assert cfg.per_frame(5.0) == pytest.approx(expected)

    def test_per_frame_named_drive(self, nba_speed: SpeedConfig) -> None:
        """per_frame_named('drive_min') equals per_frame(10.0)."""
        assert nba_speed.per_frame_named("drive_min") == pytest.approx(
            nba_speed.per_frame(10.0)
        )

    def test_per_frame_named_cut(self, nba_speed: SpeedConfig) -> None:
        """per_frame_named('cut_min') equals per_frame(14.0)."""
        assert nba_speed.per_frame_named("cut_min") == pytest.approx(
            nba_speed.per_frame(14.0)
        )

    def test_per_frame_named_missing_key_raises(
        self, nba_speed: SpeedConfig
    ) -> None:
        """per_frame_named raises KeyError for an absent threshold name."""
        with pytest.raises(KeyError):
            nba_speed.per_frame_named("nonexistent_threshold")

    def test_per_frame_scales_linearly_with_threshold(
        self, nba_speed: SpeedConfig
    ) -> None:
        """Doubling the threshold doubles the per-frame distance."""
        assert nba_speed.per_frame(20.0) == pytest.approx(
            2.0 * nba_speed.per_frame(10.0)
        )

    def test_per_frame_inverse_of_speed_conversion(
        self, nba_speed: SpeedConfig
    ) -> None:
        """ft_per_frame * video_fps == threshold_ft_s (exact inverse)."""
        threshold = 10.0
        ft_per_frame = nba_speed.per_frame(threshold)
        reconstructed = ft_per_frame * nba_speed.video_fps
        assert reconstructed == pytest.approx(threshold)

    def test_zero_threshold_gives_zero(self, nba_speed: SpeedConfig) -> None:
        """A zero threshold produces zero per-frame distance."""
        assert nba_speed.per_frame(0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Case 2 — thresholds_ft_s content & screen_dist_ft
# ---------------------------------------------------------------------------

class TestThresholdsContent:
    """NBA instance carries the correct threshold values."""

    def test_drive_min_value(self, nba_speed: SpeedConfig) -> None:
        """thresholds_ft_s['drive_min'] == 10.0."""
        assert nba_speed.thresholds_ft_s["drive_min"] == pytest.approx(10.0)

    def test_cut_min_value(self, nba_speed: SpeedConfig) -> None:
        """thresholds_ft_s['cut_min'] == 14.0."""
        assert nba_speed.thresholds_ft_s["cut_min"] == pytest.approx(14.0)

    def test_exactly_two_threshold_keys(self, nba_speed: SpeedConfig) -> None:
        """NBA fixture has exactly the two declared threshold keys."""
        assert set(nba_speed.thresholds_ft_s.keys()) == {"drive_min", "cut_min"}

    def test_screen_dist_ft_value(self, nba_speed: SpeedConfig) -> None:
        """screen_dist_ft == 6.0 for the NBA fixture."""
        assert nba_speed.screen_dist_ft == pytest.approx(6.0)

    def test_video_fps_value(self, nba_speed: SpeedConfig) -> None:
        """video_fps == 30.0 for the NBA fixture."""
        assert nba_speed.video_fps == pytest.approx(30.0)

    def test_empty_thresholds_default(self) -> None:
        """A SpeedConfig with no explicit thresholds defaults to an empty mapping."""
        cfg = SpeedConfig(video_fps=30.0)
        assert cfg.thresholds_ft_s == {}

    def test_thresholds_dict_is_accessible(self, nba_speed: SpeedConfig) -> None:
        """thresholds_ft_s is a dict-like mapping (supports 'in' and iteration)."""
        assert "drive_min" in nba_speed.thresholds_ft_s
        assert "cut_min" in nba_speed.thresholds_ft_s
        assert len(nba_speed.thresholds_ft_s) == 2


# ---------------------------------------------------------------------------
# Case 3 — frozen-ness
# ---------------------------------------------------------------------------

class TestFrozenness:
    """Mutating any field of a frozen dataclass must raise an error."""

    def test_cannot_mutate_video_fps(self, nba_speed: SpeedConfig) -> None:
        """Assigning video_fps raises FrozenInstanceError or AttributeError."""
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_speed.video_fps = 60.0  # type: ignore[misc]

    def test_cannot_mutate_screen_dist_ft(self, nba_speed: SpeedConfig) -> None:
        """Assigning screen_dist_ft raises FrozenInstanceError or AttributeError."""
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_speed.screen_dist_ft = 99.0  # type: ignore[misc]

    def test_cannot_mutate_thresholds_ft_s(self, nba_speed: SpeedConfig) -> None:
        """Reassigning thresholds_ft_s itself raises FrozenInstanceError."""
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_speed.thresholds_ft_s = {}  # type: ignore[misc]

    def test_is_frozen_dataclass(self, nba_speed: SpeedConfig) -> None:
        """The class must be declared as a frozen dataclass."""
        fields = dataclasses.fields(nba_speed)
        assert len(fields) > 0, "SpeedConfig must be a dataclass"
        params = nba_speed.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen is True, "SpeedConfig must have frozen=True"

    def test_two_identical_instances_are_equal(self) -> None:
        """Frozen dataclasses with the same field values compare equal."""
        a = SpeedConfig(
            video_fps=30.0,
            thresholds_ft_s={"drive_min": 10.0, "cut_min": 14.0},
            screen_dist_ft=6.0,
        )
        b = SpeedConfig(
            video_fps=30.0,
            thresholds_ft_s={"drive_min": 10.0, "cut_min": 14.0},
            screen_dist_ft=6.0,
        )
        assert a == b

    def test_different_fps_instances_are_not_equal(self) -> None:
        """Instances with different fps are not equal."""
        a = SpeedConfig(video_fps=30.0)
        b = SpeedConfig(video_fps=60.0)
        assert a != b
