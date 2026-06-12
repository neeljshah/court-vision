"""kernel.config.game_state — GameStateConfig: sport-agnostic game-state thresholds.

Replaces all hardcoded game-state literals scattered across the engine
(blowout detection, clutch-time logic, garbage-time detection, win-probability
promotion thresholds — AUDIT gap #5 / BUILD_BACKLOG P0-D-005).

Adding a sport = supplying a GameStateConfig instance in domains/<sport>/config.py.
The kernel never contains NBA literals — those live in domains/nba/config.py.

HONESTY MECHANISM — legacy_overrides (EXTRACTION §5.1)
------------------------------------------------------
Where two source modules use DIFFERENT literals for the SAME concept, BOTH
values are preserved verbatim under the key ``"<module>.<name>"``.  The
disagreement is NEVER unified: unifying would hide a real inconsistency in
the production code that might affect simulation results.  Callers that need
a specific module's exact behaviour must retrieve the per-module key; callers
that want a sport's canonical primary value use the corresponding field.

Primary-value provenance (NBA):
- blowout_margin  = 15.0   — game_models.py:100 (training threshold; conservative)
- clutch_margin   =  6.0   — live_game_simulator.py:279 (the wider of the two live values)
- clutch_remaining_sec = 360.0 — live_game_simulator.py:279 (sec<=360 AND period>=4)
- garbage_margin  = 18.0   — garbage_time_detector.py:157 live detect_blowout (live threshold)
- competitive_margin = 12.0 — upper bound of the "~5–12 pts competitive" note in census §Game-state
- final_margin_sigma = 13.5 — SIGMA_FULL_DEFAULT in src/ingame/universal_winprob.py:28
- winprob_promotion_period = 4 — MIN_PERIOD_FOR_UNIVERSAL in src/ingame/universal_winprob.py:33

Zero heavy imports: stdlib + typing + dataclasses only (no numpy, pandas, torch, nba_api).
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Dict, Mapping


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _make_proxy(d: Dict[str, float]) -> types.MappingProxyType:  # type: ignore[type-arg]
    """Wrap *d* in a read-only MappingProxyType.

    Used by the ``legacy_overrides`` default factory so that the field
    behaves like an immutable mapping even though the dataclass is frozen
    (a plain ``dict`` default would still allow callers to mutate the dict
    object in-place, bypassing the frozen contract at the Python level).
    """
    return types.MappingProxyType(d)


# ---------------------------------------------------------------------------
# GameStateConfig
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GameStateConfig:
    """Immutable game-state threshold specification for any sport.

    Primary fields hold the *canonical* value chosen for the sport (see
    module docstring for NBA provenance).  ``legacy_overrides`` is the
    honesty mechanism that records every per-module literal verbatim so
    that real disagreements in the source code are never silently collapsed.

    Parameters
    ----------
    blowout_margin:
        Score differential at or above which the game is considered a
        blowout for the purposes of primary simulation / prediction logic.
        NBA primary: 15.0 (game_models.py training threshold).
    clutch_margin:
        Maximum score differential for clutch-time classification.
        NBA primary: 6.0 (live_game_simulator.py:279 — the wider margin).
    clutch_remaining_sec:
        Maximum seconds remaining in the period/game for clutch-time
        classification.  NBA primary: 360.0 (live_game_simulator.py:279).
    garbage_margin:
        Score differential used by live blowout / garbage-time detectors.
        NBA primary: 18.0 (garbage_time_detector.py:157 live path — wider
        than the 15.0 training threshold, hence a distinct primary).
    competitive_margin:
        Upper bound of the "competitive game" score range.  Games within
        this margin receive full projection weight.  NBA primary: 12.0
        (upper end of the "~5–12 pts competitive" census note; no single
        named constant was found — recorded as such in NBA_LITERALS.md).
    final_margin_sigma:
        Standard deviation of final score margin used by the universal
        win-probability model.  NBA primary: 13.5 (SIGMA_FULL_DEFAULT in
        src/ingame/universal_winprob.py:28).
    winprob_promotion_period:
        Earliest period at which the universal win-probability model is
        used instead of the fallback.  NBA primary: 4 (MIN_PERIOD_FOR_UNIVERSAL
        in src/ingame/universal_winprob.py:33).
    legacy_overrides:
        Read-only ``Mapping[str, float]`` keyed ``"<module>.<name>"`` that
        captures every per-module literal verbatim.  NEVER unified — the
        disagreement is part of the record.  Defaults to the NBA-sourced
        set of known disagreements (see census §Game-state).

        Mandatory NBA keys (minimum per spec P0-D-005):
        - ``"game_models.blowout_margin"``       : 15.0
        - ``"garbage_time_detector.blowout_margin"``: 18.0
        - ``"live_game_simulator.blowout_margin"``: 18.0
        - ``"live_game_simulator.clutch_margin"`` : 6.0
        - ``"game_clock_sim.clutch_margin"``      : 5.0

        Additional keys from the census:
        - ``"garbage_time_detector.blowout_margin_training"``: 15.0
          (garbage_time_detector.py:35 — separate training threshold)
        - ``"live_game_simulator.clutch_remaining_sec"``     : 360.0
        - ``"game_clock_sim.clutch_remaining_sec"``          : 300.0
    """

    # ------------------------------------------------------------------
    # Primary / canonical fields
    # ------------------------------------------------------------------

    blowout_margin: float
    clutch_margin: float
    clutch_remaining_sec: float
    garbage_margin: float
    competitive_margin: float
    final_margin_sigma: float
    winprob_promotion_period: int

    # ------------------------------------------------------------------
    # Legacy-override registry (honesty mechanism)
    # ------------------------------------------------------------------

    #: Default NBA legacy overrides, derived verbatim from the literal census.
    #: Wrapped in MappingProxyType so that callers cannot mutate the object
    #: even though ``frozen=True`` only prevents *field re-assignment*.
    legacy_overrides: Mapping[str, float] = field(
        default_factory=lambda: _make_proxy(
            {
                # --- blowout disagreements ---
                # game_models.py:100 — training / prediction threshold
                "game_models.blowout_margin": 15.0,
                # garbage_time_detector.py:35 — training-mode threshold
                "garbage_time_detector.blowout_margin_training": 15.0,
                # garbage_time_detector.py:157 — live detect_blowout threshold
                "garbage_time_detector.blowout_margin": 18.0,
                # live_game_simulator.py:185 — blowout + sec_remaining<=480 check
                "live_game_simulator.blowout_margin": 18.0,
                # --- clutch margin disagreements ---
                # live_game_simulator.py:279 — margin<=6 AND sec<=360 AND period>=4
                "live_game_simulator.clutch_margin": 6.0,
                # game_clock_sim.py:171 — margin<=5 AND period>=4 AND clock<300
                "game_clock_sim.clutch_margin": 5.0,
                # --- clutch remaining-seconds disagreements ---
                # live_game_simulator.py:279 — sec<=360 (6 minutes)
                "live_game_simulator.clutch_remaining_sec": 360.0,
                # game_clock_sim.py:171 — clock<300 (5 minutes)
                "game_clock_sim.clutch_remaining_sec": 300.0,
            }
        )
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        if self.blowout_margin <= 0.0:
            raise ValueError(
                f"GameStateConfig.blowout_margin must be > 0; "
                f"got {self.blowout_margin}"
            )
        if self.clutch_margin <= 0.0:
            raise ValueError(
                f"GameStateConfig.clutch_margin must be > 0; "
                f"got {self.clutch_margin}"
            )
        if self.clutch_remaining_sec <= 0.0:
            raise ValueError(
                f"GameStateConfig.clutch_remaining_sec must be > 0; "
                f"got {self.clutch_remaining_sec}"
            )
        if self.garbage_margin <= 0.0:
            raise ValueError(
                f"GameStateConfig.garbage_margin must be > 0; "
                f"got {self.garbage_margin}"
            )
        if self.competitive_margin <= 0.0:
            raise ValueError(
                f"GameStateConfig.competitive_margin must be > 0; "
                f"got {self.competitive_margin}"
            )
        if self.final_margin_sigma <= 0.0:
            raise ValueError(
                f"GameStateConfig.final_margin_sigma must be > 0; "
                f"got {self.final_margin_sigma}"
            )
        if self.winprob_promotion_period < 1:
            raise ValueError(
                f"GameStateConfig.winprob_promotion_period must be >= 1; "
                f"got {self.winprob_promotion_period}"
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def is_blowout(self, margin: float) -> bool:
        """Return ``True`` if *margin* qualifies as a blowout.

        Uses the primary ``blowout_margin`` field, NOT a per-module literal.
        Callers that need module-specific behaviour should look up the
        appropriate key in ``legacy_overrides``.

        Parameters
        ----------
        margin:
            Absolute score differential (always non-negative).

        Returns
        -------
        bool
        """
        return abs(margin) >= self.blowout_margin

    def is_clutch(self, margin: float, remaining_sec: float, period: int) -> bool:
        """Return ``True`` if the current game situation qualifies as clutch time.

        Uses the primary ``clutch_margin`` / ``clutch_remaining_sec`` fields.

        Parameters
        ----------
        margin:
            Absolute score differential.
        remaining_sec:
            Seconds remaining in the current period (or game).
        period:
            Current period number, 1-indexed.  Must be >= ``winprob_promotion_period``.

        Returns
        -------
        bool
        """
        return (
            abs(margin) <= self.clutch_margin
            and remaining_sec <= self.clutch_remaining_sec
            and period >= self.winprob_promotion_period
        )

    def is_competitive(self, margin: float) -> bool:
        """Return ``True`` if the game is still within competitive range.

        Parameters
        ----------
        margin:
            Absolute score differential.

        Returns
        -------
        bool
        """
        return abs(margin) <= self.competitive_margin
