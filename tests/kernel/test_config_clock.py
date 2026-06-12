"""Tests for kernel.config.clock.GameClockConfig.

Hermetic and offline — stdlib + dataclasses only (no numpy, pandas, torch, nba_api).
Covers:
  (1) NBA instance regulation_sec() == 2880
  (2) untimed=True remaining_frac uses unit-index, never ZeroDivisionError
  (3) remaining_frac is monotonically non-increasing for the NBA clock
  (4) frozen-ness (FrozenInstanceError on mutation attempt)
"""
from __future__ import annotations

import dataclasses
from typing import List

import pytest

from kernel.config.clock import GameClockConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def nba_clock() -> GameClockConfig:
    """Standard NBA clock configuration."""
    return GameClockConfig(
        n_periods=4,
        period_len_sec=720,   # 12 minutes
        ot_len_sec=300,       # 5 minutes
        untimed=False,
        play_clock_sec=24,
        penalty_threshold=5,
        max_ot_periods=10,
    )


@pytest.fixture()
def untimed_clock() -> GameClockConfig:
    """Untimed sport (e.g. baseball-style innings — no wall-clock)."""
    return GameClockConfig(
        n_periods=9,
        period_len_sec=0,     # no wall clock
        ot_len_sec=0,
        untimed=True,
        play_clock_sec=None,
        penalty_threshold=None,
        max_ot_periods=None,
    )


# ---------------------------------------------------------------------------
# Case 1 — regulation_sec
# ---------------------------------------------------------------------------

class TestRegulationSec:
    def test_nba_regulation_sec_is_2880(self, nba_clock: GameClockConfig) -> None:
        """NBA: 4 periods × 720 s = 2880 s."""
        assert nba_clock.regulation_sec() == 2880

    def test_regulation_sec_formula(self) -> None:
        """regulation_sec() == n_periods * period_len_sec for arbitrary values."""
        cfg = GameClockConfig(
            n_periods=3, period_len_sec=1200, ot_len_sec=600,
            untimed=False, play_clock_sec=None,
        )
        assert cfg.regulation_sec() == 3600

    def test_untimed_regulation_sec_is_zero(
        self, untimed_clock: GameClockConfig
    ) -> None:
        """For untimed sports period_len_sec=0, so regulation_sec() is 0."""
        assert untimed_clock.regulation_sec() == 0


# ---------------------------------------------------------------------------
# Case 2 — untimed remaining_frac (unit-index, no ZeroDivisionError)
# ---------------------------------------------------------------------------

class TestUntimedRemainingFrac:
    def test_no_zero_division_error(self, untimed_clock: GameClockConfig) -> None:
        """Calling remaining_frac on an untimed clock must never raise ZeroDivisionError."""
        for period in range(1, untimed_clock.n_periods + 2):
            # period_clock_sec is irrelevant for untimed, but we pass various values.
            for clock in (0.0, 1.0, 999.0):
                try:
                    result = untimed_clock.remaining_frac(period, clock)
                except ZeroDivisionError:
                    pytest.fail(
                        f"ZeroDivisionError raised for untimed clock at "
                        f"period={period}, period_clock_sec={clock}"
                    )
                assert isinstance(result, float), "remaining_frac must return float"

    def test_start_of_game_is_full(self, untimed_clock: GameClockConfig) -> None:
        """At period 1 the whole game is remaining (fraction = 1.0)."""
        frac = untimed_clock.remaining_frac(1, 0.0)
        assert frac == pytest.approx(1.0)

    def test_after_all_periods_is_zero(self, untimed_clock: GameClockConfig) -> None:
        """After all periods are done the fraction should be 0."""
        # period = n_periods + 1 means everything is consumed.
        frac = untimed_clock.remaining_frac(untimed_clock.n_periods + 1, 0.0)
        assert frac == pytest.approx(0.0)

    def test_unit_index_decrements_per_period(
        self, untimed_clock: GameClockConfig
    ) -> None:
        """Each successive period produces a strictly lower (or equal) remaining_frac."""
        fracs = [
            untimed_clock.remaining_frac(p, 0.0)
            for p in range(1, untimed_clock.n_periods + 2)
        ]
        for earlier, later in zip(fracs, fracs[1:]):
            assert earlier >= later, (
                f"remaining_frac went UP: {earlier} -> {later}"
            )

    def test_result_in_unit_interval(self, untimed_clock: GameClockConfig) -> None:
        """remaining_frac must always be in [0.0, 1.0]."""
        for period in range(1, untimed_clock.n_periods + 2):
            frac = untimed_clock.remaining_frac(period, 0.0)
            assert 0.0 <= frac <= 1.0, (
                f"remaining_frac={frac} out of [0,1] at period={period}"
            )


# ---------------------------------------------------------------------------
# Case 3 — monotonicity for NBA timed clock
# ---------------------------------------------------------------------------

