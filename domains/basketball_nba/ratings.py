"""domains.basketball_nba.ratings — leak-free walk-forward Elo ratings for NBA games.

Replay a chronologically-sorted sequence of games and emit per-game PRE-game
team Elo ratings (the leak-free prediction features).  Ratings are updated AFTER
the pre-game snapshot is recorded — so future results can never contaminate features.

Model: team Elo with home-court advantage and between-season mean-regression.
  - Snapshot BEFORE update (strictly pre-game columns).
  - Season-boundary regression applied at most once per team per season transition,
    keyed to processed rows only (deterministic, replay-ordered).
  - Zero-sum Elo update: delta added to home, subtracted from away.

Input DataFrame columns (the games.parquet built by the ingest agent):
  game_id, date, season, home_team, away_team, home_win (1.0/0.0),
  rest_days_home, rest_days_away, home_b2b, away_b2b, travel_home, travel_away.
  Only date, season, home_team, away_team, home_win are consumed here;
  extra columns are preserved in the output.

PRIVATE: outputs are price-bearing when combined with odds; ``data/domains/basketball_nba/``
is never tracked.  No src.* / kernel.* / other-domain imports (falsifier F5 compliance).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

from domains.basketball_nba.elo_config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EloState:
    """Snapshot of team Elo ratings at a point in time.

    ``elo``         : team_name → Elo rating (float)
    ``counts``      : team_name → number of games processed
    ``last_season`` : team_name → season integer of the last processed game
    ``last_date``   : date of the last processed game (None if empty)
    ``n_processed`` : total games processed
    """

    elo: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    last_season: Dict[str, int] = field(default_factory=dict)
    last_date: Optional[dt.date] = None
    n_processed: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Return ``df`` sorted by pinned chronological order.

    Key: (date, home_team, away_team) — mergesort-stable so ties within the
    same game-day retain deterministic order.  The date key is parsed via
    ``pd.to_datetime`` so ordering is dtype-robust: datetime64 columns and
    non-zero-padded date strings sort chronologically, not lexically.  (For
    the zero-padded ISO strings used by the current callers this is order-
    preserving; it only fixes the datetime64 / non-padded cases.)
    """
    sort_df = pd.DataFrame(
        {
            "k0": pd.to_datetime(df["date"]).values,
            "k1": df["home_team"].astype(str).values,
            "k2": df["away_team"].astype(str).values,
        },
        index=df.index,
    )
    sorted_idx = sort_df.sort_values(["k0", "k1", "k2"], kind="mergesort").index
    return df.loc[sorted_idx].reset_index(drop=True)


def _p_home(elo_home: float, elo_away: float) -> float:
    """Return P(home team wins) given pre-game Elo ratings with HFA applied.

    Formula (pinned)::

        d = (elo_home + ELO_HFA) - elo_away
        p = 1 / (1 + 10 ** (-d / 400))
    """
    d = (elo_home + ELO_HFA) - elo_away
    return 1.0 / (1.0 + math.pow(10.0, -d / 400.0))


