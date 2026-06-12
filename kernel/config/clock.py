"""kernel.config.clock — GameClockConfig: sport-agnostic game clock configuration.

Replaces all hardcoded clock literals in the engine
(REG_GAME_LEN_SEC=2880, OT_PERIOD_LEN=300, BONUS_FOULS=5, BUCKET_BREAKPOINTS …).

Adding a sport = supplying a GameClockConfig instance in domains/<sport>/config.py.
The kernel never contains NBA literals — those live in domains/nba/config.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class GameClockConfig:
    """Immutable clock specification for any sport.

    Parameters
    ----------
    n_periods:
        Number of regulation periods (NBA 4, NFL 4, soccer 2, NHL 3, MLB 9).
    period_len_sec:
        Duration of one regulation period in seconds (NBA 720, NFL 900,
        soccer 2700).  Use 0 for untimed sports (MLB).
    ot_len_sec:
        Duration of one overtime period in seconds (NBA 300, NFL 600).
        Use 0 for untimed OT (MLB extra innings).
    untimed:
        When True the sport has no wall-clock (e.g. MLB innings, set-based
        sports).  ``remaining_frac`` falls back to a unit-index calculation
        that is guaranteed ZeroDivision-free.
    play_clock_sec:
        Per-possession shot/play clock in seconds (NBA 24, NFL 40).
        None where absent (soccer, baseball).
    penalty_threshold:
        Fouls / violations that trigger the bonus / penalty situation.
        NBA team fouls = 5; None where the concept does not apply.
    max_ot_periods:
        Maximum overtime periods before the game is ruled a draw / tie.
        None = play until decided (some formats allow unlimited OT).
    """

    n_periods: int
    period_len_sec: int
    ot_len_sec: int
    untimed: bool = False
    play_clock_sec: Optional[int] = 24
    penalty_threshold: Optional[int] = 5
    max_ot_periods: Optional[int] = None

    # ------------------------------------------------------------------
    # Core computed properties
    # ------------------------------------------------------------------

    def regulation_sec(self) -> int:
        """Total regulation time in seconds.

        Returns
        -------
        int
            ``n_periods * period_len_sec``.
            NBA: 4 * 720 = 2880.
            Untimed sports return 0 (the caller should use unit counts instead).
        """
        return self.n_periods * self.period_len_sec

    def remaining_frac(self, period: int, period_clock_sec: float) -> float:
        """Fraction of the game that is still to be played (1.0 = start, 0.0 = end).

        The value is monotonically non-increasing as the game progresses.

        Timed sports
        ------------
        Elapsed seconds are computed and divided by ``regulation_sec()``.  The
        result is clamped to [0.0, 1.0] to handle OT calls gracefully.

        Untimed sports  (``untimed=True``)
        -----------------------------------
        There is no wall-clock, so the fraction is estimated by unit index:

            remaining_frac = max(0, n_periods - (period - 1)) / n_periods

        This is ZeroDivision-safe (``n_periods`` must be ≥ 1 for a meaningful
        config) and strictly non-increasing as ``period`` advances.

        Parameters
        ----------
        period:
            Current period number, 1-indexed.  OT counts beyond ``n_periods``
            are acceptable; the timed path will clamp to 0.
        period_clock_sec:
            Seconds *remaining* in the current period (counts down toward 0).

        Returns
        -------
        float
            Value in [0.0, 1.0].
        """
        if self.untimed:
            # Unit-index path: no division by period_len_sec (could be 0).
            # Treat each period as one equal unit; how many units remain?
            units_remaining = max(0, self.n_periods - (period - 1))
            # n_periods is always ≥ 1 for a valid config; guarded below.
            total_units = self.n_periods if self.n_periods > 0 else 1
            return float(units_remaining) / float(total_units)

        # Timed path: compute elapsed vs total regulation.
        total_sec = float(self.regulation_sec())
        if total_sec <= 0.0:
            # Degenerate: 0-length regulation (should not arise for timed sports).
            return 0.0

        periods_done = max(0, period - 1)
        elapsed_in_period = max(0.0, float(self.period_len_sec) - period_clock_sec)
        elapsed_total = periods_done * self.period_len_sec + elapsed_in_period

        frac_elapsed = min(1.0, elapsed_total / total_sec)
        return max(0.0, 1.0 - frac_elapsed)

    # ------------------------------------------------------------------
    # Snapshot grid — canonical labels for RMSE/bias guard + routed ensemble
    # ------------------------------------------------------------------

    def snapshot_grid(self) -> Tuple[str, ...]:
        """Canonical snapshot labels at each period boundary.

        Returns a tuple of labels of the form ``"endP<n>"`` for each period
        boundary *within* regulation (i.e. excluding the game-end boundary).

        Examples
        --------
        NBA (n_periods=4) → ``("endP1", "endP2", "endP3")``.
        Soccer (n_periods=2) → ``("endP1",)``.
        MLB  (n_periods=9) → ``("endP1", ..., "endP8")``.

        Downstream modules (``kernel/validation/rmse_bias_guard.py``,
        ``kernel/sim_framework/routed_ensemble.py``) map these to the
        corresponding ``remaining_frac`` cut points via ``remaining_frac(p, 0)``.
        """
        return tuple(f"endP{p}" for p in range(1, self.n_periods))

    # ------------------------------------------------------------------
    # Bucket breakpoints — time-remaining routing thresholds
    # ------------------------------------------------------------------

    def bucket_breakpoints(self) -> Tuple[float, ...]:
        """Remaining-fraction cut points for time-remaining bucketing.

        Replaces the hard-coded ``BUCKET_BREAKPOINTS`` in
        ``kernel/model_ops/ingame_sigma.py`` and the 2–46-minute buckets in
        ``kernel/sim_framework/routed_ensemble.py`` with a sport-portable tuple.

        Returns
        -------
        Tuple[float, ...]
            Sorted descending (i.e. early-game to late-game) cut points in
            [0, 1].  For an n_periods game there are n_periods − 1 interior
            period boundaries plus a handful of intra-period cuts.

        Design
        ------
        Each period boundary contributes one cut point.  Within each period
        we insert a midpoint cut so that intra-period buckets exist.
        For untimed sports the midpoints are based purely on period fractions.
        """
        cuts: list[float] = []

        if self.n_periods <= 0:
            return ()

        for p in range(1, self.n_periods + 1):
            # End-of-period boundary (= start of next period).
            boundary = self.remaining_frac(p + 1, float(self.period_len_sec))
            # Midpoint within this period.
            mid_clock = self.period_len_sec / 2.0 if self.period_len_sec > 0 else 0.5
            midpoint = self.remaining_frac(p, mid_clock)
            cuts.extend([midpoint, boundary])

        # Deduplicate and sort descending (1.0 = game start, 0.0 = game end).
        seen: set[float] = set()
        result: list[float] = []
        for c in sorted(set(cuts), reverse=True):
            if c not in seen and 0.0 < c < 1.0:
                seen.add(c)
                result.append(c)

        return tuple(result)
