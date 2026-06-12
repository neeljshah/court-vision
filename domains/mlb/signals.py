"""domains.mlb.signals — Three honest gate candidates for the MLB adapter.

Each signal targets ``"winprob"`` so the gate routes through Brier scoring
rather than MAE.  The expected gate verdict is written in each class docstring
BEFORE any gate run — this is the honest-discipline practice: expected REJECTs
are the success criterion, not a failure.

F5 compliance (binding): ZERO imports from any other domain adapter,
``src.data``, ``src.sim``, ``src.tracking``, ``src.pipeline``, or
``domains.mlb.config``.  Only the sport-agnostic kernel seam
(``src.loop.signal.*``) is used.

PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Signal 1 — mlb_rest_advantage
# ---------------------------------------------------------------------------


class MLBRestAdvantageSignal(Signal):
    """Rest-days differential (home minus away) as a schedule-fatigue signal.

    Hypothesis: teams with more rest days win more often than
    market-implied probability predicts.

    Expected gate verdict: REJECT.
    Rationale: MLB plays near-daily so the rest differential sits at zero for
    the vast majority of games.  Schedules are fully public information posted
    weeks in advance and are incorporated immediately by sharp books.  The rest
    differential captures no information beyond what the market has already
    priced.  REJECT is the predicted and honest gate outcome — it demonstrates
    the gate's discrimination on a fourth sport, not a signal weakness.
    """

    name: str = "mlb_rest_advantage"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return rest-day differential (rest_days_home - rest_days_away), clipped to [-3, 3].

        Reads ``ctx.extra["rest_days_home"]`` and ``ctx.extra["rest_days_away"]``
        (populated by the MLB adapter's feature bundle).
        Returns None when either key is missing.

        The clip bound is ±3 because MLB schedules are dense: meaningful
        rest differentials beyond three days are rare and would be extreme
        outliers already priced by the line.
        """
        rest_home = ctx.extra.get("rest_days_home")
        rest_away = ctx.extra.get("rest_days_away")
        if rest_home is None or rest_away is None:
            return None
        return float(np.clip(float(rest_home) - float(rest_away), -3.0, 3.0))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "MLB home teams with more days of rest since their last game "
                "outperform their market-implied win probability compared to "
                "away teams with less rest."
            ),
            rationale=(
                "MLB plays near-daily so the mass of rest differentials sits at "
                "zero.  Schedule information is fully public at game time and is "
                "priced into sharp books within minutes of release.  The signal "
                "is expected to carry no residual information above the market "
                "close.  REJECT is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 2 — mlb_streak_form
# ---------------------------------------------------------------------------


class MLBStreakFormSignal(Signal):
    """Recent-win-rate differential vs Elo-implied probability — the hot-team narrative stat.

    Hypothesis: teams whose last-10 win rate exceeds their Elo-implied win
    probability continue to outperform their market probability.

    Expected gate verdict: REJECT.
    Rationale: last-10 win rate is the canonical baseball hot-team narrative
    stat, prominently displayed on every sportsbook and syndicated sports
    media outlet.  It is fully public information priced by the closing line.
    Expected to fail the walk-forward or null-shuffle criterion.  REJECT is
    the predicted and honest gate outcome.
    """

    name: str = "mlb_streak_form"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return recent_win10 minus p_home_elo, clipped to [-0.5, 0.5].

        Reads:
            ctx.extra["recent_win10"]  — home team win rate over last 10 games
                                         (adapter sets to None when < 10 prior games
                                         are available; signal returns None in that case)
            ctx.extra["p_home_elo"]    — Elo-implied home win probability

        Returns None when either key is missing or recent_win10 is None.
        """
        recent_win10 = ctx.extra.get("recent_win10")
        p_elo = ctx.extra.get("p_home_elo")
        if recent_win10 is None or p_elo is None:
            return None
        return float(np.clip(float(recent_win10) - float(p_elo), -0.5, 0.5))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "MLB home teams whose last-10 win rate exceeds their Elo-implied "
                "win probability outperform that probability in subsequent games."
            ),
            rationale=(
                "Last-10 form is the canonical hot-team narrative stat in baseball, "
                "prominently displayed on every betting interface and sports media "
                "platform.  It is fully public and incorporated into sharp-book "
                "closing lines.  Expected to fail walk-forward or null-shuffle "
                "criterion.  REJECT is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Signal 3 — mlb_h2h_season
# ---------------------------------------------------------------------------


class MLBH2HSeasonSignal(Signal):
    """Head-to-head season series rate vs Elo-implied probability — H2H narrative signal.

    Hypothesis: the home team's win rate in prior regular-season meetings
    against the same opponent carries information above the Elo-implied
    win probability.

    Expected gate verdict: REJECT.
    Rationale: head-to-head season series record is a narrative stat shown on
    all betting platforms and broadcast pre-game shows.  It is fully public
    information priced into closing lines.  Small within-season H2H samples
    (teams meet 6–19 times per season) make the signal noise-dominated.
    Mirrors the platform-wide finding that narrative H2H stats reject
    gate-clean.  REJECT is the predicted and honest gate outcome.
    """

    name: str = "mlb_h2h_season"
    target: str = "winprob"
    scope: str = "pregame"
    reads_atlas = []
    emits = []

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Return h2h_rate minus p_home_elo, clipped to [-0.5, 0.5].

        Reads:
            ctx.extra["h2h_rate"]    — home team win rate in prior H2H games this season
            ctx.extra["h2h_n"]       — number of prior H2H games this season (sample size)
            ctx.extra["p_home_elo"]  — Elo-implied home win probability

        Returns None when any key is missing or h2h_n < 6 (insufficient sample —
        fewer than 6 prior meetings makes the rate unreliable).
        """
        h2h_rate = ctx.extra.get("h2h_rate")
        h2h_n = ctx.extra.get("h2h_n")
        p_elo = ctx.extra.get("p_home_elo")
        if h2h_rate is None or h2h_n is None or p_elo is None:
            return None
        if float(h2h_n) < 6:
            return None  # insufficient H2H sample
        return float(np.clip(float(h2h_rate) - float(p_elo), -0.5, 0.5))

    def hypothesis(self) -> Hypothesis:
        """Return the pre-run hypothesis for the gate."""
        return Hypothesis(
            name=self.name,
            target="winprob",
            scope="pregame",
            statement=(
                "The MLB home team's win rate in prior season series games against "
                "the same opponent carries information above the Elo-implied win "
                "probability for the current game."
            ),
            rationale=(
                "H2H season series record is a narrative stat prominently visible "
                "on all betting interfaces and broadcast pre-game shows, fully "
                "public and priced into sharp-book closing lines.  Within-season "
                "sample sizes (6–19 meetings) make the signal noise-dominated. "
                "Mirrors the intel-campaign finding that narrative H2H stats reject "
                "gate-clean.  REJECT is the predicted and honest gate outcome."
            ),
            source="seed",
            expected_verdict="REJECT",
            priority="P2",
        )


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

ALL_SIGNALS: tuple = (
    MLBRestAdvantageSignal,
    MLBStreakFormSignal,
    MLBH2HSeasonSignal,
)

__all__ = [
    "MLBRestAdvantageSignal",
    "MLBStreakFormSignal",
    "MLBH2HSeasonSignal",
    "ALL_SIGNALS",
]
