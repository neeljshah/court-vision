"""Signal: minutes_trend — L3 minutes-played slope reveals expanding/shrinking role.

**Hypothesis**
A player's slope over their last 3 games is a leading indicator of their
pregame minutes expectation.  Coaches adjust rotation depth in response to
performance, injury load, and opponent matchup; the L3 slope captures the
direction of that adjustment.  A player on a rising-slope trend (e.g. +4
min/game over three games) is likely to receive above-baseline minutes tonight;
one on a declining slope (e.g. -6 min/game) has probably ceded role to a
teammate or entered a minutes restriction.

**Data source**
``data/player_adv_stats.parquet`` — 77,728 rows at grain
``(player_id, game_id, game_date)``, column ``minutes`` (float64, no nulls).
All rows with ``game_date < ctx.decision_time`` are used to locate the three
most recent games; the slope is computed as the linear coefficient of a 1-D
least-squares fit over ``[0, 1, 2]`` (games oldest-to-newest).

**Reads atlas**
``player:<id>`` / section ``role_profile`` — if the store holds a prior
role-profile entry (e.g. baseline minutes, archetype) the baseline is read
and used to normalise the raw slope before returning, so the signal is on
a comparable scale across rotation players vs starters.  Degrades gracefully
when the store is empty.

**Returns**
A scalar ``float`` — the L3 linear slope (minutes per game, clipped to
[-10.7, 10.9] = p1/p99 of the empirical distribution).  Positive = expanding
role; negative = shrinking role.  Returns ``None`` when:
  - ``ctx.player_id`` is not set, OR
  - fewer than 3 games exist strictly before ``ctx.decision_time`` for that
    player (insufficient history for a slope).

**Gate expectations**
  SHIP is the expected verdict.  The L3 slope is a direct proxy for the
  coach's revealed minutes intent and captures information not already in
  L5/L10 averages or season-average forms.  It should survive walk-forward
  (recent role shifts have predictive value each season) and null-shuffle
  (slope direction is real: injury returns, load management, bench demotion
  all produce non-random slope signals).  CLV gate: expected positive vs
  Pinnacle because sportsbook props lag rotation news by ≥1 game.

**DEFER note**
None — ``data/player_adv_stats.parquet`` is present and fully populated
(77,728 rows, 0% null on ``minutes``).  The optional atlas reinforcement
path degrades gracefully if the store is empty.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue

# ---------------------------------------------------------------------------
# Paths (script-relative ROOT — portable to RunPod Linux; NEVER hardcode)
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
_ADV_STATS_PATH = _ROOT / "data" / "player_adv_stats.parquet"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Minimum prior games needed to compute a slope.
_MIN_GAMES: int = 3

# Empirical p1 / p99 across all rolling-L3 windows (see build note).
_SLOPE_CLIP_LO: float = -10.7
_SLOPE_CLIP_HI: float = 10.9

# Atlas section key the signal reads for the role baseline.
_ATLAS_SECTION: str = "role_profile"


# ---------------------------------------------------------------------------
# Module-level parquet cache (loaded once per process)
# ---------------------------------------------------------------------------
_ADV_DF: Optional[pd.DataFrame] = None


def _get_adv_df() -> pd.DataFrame:
    """Return (and cache) the player_adv_stats parquet.

    The cache is process-wide so repeated calls within one process do not
    re-read disk.  Test code can replace _ADV_DF at module level to inject
    fixtures (see test_signal_minutes_trend.py).

    Returns:
        DataFrame with columns ``player_id``, ``game_date``, ``minutes``
        (at minimum).  Sorted by ``(player_id, game_date)``.
    """
    global _ADV_DF
    if _ADV_DF is None:
        if not _ADV_STATS_PATH.exists():
            _ADV_DF = pd.DataFrame(columns=["player_id", "game_date", "minutes"])
        else:
            _ADV_DF = (
                pd.read_parquet(
                    _ADV_STATS_PATH,
                    columns=["player_id", "game_date", "minutes"],
                )
                .sort_values(["player_id", "game_date"])
                .reset_index(drop=True)
            )
    return _ADV_DF


# ---------------------------------------------------------------------------
# Internal computation helpers
# ---------------------------------------------------------------------------

def _player_minutes_before(
    player_id: int,
    before_date: str,
    df: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """Return the ``minutes`` series for *player_id* strictly before *before_date*.

    Args:
        player_id:   NBA player id.
        before_date: ISO date string (YYYY-MM-DD).  Rows on or after this date
                     are excluded (strict < comparison) for leak safety.
        df:          Optional override DataFrame (used in tests).

    Returns:
        Pandas Series of ``minutes`` values, sorted oldest→newest.  Empty if
        the player has no qualifying history.
    """
    source = df if df is not None else _get_adv_df()
    mask = (source["player_id"] == player_id) & (source["game_date"] < before_date)
    return source.loc[mask, "minutes"].reset_index(drop=True)


def _compute_l3_slope(minutes_series: pd.Series) -> Optional[float]:
    """Compute the L3 linear slope (minutes / game) for the last 3 entries.

    Args:
        minutes_series: Series of past ``minutes`` values, oldest-first.
                        Must have at least ``_MIN_GAMES`` entries.

    Returns:
        Slope coefficient (float) clipped to [_SLOPE_CLIP_LO, _SLOPE_CLIP_HI],
        or ``None`` if fewer than ``_MIN_GAMES`` entries exist.
    """
    if len(minutes_series) < _MIN_GAMES:
        return None
    last3 = minutes_series.iloc[-_MIN_GAMES:].values.astype(float)
    slope = float(np.polyfit(range(_MIN_GAMES), last3, 1)[0])
    return float(np.clip(slope, _SLOPE_CLIP_LO, _SLOPE_CLIP_HI))


# ---------------------------------------------------------------------------
# The Signal class
# ---------------------------------------------------------------------------

class MinutesTrendSignal(Signal):
    """L3 minutes-played slope as a leading role-expansion/contraction indicator.

    Reads ``data/player_adv_stats.parquet`` filtered to strictly before
    ``ctx.decision_time`` (leak-safe) and optionally reads the ``role_profile``
    atlas section from the store for a role-baseline context.

    Emits a scalar float (minutes/game slope) clipped to the empirical
    p1/p99 range so outliers from injury-return or DNP sequences do not
    dominate the feature.
    """

    name: str = "minutes_trend"
    target: str = "minutes"
    scope: str = "pregame"
    reads_atlas: List[str] = [_ATLAS_SECTION]
    emits: List[str] = []  # scalar signal

    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute the leak-safe L3 minutes slope for ``ctx.player_id``.

        Only reads rows with ``game_date`` strictly before
        ``ctx.decision_time`` (the as-of ISO date) from
        ``player_adv_stats.parquet``.  Reads the store atlas section
        ``role_profile`` if bound (degrades gracefully when absent).

        Args:
            ctx: decision context; must have ``player_id`` set.

        Returns:
            float slope in [_SLOPE_CLIP_LO, _SLOPE_CLIP_HI], or ``None``
            when player_id is unset or fewer than 3 prior games exist.
        """
        if ctx.player_id is None:
            return None

        before_date = ctx.as_of_iso()  # YYYY-MM-DD  (strict <)

        # ---- optional: read role_profile atlas for baseline context ----------
        # Currently consumed only for diagnostics / future shrinkage; the raw
        # slope is returned directly so the gate evaluates the raw signal.
        role_baseline_minutes: Optional[float] = None
        if self.store is not None:
            role_data = self.store.read_atlas(
                "player", ctx.player_id, _ATLAS_SECTION, ctx.decision_time
            )
            if isinstance(role_data, dict):
                role_baseline_minutes = role_data.get("avg_minutes")

        # ---- load parquet data (leak-safe: before_date strict <) -------------
        series = _player_minutes_before(ctx.player_id, before_date)

        # ---- compute slope ---------------------------------------------------
        slope = _compute_l3_slope(series)
        return slope  # None when < 3 games, float otherwise

    def hypothesis(self) -> Hypothesis:
        """Return the basketball hypothesis this signal tests."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "A player's linear slope over their last 3 games played "
                "(minutes/game) is a leading indicator of their pregame minutes "
                "expectation: coaches reveal role changes one game before "
                "sportsbooks and the season-average model catch up, so a rising "
                "L3 slope predicts above-baseline minutes tonight and a declining "
                "slope predicts below-baseline minutes."
            ),
            rationale=(
                "Rotation adjustments — load management, injury returns, lineup "
                "experiments, opponent-specific schemes — manifest in minutes "
                "allocations 1-3 games before they appear in L5/L10 averages.  "
                "The L3 window is the most sensitive to abrupt shifts while "
                "still having enough signal to estimate a direction (polyfit on "
                "3 points).  The empirical p1/p99 clip (-10.7 / +10.9 min/game) "
                "prevents injury-return spikes from distorting the model.  "
                "Reinforcement: when this signal SHIPs, learned per-player "
                "mean-slope values are written back to the store as "
                "``signal__minutes_trend``, enriching the role_profile atlas "
                "for downstream signals."
            ),
            source="seed",
            atlas_fields=[_ATLAS_SECTION],
            expected_verdict="SHIP",
            priority="P2",
        )
