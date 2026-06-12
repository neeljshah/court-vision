"""domains.soccer.signals — Three honest gate candidates for the soccer adapter.

Each signal targets ``"winprob"`` so the gate routes through Brier scoring
rather than MAE.  The expected gate verdict is written in each class docstring
BEFORE any gate run — this is the honest-discipline practice: expected REJECTs
are the success criterion, not a failure.

F5 compliance (binding): ZERO imports from any other domain adapter,
``src.data``, ``src.sim``, ``src.tracking``, ``src.pipeline``, or
``domains.soccer.config``.  Only the sport-agnostic kernel seam
(``src.loop.signal.*``) is used.

PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Signal 1 — soccer_rest_congestion
# ---------------------------------------------------------------------------


class SoccerRestCongestionSignal(Signal):
    """Rest-days differential (home minus away) as a fixture-congestion signal.

    Hypothesis: teams with significantly more rest days win more often than
    market-implied probability predicts.

    Expected gate verdict: REJECT.
    Rationale: fixture congestion and rest schedules are fully public information
    at match time and are incorporated immediately by sharp books (e.g. Pinnacle).
    The rest differential captures no information beyond what the market has
    already priced.  REJECT is the predicted and honest gate outcome — it
    demonstrates the gate's discrimination on sport-3 data, not a signal weakness.
    """

    name: str = "soccer_rest_congestion"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return rest-day differential (rest_days_home - rest_days_away), clipped to [-10, 10].

        Reads ``ctx.extra["rest_days_home"]`` and ``ctx.extra["rest_days_away"]``
        (populated by the soccer adapter's feature bundle).
        Returns None when either key is missing.
        """
        rest_home = ctx.extra.get("rest_days_home")
        rest_away = ctx.extra.get("rest_days_away")
        if rest_home is None or rest_away is None:
            return None
        return float(np.clip(float(rest_home) - float(rest_away), -10.0, 10.0))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "Teams with more rest days (fewer days since last fixture) "
                "outperform their market-implied win probability in soccer."
            ),
            rationale=(
                "Fixture congestion and rest differentials are fully public at "
                "kickoff time and are priced into sharp books within minutes of "
                "schedule release.  The signal is expected to carry no residual "
                "information above the market close.  REJECT is the predicted "
                "and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 2 — soccer_totals_form
# ---------------------------------------------------------------------------


class SoccerTotalsFormSignal(Signal):
    """Recent-form totals mean vs Poisson lambda — the 'over team' narrative stat.

    Hypothesis: teams whose recent matches produced more total goals than the
    Poisson-implied lambda beat their expected totals win probability.

    Expected gate verdict: REJECT.
    Rationale: 'over team' recent-form is the canonical totals narrative stat
    in soccer, prominently displayed on every betting interface and syndicated
    sports media.  It is fully public information priced by totals markets.
    Expected to fail the walk-forward or null-shuffle criterion.  REJECT is
    the predicted and honest gate outcome.
    """

    name: str = "soccer_totals_form"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return recent-totals-mean minus Poisson lambda, clipped to [-2.5, 2.5].

        Reads ``ctx.extra["recent_totals_mean"]`` and ``ctx.extra["lam_total"]``
        (populated by the soccer adapter; recent_totals_mean is set to None by
        the adapter when fewer than 5 prior matches are available).
        Returns None when either key is missing or recent_totals_mean is None.
        """
        recent = ctx.extra.get("recent_totals_mean")
        lam = ctx.extra.get("lam_total")
        if recent is None or lam is None:
            return None
        return float(np.clip(float(recent) - float(lam), -2.5, 2.5))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "Teams whose recent matches averaged more total goals than the "
                "Poisson-implied lambda outperform their expected over/under "
                "probability in soccer."
            ),
            rationale=(
                "Recent-form totals is the canonical narrative stat for soccer "
                "totals betting, fully public and incorporated into sharp-book "
                "lines.  Expected to fail walk-forward or null-shuffle criterion. "
                "REJECT is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 3 — soccer_h2h_totals
# ---------------------------------------------------------------------------


class SoccerH2HTotalsSignal(Signal):
    """Head-to-head totals mean vs Poisson lambda — H2H narrative totals signal.

    Hypothesis: the historical average total goals in prior matchups between
    the two teams carries information above the Poisson lambda.

    Expected gate verdict: REJECT.
    Rationale: head-to-head totals is a narrative stat prominently shown on
    all betting platforms and is priced into the closing line.  Small H2H
    samples dominate the distribution (most fixture pairs have few prior
    meetings), making the signal noise-dominated.  Mirrors the sport-agnostic
    finding that narrative H2H stats reject gate-clean on real data.
    REJECT is the predicted and honest gate outcome.
    """

    name: str = "soccer_h2h_totals"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return H2H totals mean minus Poisson lambda, clipped to [-2.5, 2.5].

        Reads:
            ctx.extra["h2h_totals_mean"] — mean total goals across prior H2H matches
            ctx.extra["h2h_total"]       — number of prior H2H matches (sample size)
            ctx.extra["lam_total"]       — Poisson lambda for this fixture

        Returns None when any key is missing or h2h_total < 3 (insufficient sample).
        """
        h2h_mean = ctx.extra.get("h2h_totals_mean")
        h2h_n = ctx.extra.get("h2h_total")
        lam = ctx.extra.get("lam_total")
        if h2h_mean is None or h2h_n is None or lam is None:
            return None
        if float(h2h_n) < 3:
            return None  # insufficient H2H sample
        return float(np.clip(float(h2h_mean) - float(lam), -2.5, 2.5))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "The historical mean total goals in prior head-to-head fixtures "
                "between two soccer teams carries information above the "
                "Poisson-implied lambda for the current match."
            ),
            rationale=(
                "H2H totals is a narrative stat, prominently visible on all "
                "betting interfaces and priced into sharp-book closing lines. "
                "Most fixture pairs have sparse prior meetings, making the signal "
                "noise-dominated.  Mirrors the intel-campaign finding that H2H "
                "narrative stats reject gate-clean.  REJECT is the predicted and "
                "honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

ALL_SIGNALS: tuple = (
    SoccerRestCongestionSignal,
    SoccerTotalsFormSignal,
    SoccerH2HTotalsSignal,
)

__all__ = [
    "SoccerRestCongestionSignal",
    "SoccerTotalsFormSignal",
    "SoccerH2HTotalsSignal",
    "ALL_SIGNALS",
]
