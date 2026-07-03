"""domains.basketball_wnba.ratings -- leak-free walk-forward Elo ratings for WNBA games.

Thin local mirror of domains.basketball_nba.ratings: SAME replay algorithm (Elo +
home-court advantage + between-season mean-regression, snapshot-before-update),
parameterized by domains.basketball_wnba.elo_config instead of the NBA config.
Not imported from basketball_nba directly because that module hardcodes the NBA
ELO_K/ELO_HFA/SEASON_REGRESS constants at import time (no injection seam) --
duplicating the ~230-line replay engine here is the leak-free, config-correct path
without editing the human-gated basketball_nba module (see .claude/rules/human-
gated-paths.md -- domains/basketball_nba is NOT in this lane's edit scope anyway;
this file lives entirely under domains/basketball_wnba, which is in-scope).

Replay a chronologically-sorted sequence of games and emit per-game PRE-game team
Elo ratings (leak-free features). Ratings update AFTER the pre-game snapshot is
recorded -- future results can never contaminate features.

Input DataFrame columns (from ingest_espn.ingest_seasons):
  event_id, date, season, home_team, away_team, home_score, away_score, home_win
  (1.0/0.0), neutral_site, status_name.
  Only date, season, home_team, away_team, home_win are consumed here; extra
  columns are preserved in the output.

PRIVATE: outputs are price-bearing when combined with odds; data/domains/wnba/ is
never tracked. No src.* / kernel.* / other-domain imports (falsifier F5 compliance).
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

from domains.basketball_wnba.elo_config import ELO_K, ELO_MEAN, ELO_HFA, SEASON_REGRESS

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class EloState:
    """Snapshot of team Elo ratings at a point in time.

    ``elo``         : team_name -> Elo rating (float)
    ``counts``      : team_name -> number of games processed
    ``last_season`` : team_name -> season int of the last processed game
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

    Initialises unseen teams to ELO_MEAN before use. Applies regression at most
    once per team per season transition -- keyed to processed rows.
    """
    if team not in state.elo:
        state.elo[team] = ELO_MEAN
        state.last_season[team] = season
        return

    prev_season = state.last_season.get(team)
    if prev_season is not None and prev_season != season:
        state.elo[team] += SEASON_REGRESS * (ELO_MEAN - state.elo[team])
        state.last_season[team] = season


# ---------------------------------------------------------------------------
# Core replay engine
# ---------------------------------------------------------------------------


def replay(games: pd.DataFrame, until: Optional[dt.date] = None) -> EloState:
    """Replay games in chronological order and return the resulting EloState.

    ``until``: if provided, process only games with ``date < until`` (strictly
    before) -- the AsOfContext.decision_time contract.
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
        home_win = float(df["home_win"].iloc[i])

        _maybe_regress(state, home, season)
        _maybe_regress(state, away, season)

        p = _p_home(state.elo[home], state.elo[away])

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
    """Leak-free per-game pre-game Elo ratings and home win probability.

    Returns input rows in chronological order with added columns (all STRICTLY
    pre-game): elo_home, elo_away, elo_diff_hfa, p_home_elo.
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
    """EloState using only games strictly before ``date`` (adapter API contract).

    Truncation-invariance: for a pinned sort order, elo_state_asof(full_df, D)
    replays the identical sequence a fresh replay() on the date<D subset would --
    same float ops in the same order. Same-day games never feed each other
    (date-granular strict-before cut).
    """
    return replay(games_df, until=date)


__all__ = ["EloState", "replay", "walk_forward_elo", "elo_state_asof"]