class TestNBAMonotonicity:
    """remaining_frac must be non-increasing as the game progresses."""

    def _advance_sequence(
        self, cfg: GameClockConfig, clock_step_sec: int = 60
    ) -> List[float]:
        """Build a sequence of (period, period_clock_sec) pairs that march
        forward in time, and record remaining_frac at each step."""
        fracs: List[float] = []
        for period in range(1, cfg.n_periods + 1):
            clock = cfg.period_len_sec
            while clock >= 0:
                fracs.append(cfg.remaining_frac(period, float(clock)))
                clock -= clock_step_sec
        return fracs

    def test_monotonically_non_increasing(self, nba_clock: GameClockConfig) -> None:
        """remaining_frac sequence is non-increasing at every clock step."""
        fracs = self._advance_sequence(nba_clock, clock_step_sec=60)
        for i, (a, b) in enumerate(zip(fracs, fracs[1:])):
            assert a >= b - 1e-9, (
                f"Non-monotonic at step {i}: {a} < {b}"
            )

    def test_starts_near_one(self, nba_clock: GameClockConfig) -> None:
        """At the very start of Q1 the full game remains."""
        frac = nba_clock.remaining_frac(1, float(nba_clock.period_len_sec))
        assert frac == pytest.approx(1.0)

    def test_ends_at_zero(self, nba_clock: GameClockConfig) -> None:
        """At the end of the final period, 0 game time remains."""
        frac = nba_clock.remaining_frac(nba_clock.n_periods, 0.0)
        assert frac == pytest.approx(0.0)

    def test_midgame_between_zero_and_one(self, nba_clock: GameClockConfig) -> None:
        """Halftime is approximately 0.5 for a symmetric game."""
        # End of Q2 = start of second half.
        frac = nba_clock.remaining_frac(3, float(nba_clock.period_len_sec))
        assert 0.45 <= frac <= 0.55, (
            f"Halftime remaining_frac={frac} not near 0.5"
        )

    def test_fine_grained_within_period(self, nba_clock: GameClockConfig) -> None:
        """Within a single period, clock ticking down strictly decreases frac."""
        period = 2
        clocks = list(range(nba_clock.period_len_sec, -1, -10))
        fracs = [nba_clock.remaining_frac(period, float(c)) for c in clocks]
        for a, b in zip(fracs, fracs[1:]):
            assert a >= b - 1e-9, (
                f"Within-period monotonicity violated: {a} -> {b}"
            )


# ---------------------------------------------------------------------------
# Case 4 — frozen-ness
# ---------------------------------------------------------------------------

class TestFrozenness:
    def test_cannot_mutate_n_periods(self, nba_clock: GameClockConfig) -> None:
        """Assigning to a field of a frozen dataclass must raise FrozenInstanceError."""
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_clock.n_periods = 6  # type: ignore[misc]

    def test_cannot_mutate_period_len_sec(self, nba_clock: GameClockConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            nba_clock.period_len_sec = 900  # type: ignore[misc]

    def test_cannot_mutate_untimed(self, untimed_clock: GameClockConfig) -> None:
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            untimed_clock.untimed = False  # type: ignore[misc]

    def test_is_frozen_dataclass(self, nba_clock: GameClockConfig) -> None:
        """The class must be declared as a frozen dataclass."""
        fields = dataclasses.fields(nba_clock)
        assert len(fields) > 0, "GameClockConfig must be a dataclass"
        # Verify by checking __dataclass_params__
        params = nba_clock.__dataclass_params__  # type: ignore[attr-defined]
        assert params.frozen is True, "GameClockConfig must have frozen=True"


# ---------------------------------------------------------------------------
# Case 5 — snapshot_grid & bucket_breakpoints sanity
# ---------------------------------------------------------------------------

class TestSnapshotGrid:
    def test_nba_snapshot_grid_length(self, nba_clock: GameClockConfig) -> None:
        """NBA should produce 3 snapshot labels (endP1, endP2, endP3)."""
        grid = nba_clock.snapshot_grid()
        assert len(grid) == 3
        assert grid == ("endP1", "endP2", "endP3")

    def test_snapshot_grid_labels_start_at_endp1(
        self, nba_clock: GameClockConfig
    ) -> None:
        """First label is always endP1."""
        grid = nba_clock.snapshot_grid()
        assert grid[0] == "endP1"

    def test_snapshot_grid_two_period_sport(self) -> None:
        """A two-period sport produces exactly one intermediate label."""
        cfg = GameClockConfig(
            n_periods=2, period_len_sec=2700, ot_len_sec=900,
            untimed=False, play_clock_sec=None,
        )
        assert cfg.snapshot_grid() == ("endP1",)

    def test_snapshot_grid_untimed(self, untimed_clock: GameClockConfig) -> None:
        """snapshot_grid works for untimed configs (length = n_periods - 1)."""
        grid = untimed_clock.snapshot_grid()
        assert len(grid) == untimed_clock.n_periods - 1


class TestBucketBreakpoints:
    def test_returns_tuple(self, nba_clock: GameClockConfig) -> None:
        bp = nba_clock.bucket_breakpoints()
        assert isinstance(bp, tuple)

    def test_values_in_open_unit_interval(self, nba_clock: GameClockConfig) -> None:
        """All breakpoints must be strictly inside (0, 1)."""
        for b in nba_clock.bucket_breakpoints():
            assert 0.0 < b < 1.0, f"Breakpoint {b} outside (0,1)"

    def test_sorted_descending(self, nba_clock: GameClockConfig) -> None:
        """Breakpoints must be sorted descending (early-game to late-game)."""
        bp = nba_clock.bucket_breakpoints()
        assert list(bp) == sorted(bp, reverse=True), "Breakpoints must be descending"

    def test_untimed_no_zero_division(self, untimed_clock: GameClockConfig) -> None:
        """bucket_breakpoints() must not raise ZeroDivisionError for untimed."""
        try:
            untimed_clock.bucket_breakpoints()
        except ZeroDivisionError:
            pytest.fail("ZeroDivisionError in bucket_breakpoints() for untimed clock")
