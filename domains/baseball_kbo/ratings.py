"""domains.baseball_kbo.ratings -- leak-free walk-forward Elo ratings for KBO games.

Thin local mirror of domains.baseball_npb.ratings (itself a mirror of
domains.basketball_wnba.ratings / domains.basketball_nba.ratings): SAME
replay algorithm (Elo + home-court advantage + between-season mean-
regression, snapshot-before-update), parameterized by
domains.baseball_kbo.elo_config. Duplicated rather than imported for the same
self-containment reason as NPB (no injection seam into the NBA/MLB engines;
domains.mlb is not sport-blind-importable -- F5 rule).

TIES (KBO allows draws): a tied game has home_win=NaN. NaN-labeled rows are
EXCLUDED from the Elo update (no winner signal to learn from) but their
PRE-GAME ratings are still recorded in the walk-forward output.

Input DataFrame columns (from ingest_kbo.ingest_seasons): date, season,
home_team, away_team, home_score, away_score, home_win (1.0/0.0/NaN for a
tie), tied (bool). Only date, season, home_team, away_team, home_win are
consumed here; extra columns are preserved in the output.

PRIVATE: outputs are price-bearing when combined with odds; data/domains/kbo/
is never tracked. No src.*/kernel.*/other-domain imports (F5 compliance).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/baseball_kbo/test_ratings.py -q
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

from domains.baseball_kbo.elo_config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EloState:
    """Snapshot of team Elo ratings at a point in time.

    ``elo``         : team_name -> Elo rating (float)
    ``counts``      : team_name -> number of DECISIVE (non-tied) games processed
    ``last_season`` : team_name -> season int of the last processed game
    ``last_date``   : date of the last processed game (None if empty)
    ``n_processed`` : total rows processed (decisive + tied)
    ``n_tied``      : rows skipped from the Elo UPDATE because they were tied
    """

    elo: Dict[str, float] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)
    last_season: Dict[str, int] = field(default_factory=dict)
    last_date: Optional[dt.date] = None
    n_processed: int = 0
    n_tied: int = 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Return ``df`` sorted by pinned chronological order.

    Key: (date, home_team, away_team) -- mergesort-stable so ties within the
    same game-day retain deterministic order.
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
    """P(home team wins) given pre-game Elo ratings with HFA applied.

        d = (elo_home + ELO_HFA) - elo_away
        p = 1 / (1 + 10 ** (-d / 400))
    """
    d = (elo_home + ELO_HFA) - elo_away
    return 1.0 / (1.0 + math.pow(10.0, -d / 400.0))


def _maybe_regress(state: EloState, team: str, season: int) -> None:
    """Apply season-boundary regression for ``team`` if season changed.

    Initialises unseen teams to ELO_MEAN before use. Applies regression at
    most once per team per season transition -- keyed to processed rows.
    """
    if team not in state.elo:
        state.elo[team] = ELO_MEAN
        state.last_season[team] = season
        return

    prev_season = state.last_season.get(team)
    if prev_season is not None and prev_season != season:
        state.elo[team] += SEASON_REGRESS * (ELO_MEAN - state.elo[team])
        state.last_season[team] = season


def _is_tied_row(home_win) -> bool:
    """True iff the row's home_win label is NaN (a recorded KBO draw)."""
    try:
        return bool(pd.isna(home_win))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def replay(games: pd.DataFrame, until: Optional[dt.date] = None) -> EloState:
    """Replay games in chronological order and return the resulting EloState.

    ``until``: if provided, process only games with ``date < until`` (strictly
    before) -- the AsOfContext.decision_time contract. A tied row still
    advances last_date/n_processed bookkeeping but never updates Elo (no
    winner signal).
    """
    if len(games) == 0:
        return EloState()

    df = _sorted(games)
    dates = pd.to_datetime(df["date"]).dt.date

    state = EloState()

    for i in range(len(df)):
        row_date = dates.iloc[i]

        if until is not None and row_date >= until:
            continue

        home = str(df["home_team"].iloc[i])
        away = str(df["away_team"].iloc[i])
        season = int(df["season"].iloc[i])
        home_win = df["home_win"].iloc[i]

        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)

        if _is_tied_row(home_win):
            state.n_tied += 1
        else:
            p = _p_home(state.elo[home], state.elo[away])
            s_home = 1.0 if float(home_win) >= 0.5 else 0.0
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
    """Leak-free per-game pre-game Elo ratings and home win probability.

    Returns input rows in chronological order with added columns (all
    STRICTLY pre-game): elo_home, elo_away, elo_diff_hfa, p_home_elo. A tied
    row is still fully represented in the output (its pre-game ratings ARE
    recorded) but does not perturb the ratings used for later rows.
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
        home_win = df["home_win"].iloc[i]

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

        # ---- UPDATE RATINGS (post-snapshot; skipped for a tie) ----
        if _is_tied_row(home_win):
            state.n_tied += 1
        else:
            s_home = 1.0 if float(home_win) >= 0.5 else 0.0
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
    """EloState using only games strictly before ``date`` (adapter API
    contract).

    Truncation-invariance: for a pinned sort order, elo_state_asof(full_df, D)
    replays the identical sequence a fresh replay() on the date<D subset
    would -- same float ops in the same order. Same-day games never feed each
    other (date-granular strict-before cut).
    """
    return replay(games_df, until=date)


__all__ = ["EloState", "replay", "walk_forward_elo", "elo_state_asof"]
