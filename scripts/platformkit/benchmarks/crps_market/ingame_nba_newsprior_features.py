"""scripts.platformkit.benchmarks.crps_market.ingame_nba_newsprior_features --
tip-time-knowable feature math for ingame_nba_newsprior.py (see that module's
docstring for the full knowability audit + honesty caveats). This file is
feature computation ONLY, no fitting/scoring.

SOURCE: data/domains/basketball_nba/player_boxscores.parquet (starter flag +
`min` per player-game). Ranking window is a TRAILING WINDOW of a team's last
TRAIL_WINDOW games strictly before the target date (not season-scoped) --
avoids a season-boundary cold start; early-season windows are noisier
(small known limitation, not corrected here).

KNOWABILITY:
  - star_out_{home,away}: an ACTUAL-PLAYED proxy for a tip-time scratch, not a
    real historical injury report (none exists for this corpus's span -- see
    ingame_nba_newsprior.py docstring). Conflates true tip-time outs with
    in-game exits, rest, and roster churn. Upper-bound-noisy, not causal.
  - n_starters_changed_{home,away}: same actual-outcome-proxy caveat.
  - b2b_{home,away} / rest_days: genuine schedule facts, no caveat -- derived
    purely from each team's own game-date history (nothing about THIS game's
    outcome is used).
"""
from __future__ import annotations

from typing import Dict, Optional, Set

import numpy as np
import pandas as pd

TRAIL_WINDOW = 15

FEATURE_COLUMNS = [
    "star_out_home", "star_out_away",
    "n_starters_changed_home", "n_starters_changed_away",
    "b2b_home", "b2b_away", "rest_days_diff",
]


def team_frames(pbox: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """team tricode -> that team's player-game rows, sorted by date."""
    return {t: g.sort_values("date") for t, g in pbox.groupby("team")}


def team_game_dates(pbox: pd.DataFrame) -> Dict[str, np.ndarray]:
    """team tricode -> sorted unique array of that team's game dates."""
    return {t: np.sort(g["date"].unique()) for t, g in pbox.groupby("team")}


def _prior_window(team_frame: pd.DataFrame, before_date: pd.Timestamp,
                  n_games: int = TRAIL_WINDOW) -> pd.DataFrame:
    prior = team_frame[team_frame["date"] < before_date]
    if prior.empty:
        return prior
    last_dates = prior["date"].drop_duplicates().nlargest(n_games)
    return prior[prior["date"].isin(last_dates)]


def _top3_usage_ids(window: pd.DataFrame) -> Set[int]:
    if window.empty:
        return set()
    return set(window.groupby("player_id")["min"].mean().nlargest(3).index)


def _modal_five_ids(window: pd.DataFrame) -> Set[int]:
    if window.empty:
        return set()
    starters = window[window["starter"].astype(bool)]
    if starters.empty:
        return set()
    return set(starters.groupby("player_id").size().nlargest(5).index)


def _star_out(game_team: pd.DataFrame, top3_ids: Set[int]) -> bool:
    """True if >=1 of the top-3 prior-usage players did not log min>0 in this
    game (absent from the boxscore OR present with min==0)."""
    if not top3_ids:
        return False
    played = set(game_team.loc[game_team["min"] > 0, "player_id"])
    return not top3_ids.issubset(played)


def _n_starters_changed(game_team: pd.DataFrame, modal_five: Set[int]) -> int:
    if not modal_five:
        return 0
    actual = set(game_team.loc[game_team["starter"].astype(bool), "player_id"])
    return len(modal_five - actual)


def _rest_days(dates: np.ndarray, game_date: pd.Timestamp) -> Optional[int]:
    prior = dates[dates < np.datetime64(game_date)]
    if len(prior) == 0:
        return None
    return int((game_date - pd.Timestamp(prior[-1])).days)


def build_features(pbox_by_team: Dict[str, pd.DataFrame],
                   dates_by_team: Dict[str, np.ndarray],
                   home: str, away: str, game_date) -> Dict[str, float]:
    """One row of FEATURE_COLUMNS for a single game. A team missing from
    player_boxscores (e.g. the post-2026-04-12 coverage tail) yields an
    honest all-zero/False row rather than a fabricated value."""
    ts = pd.Timestamp(game_date)
    out: Dict[str, float] = {}
    rest: Dict[str, Optional[int]] = {}
    for side, team in (("home", home), ("away", away)):
        tf = pbox_by_team.get(team)
        if tf is None:
            out[f"star_out_{side}"] = 0.0
            out[f"n_starters_changed_{side}"] = 0.0
            out[f"b2b_{side}"] = 0.0
            rest[side] = None
            continue
        window = _prior_window(tf, ts)
        top3 = _top3_usage_ids(window)
        modal5 = _modal_five_ids(window)
        game_team = tf[tf["date"] == ts]
        out[f"star_out_{side}"] = float(_star_out(game_team, top3))
        out[f"n_starters_changed_{side}"] = float(_n_starters_changed(game_team, modal5))
        rd = _rest_days(dates_by_team.get(team, np.array([], dtype="datetime64[ns]")), ts)
        rest[side] = rd
        out[f"b2b_{side}"] = float(rd == 1) if rd is not None else 0.0
    out["rest_days_diff"] = float((rest["home"] or 0) - (rest["away"] or 0))
    return out