def _maybe_regress(state: EloState, team: str, season: int) -> None:
    """Apply season-boundary regression for ``team`` if season changed.

    Initialises unseen teams to ELO_MEAN before use.  Applies regression at
    most once per team per season transition — keyed to processed rows, so
    a mid-offseason until cut that has processed no new-season rows leaves
    both replay paths identical.
    """
    if team not in state.elo:
        # First-ever appearance: initialise to prior and record season.
        state.elo[team] = ELO_MEAN
        state.last_season[team] = season
        return

    prev_season = state.last_season.get(team)
    if prev_season is not None and prev_season != season:
        # Season boundary: regress toward mean.
        state.elo[team] += SEASON_REGRESS * (ELO_MEAN - state.elo[team])
        state.last_season[team] = season


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def replay(games: pd.DataFrame, until: Optional[dt.date] = None) -> EloState:
    """Replay games in chronological order and return the resulting EloState.

    Parameters
    ----------
    games:
        DataFrame with columns: ``date`` (date-like), ``season`` (int),
        ``home_team`` (str), ``away_team`` (str), ``home_win`` (1.0/0.0).
        ``season`` must be int (callers map the NBA "YYYY-YY" string via
        ``_season_to_int``); ``int(df['season'])`` is consumed directly here.
    until:
        If provided, process only games with ``date < until`` (strictly before).
        This is the AsOfContext.decision_time contract: the date D itself is
        excluded so that ratings are leak-free for predicting games ON date D.

    Returns
    -------
    EloState
        Snapshot of ratings AFTER processing all qualifying games.
    """
    if len(games) == 0:
        return EloState()

    df = _sorted(games)
    dates = pd.to_datetime(df["date"]).dt.date

    state = EloState()

    for i in range(len(df)):
        row_date = dates.iloc[i]

        # Strict-before filter.
        if until is not None and row_date >= until:
            continue

        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        home_win = float(df["home_win"].iloc[i])

        # --- Step 1: season-boundary regression (before snapshot) ---
        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)

        # --- Step 2: snapshot (pre-game win probability) ---
        p = _p_home(state.elo[home], state.elo[away])

        # --- Step 3: update (post-snapshot) ---
        s_home = 1.0 if home_win >= 0.5 else 0.0
        delta = ELO_K * (s_home - p)
        state.elo[home] += delta
        state.elo[away] -= delta

        state.counts[home] = state.counts.get(home, 0) + 1
        state.counts[away] = state.counts.get(away, 0) + 1

        state.last_date = row_date
        state.n_processed += 1

    return state


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def walk_forward_elo(games_df: pd.DataFrame) -> pd.DataFrame:
    """Compute leak-free per-game pre-game Elo ratings and home win probability.

    For each game IN DATE ORDER:
      1. Apply any season-boundary regression (transition only, never re-applied).
      2. Record the PRE-game Elo ratings and home win probability (snapshot).
      3. Update ratings from the result.

    Parameters
    ----------
    games_df:
        DataFrame with columns: ``date``, ``season``, ``home_team``,
        ``away_team``, ``home_win`` (1.0/0.0).
        ``season`` must be int (callers map the NBA "YYYY-YY" string via
        ``_season_to_int``); ``int(df['season'])`` is consumed directly here.
        Extra columns are preserved.

    Returns
    -------
    pd.DataFrame
        Input rows in chronological order with added columns (all STRICTLY
        pre-game):
        ``elo_home``       — home team Elo before this game
        ``elo_away``       — away team Elo before this game
        ``elo_diff_hfa``   — (elo_home + ELO_HFA) - elo_away
        ``p_home_elo``     — P(home wins) = 1 / (1 + 10^(-elo_diff_hfa/400))
    """
    if len(games_df) == 0:
        out = games_df.copy()
        out["elo_home"] = pd.Series(dtype=float)
        out["elo_away"] = pd.Series(dtype=float)
        out["elo_diff_hfa"] = pd.Series(dtype=float)
        out["p_home_elo"] = pd.Series(dtype=float)
        return out

    df = _sorted(games_df)
    dates = pd.to_datetime(df["date"]).dt.date

    state = EloState()

    elo_homes: list[float] = []
    elo_aways: list[float] = []
    elo_diffs: list[float] = []
    p_homes: list[float] = []

    for i in range(len(df)):
        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        home_win = float(df["home_win"].iloc[i])

        # --- Step 1: season-boundary regression (before snapshot) ---
        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)

        # ---- RECORD PRE-GAME SNAPSHOT (leak-free) ----
        eh = state.elo[home]
        ea = state.elo[away]
        diff = (eh + ELO_HFA) - ea
        p = 1.0 / (1.0 + math.pow(10.0, -diff / 400.0))

        elo_homes.append(eh)
        elo_aways.append(ea)
        elo_diffs.append(diff)
        p_homes.append(p)

        # ---- UPDATE RATINGS (post-snapshot) ----
        s_home = 1.0 if home_win >= 0.5 else 0.0
        delta = ELO_K * (s_home - p)
        state.elo[home] += delta
        state.elo[away] -= delta

        state.counts[home] = state.counts.get(home, 0) + 1
        state.counts[away] = state.counts.get(away, 0) + 1

        state.last_date = dates.iloc[i]
        state.n_processed += 1

    out = df.copy()
    out["elo_home"] = elo_homes
    out["elo_away"] = elo_aways
    out["elo_diff_hfa"] = elo_diffs
    out["p_home_elo"] = p_homes
    return out


def elo_state_asof(games_df: pd.DataFrame, date: dt.date) -> EloState:
    """Return the EloState using only games strictly before ``date``.

    Equivalent to ``replay(games_df, until=date)`` — alias kept for the
    adapter API contract.

    Truncation-invariance guarantee:
        For integer-season inputs in the pinned sort order,
        ``elo_state_asof(full_df, D)`` produces an EloState identical to the
        one you would obtain by replaying only the subset of rows with
        ``date < D`` through a fresh ``replay()`` call.  Both paths execute
        the same sorted iteration in the same order — the same float
        operations in the same sequence.  Same-day games never feed each
        other because the cut is date-granular strict-before: all games ON
        date D are excluded.
    """
    return replay(games_df, until=date)
