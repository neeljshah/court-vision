"""
elo.py — FiveThirtyEight-style Team ELO ratings for NBA win probability.

Improvements over the legacy advanced_features.build_elo_ratings:
  - Home court adjustment: +85 elo points for E calculation (not updates)
  - Margin-of-victory multiplier applied to K (auto-corrects lucky close wins)
  - Season-to-season regression: 25% pull toward 1505 mean at each new season
  - K = 20 base

Public API
----------
    class TeamElo
    build_elo_history(seasons) -> pd.DataFrame
    compute_game_elo_lookup_v2(seasons) -> dict   # drop-in replacement
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, List, Optional

import pandas as pd

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_NBA_CACHE   = os.path.join(_PROJECT_DIR, "data", "nba")
_ELO_STATE_PATH = os.path.join(_PROJECT_DIR, "data", "models", "elo_state.json")

# FiveThirtyEight constants (NBA variant)
_K          = 20
_HOME_ADV   = 85      # elo pts added to home rating for E calc only
_MEAN_ELO   = 1505.0  # long-run mean (FTE uses 1505 not 1500)
_START_ELO  = 1500.0  # fresh-team starting elo
_REGRESSION = 0.25    # 25% revert to mean between seasons


def _win_prob(home_elo: float, away_elo: float) -> float:
    """Expected win prob for home team with home-court adjustment."""
    return 1.0 / (1.0 + 10.0 ** ((away_elo - (home_elo + _HOME_ADV)) / 400.0))


def _mov_multiplier(margin: float, elo_diff: float) -> float:
    """
    Margin-of-victory multiplier for K.

    FiveThirtyEight formula:
        mov_mult = ln(|margin| + 1) * (2.2 / ((elo_diff * 0.001) + 2.2))

    Caps mov_mult at 3.0 to prevent one blowout from distorting ratings too much.
    """
    if margin == 0:
        return 1.0
    raw = math.log(abs(margin) + 1) * (2.2 / (abs(elo_diff) * 0.001 + 2.2))
    return min(raw, 3.0)


class TeamElo:
    """
    FiveThirtyEight-style NBA ELO tracker.

    Ratings are stored as {team_abbr: float} and updated game-by-game.
    Supports multi-season operation with end-of-season regression.
    """

    def __init__(self, ratings: Optional[Dict[str, float]] = None):
        self._ratings: Dict[str, float] = dict(ratings or {})
        self._current_season: Optional[str] = None

    def _init_team(self, team: str) -> None:
        if team not in self._ratings:
            self._ratings[team] = _START_ELO

    def _regress_to_mean(self) -> None:
        """Pull all ratings 25% toward the mean at the start of a new season."""
        for team in self._ratings:
            self._ratings[team] = round(
                self._ratings[team] * (1 - _REGRESSION) + _MEAN_ELO * _REGRESSION, 2
            )

    def rating(self, team: str) -> float:
        """Return current rating for a team (1500 if unseen)."""
        return self._ratings.get(team, _START_ELO)

    def update(
        self,
        home_abbr: str,
        away_abbr: str,
        home_score: float,
        away_score: float,
        season: str,
    ) -> tuple[float, float]:
        """
        Update ratings after a game. Returns (home_elo_pre, away_elo_pre) snapshots.

        Args:
            home_abbr:  Home team abbreviation.
            away_abbr:  Away team abbreviation.
            home_score: Final home score.
            away_score: Final away score.
            season:     Season string e.g. "2024-25".

        Returns:
            (home_elo_before_update, away_elo_before_update)
        """
        # Season transition — regress ratings once at first game of a new season
        if season != self._current_season:
            if self._current_season is not None:
                self._regress_to_mean()
            self._current_season = season

        self._init_team(home_abbr)
        self._init_team(away_abbr)

        h_pre = self._ratings[home_abbr]
        a_pre = self._ratings[away_abbr]

        exp_home = _win_prob(h_pre, a_pre)
        actual   = 1.0 if home_score > away_score else (0.5 if home_score == away_score else 0.0)
        margin   = home_score - away_score
        elo_diff = h_pre - a_pre
        mov_mult = _mov_multiplier(margin, elo_diff) if actual != 0.5 else 1.0

        delta = _K * mov_mult * (actual - exp_home)
        self._ratings[home_abbr] = round(h_pre + delta, 2)
        self._ratings[away_abbr] = round(a_pre - delta, 2)

        return h_pre, a_pre

    def to_dict(self) -> dict:
        return {"ratings": dict(self._ratings), "current_season": self._current_season}

    @classmethod
    def from_dict(cls, d: dict) -> "TeamElo":
        obj = cls(ratings=d.get("ratings", {}))
        obj._current_season = d.get("current_season")
        return obj


def _load_season_rows(season: str) -> List[dict]:
    """Load rows from season_games_{season}.json. Returns [] on miss."""
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        return []
    try:
        payload = json.load(open(path))
        if isinstance(payload, dict):
            return payload.get("rows", [])
        return payload
    except Exception:
        return []


def build_elo_history(seasons: List[str]) -> pd.DataFrame:
    """
    Walk all games chronologically and return a DataFrame with pre-game ELO.

    Columns: game_id, home_team, away_team, game_date, season,
             home_elo_pre, away_elo_pre, elo_diff

    Args:
        seasons: Season strings in chronological order e.g. ["2022-23","2023-24","2024-25"].

    Returns:
        DataFrame sorted by game_date.
    """
    all_games: List[dict] = []
    for s in seasons:
        rows = _load_season_rows(s)
        all_games.extend(rows)

    if not all_games:
        return pd.DataFrame()

    all_games.sort(key=lambda g: (g.get("game_date", ""), g.get("game_id", "")))

    tracker = TeamElo()
    records = []
    for g in all_games:
        home  = str(g.get("home_team", ""))
        away  = str(g.get("away_team", ""))
        gid   = str(g.get("game_id", ""))
        date  = str(g.get("game_date", ""))
        ssn   = str(g.get("season", seasons[0]))

        # Need scores to compute MOV — fall back to home_win if no scores
        home_score = float(g.get("home_score", 0) or 0)
        away_score = float(g.get("away_score", 0) or 0)

        if home_score == 0 and away_score == 0:
            # No scores in cache — infer from home_win (0/1), use margin=1
            hw = g.get("home_win")
            if hw == 1:
                home_score, away_score = 101.0, 100.0
            elif hw == 0:
                home_score, away_score = 100.0, 101.0

        if not home or not away:
            continue

        h_pre, a_pre = tracker.update(home, away, home_score, away_score, ssn)

        records.append({
            "game_id":     gid,
            "home_team":   home,
            "away_team":   away,
            "game_date":   date,
            "season":      ssn,
            "home_elo_pre": round(h_pre, 2),
            "away_elo_pre": round(a_pre, 2),
            "elo_diff":    round(h_pre - a_pre, 2),
        })

    # Persist final state
    os.makedirs(os.path.dirname(_ELO_STATE_PATH), exist_ok=True)
    try:
        with open(_ELO_STATE_PATH, "w") as f:
            json.dump(tracker.to_dict(), f)
    except Exception:
        pass

    return pd.DataFrame(records)


def compute_game_elo_lookup_v2(seasons: List[str]) -> dict:
    """
    Build game_id → {"home_elo": float, "away_elo": float} with the improved formula.

    Drop-in replacement for advanced_features.compute_game_elo_lookup.
    Uses K=20 + MOV multiplier + home_adj=85 + 25% season regression.

    Args:
        seasons: Season strings in chronological order.

    Returns:
        Dict mapping str(game_id) → {"home_elo": float, "away_elo": float}.
    """
    df = build_elo_history(seasons)
    if df.empty:
        return {}
    return {
        str(row["game_id"]): {
            "home_elo": float(row["home_elo_pre"]),
            "away_elo": float(row["away_elo_pre"]),
        }
        for _, row in df.iterrows()
    }


def get_current_elo(team_abbr: str) -> float:
    """Return current (most recent) ELO for a team from the persisted state. 1500 on miss."""
    try:
        if not os.path.exists(_ELO_STATE_PATH):
            return _START_ELO
        state = json.load(open(_ELO_STATE_PATH))
        return float(state.get("ratings", {}).get(team_abbr, _START_ELO))
    except Exception:
        return _START_ELO
