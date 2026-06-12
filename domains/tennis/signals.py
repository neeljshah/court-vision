"""domains.tennis.signals — Three honest gate candidates for the tennis adapter.

Each signal targets ``"winprob"`` so the gate routes through Brier scoring
(``_CLASS_TARGETS`` in gate.py:42) rather than MAE.  The expected gate verdict
is written in each class docstring BEFORE any gate run — this is the honest-
discipline practice from SECOND_DOMAIN_PROOF.md §4.4: expected REJECTs are the
success criterion, not a failure.

F5 compliance (binding): ZERO imports from ``domains.nba``, ``src.data``,
``src.sim``, ``src.tracking``, or ``src.pipeline``.  Only the sport-agnostic
kernel seam (``src.loop.signal.*``) is used.

PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Signal 1 — fatigue_rest
# ---------------------------------------------------------------------------


class FatigueRestSignal(Signal):
    """Days-since-last-match (rest) advantage for the favoured player.

    Hypothesis: a player with significantly more rest days wins more often
    than Elo predicts.

    Expected gate verdict: REJECT.
    Rationale: fatigue/rest is widely known to market participants on sharp
    books (Pinnacle prices tennis within minutes of draw release with player
    schedules fully public).  The Elo baseline absorbs some of the signal;
    the residual is priced away. Expected to fail the walk-forward criterion
    and/or not beat the null-shuffle (SECOND_DOMAIN_PROOF.md §4.4, signal 1).
    A REJECT is the HONEST SUCCESS OUTCOME for this signal — it demonstrates
    the gate works on sport-2 data, not that the signal is weak.
    """

    name: str = "tennis_fatigue_rest"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return rest-day advantage (rest_a - rest_b), clipped to [-15, 15].

        Reads ``ctx.extra["rest_days_a"]`` and ``ctx.extra["rest_days_b"]``
        (populated by TennisAdapter.feature_bundle via _add_rest_days).
        Returns None when either value is missing.
        """
        ra = ctx.extra.get("rest_days_a")
        rb = ctx.extra.get("rest_days_b")
        if ra is None or rb is None:
            return None
        return float(np.clip(float(ra) - float(rb), -15.0, 15.0))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "Players with more rest days (days since last completed match) "
                "outperform their Elo-predicted win probability."
            ),
            rationale=(
                "Rest/fatigue is a widely documented factor in tennis but is fully "
                "visible to sharp books at draw time. Expected to be priced — "
                "REJECT is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 2 — surface_transition
# ---------------------------------------------------------------------------


class SurfaceTransitionSignal(Signal):
    """Penalty for a player's first event on a new surface.

    Hypothesis: players performing their first tournament on a surface change
    (e.g. clay → grass) have worse outcomes than Elo predicts.

    Expected gate verdict: REJECT or DEFER (power).
    Rationale: surface transitions are sparse events.  The gate's
    ``_MIN_FOLD_ROWS = 60`` requirement may not be met on the sub-population
    of first-surface-of-season matches → DEFER (insufficient walk-forward
    folds) is plausible.  If enough rows exist, the signal is likely already
    priced (sharp books run surface-specific Elo models) → REJECT.
    The DEFER/REJECT result is the honest expected outcome; a SHIP would be
    a single-fold-lift artifact requiring the full artifact-hunt protocol.
    """

    name: str = "tennis_surface_transition"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return 1.0 if this is a surface-transition match for entity_a, else 0.0.

        Reads ``ctx.extra["is_surface_transition"]`` (bool/int).
        Returns None when the flag is unavailable.
        """
        flag = ctx.extra.get("is_surface_transition")
        if flag is None:
            return None
        return 1.0 if flag else 0.0

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "Players competing in their first tournament of the season on a "
                "new surface underperform their Elo-implied win probability."
            ),
            rationale=(
                "Surface-transition matches are sparse; the gate may DEFER due to "
                "insufficient fold rows.  If sufficient data exist, the signal is "
                "likely priced by sharp books.  REJECT or DEFER is the predicted "
                "and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 3 — h2h_residual
# ---------------------------------------------------------------------------


class H2HResidualSignal(Signal):
    """Head-to-head record residual over Elo expectation.

    Hypothesis: a player's historical win rate vs a specific opponent
    exceeds what their overall Elo ratings predict.

    Expected gate verdict: REJECT.
    Rationale: H2H record is the classic narrative tennis stat and is
    prominently visible on all betting interfaces.  Sharp books (Pinnacle)
    adjust for H2H — any marginal information above Elo is priced.  Weak
    small-sample signal (most H2H pairs have few matches) that is unlikely
    to beat the null-shuffle control.  REJECT is the predicted honest outcome.
    This mirrors the NBA intel-campaign finding that narrative stats
    (outcome-impact artifacts) REJECT gate-clean.
    """

    name: str = "tennis_h2h_residual"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return the H2H win-rate residual vs Elo expectation for entity_a.

        Reads:
            ctx.extra["h2h_wins_a"]   — entity_a wins vs entity_b (historical)
            ctx.extra["h2h_total"]    — total H2H matches
            ctx.extra["elo_prob_a"]   — Elo P(a wins), pre-match leak-free

        Returns None when any field is missing or H2H sample < 3 matches.
        Clipped to [-0.5, 0.5] to bound outlier small-sample pairs.
        """
        wins_a = ctx.extra.get("h2h_wins_a")
        total = ctx.extra.get("h2h_total")
        elo_p = ctx.extra.get("elo_prob_a")
        if wins_a is None or total is None or elo_p is None:
            return None
        total_f = float(total)
        if total_f < 3:
            return None  # insufficient H2H sample
        h2h_rate = float(wins_a) / total_f
        residual = h2h_rate - float(elo_p)
        return float(np.clip(residual, -0.5, 0.5))

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "A player's head-to-head win rate vs a specific opponent "
                "carries information beyond their overall Elo win probability."
            ),
            rationale=(
                "H2H record is the canonical narrative tennis stat, fully visible "
                "and already priced into Pinnacle's sharp line.  Small-sample "
                "pairs dominate the distribution.  REJECT (does not beat null-"
                "shuffle) is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

ALL_SIGNALS: tuple[type, ...] = (
    FatigueRestSignal,
    SurfaceTransitionSignal,
    H2HResidualSignal,
)

__all__ = [
    "FatigueRestSignal",
    "SurfaceTransitionSignal",
    "H2HResidualSignal",
    "ALL_SIGNALS",
]
