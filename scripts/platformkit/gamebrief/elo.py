"""Pregame Elo win probability for one historical NBA game.

Reuses GenericRatingModel's leak-free walk-forward Elo as-is (no new modeling,
no re-tuned constants) -- this module only locates the target game inside the
walk-forward output.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from scripts.platformkit.generic_rating import GenericRatingModel

_HFA = 65.0  # NBA constant pinned in generic_rating._SPORT_HFA; mirrored here
# rather than importing a private module dict.


def pregame_prob(games_df: pd.DataFrame, home: str, away: str, date: Any) -> Optional[Dict]:
    """Leak-free pregame home-win prob for the (home, away, date) game, found by
    replaying every prior game in `games_df` through the shared Elo model."""
    df = games_df.sort_values("date").reset_index(drop=True)
    target_date = pd.Timestamp(date)
    mask = (df["date"] == target_date) & (
        ((df["home_team"] == home) & (df["away_team"] == away))
        | ((df["home_team"] == away) & (df["away_team"] == home))
    )
    idx = df.index[mask]
    if len(idx) == 0:
        return None
    i = int(idx[0])

    recs = [
        {"home": r.home_team, "away": r.away_team, "season": r.season, "home_win": float(r.home_win)}
        for r in df.itertuples()
    ]
    probs = GenericRatingModel(hfa=_HFA).walkforward(recs)
    p_home_team_wins = float(probs[i])
    matchup_home = df.loc[i, "home_team"]
    if matchup_home != home:  # requested "home" is actually away in the stored row
        p_home_team_wins = 1.0 - p_home_team_wins
    return {
        "game_id": str(df.loc[i, "game_id"]),
        "home_win_prob": round(p_home_team_wins, 4),
        "away_win_prob": round(1.0 - p_home_team_wins, 4),
        "n_prior_games_in_history": i,
    }
