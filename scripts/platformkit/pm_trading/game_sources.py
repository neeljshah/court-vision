"""game_sources.py -- Game dataclass and GameSource implementations.

Provides all "today's games" sources (each degrades to [] on any
network/parse error so the live runner never crashes when offline):
  MockGamesSource     -- deterministic, for tests.
  JSONFileSource      -- read data/pm_trading/games_today.json.
  NBAScoreboardSource -- src.live.pregame_probe.fetch_scoreboard (NBA, in-season).
  MLBStatsAPISource   -- statsapi.mlb.com schedule (KEYLESS, public; summer-live).

collect_games() fans out across a list of sources and merges results.
"""
from __future__ import annotations

import json
import pathlib
import sys
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Sequence

_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_GAMES_FILE = _ROOT / "data" / "pm_trading" / "games_today.json"

# MLB full team name -> abbreviation the MLB predictor expects. The predictor's
# set differs from MLB's official codes (KAN not KC, SDG not SD, SFG not SF,
# TAM not TB, WAS not WSH, OAK for Athletics), so map explicitly -- otherwise
# every game silently logs the home-field BASELINE (~0.534).
MLB_NAME_TO_ABBR = {
    "Arizona Diamondbacks": "ARI", "Athletics": "OAK", "Oakland Athletics": "OAK",
    "Atlanta Braves": "ATL", "Baltimore Orioles": "BAL", "Boston Red Sox": "BOS",
    "Chicago Cubs": "CHC", "Chicago White Sox": "CWS", "Cincinnati Reds": "CIN",
    "Cleveland Guardians": "CLE", "Colorado Rockies": "COL", "Detroit Tigers": "DET",
    "Houston Astros": "HOU", "Kansas City Royals": "KAN", "Los Angeles Angels": "LAA",
    "Los Angeles Dodgers": "LAD", "Miami Marlins": "MIA", "Milwaukee Brewers": "MIL",
    "Minnesota Twins": "MIN", "New York Mets": "NYM", "New York Yankees": "NYY",
    "Philadelphia Phillies": "PHI", "Pittsburgh Pirates": "PIT",
    "San Diego Padres": "SDG", "San Francisco Giants": "SFG",
    "Seattle Mariners": "SEA", "St. Louis Cardinals": "STL", "Tampa Bay Rays": "TAM",
    "Texas Rangers": "TEX", "Toronto Blue Jays": "TOR", "Washington Nationals": "WAS",
}


@dataclass
class Game:
    sport: str
    home: str
    away: str
    game_id: str = ""
    game_date: str = ""
    start_iso: str = ""
    # live in-game state (None for pregame); MLB: inning/half/runs
    inning: Optional[int] = None
    half: str = ""          # "top" | "bottom"
    home_runs: Optional[int] = None
    away_runs: Optional[int] = None
    state: str = ""         # "Preview" | "Live" | "Final"


class GameSource(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def fetch(self) -> List[Game]:
        ...


class MockGamesSource(GameSource):
    def __init__(self, games: Sequence[Game]) -> None:
        self._games = list(games)

    @property
    def name(self) -> str:
        return "mock"

    def fetch(self) -> List[Game]:
        return list(self._games)


class JSONFileSource(GameSource):
    """Reads a local list of today's real matchups you/the agent maintain."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = pathlib.Path(path) if path else _GAMES_FILE

    @property
    def name(self) -> str:
        return "json_file"

    def fetch(self) -> List[Game]:
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        out = []
        for r in rows or []:
            try:
                out.append(Game(
                    sport=r["sport"], home=r["home"], away=r["away"],
                    game_id=r.get("game_id", ""),
                    game_date=r.get("game_date", ""),
                    start_iso=r.get("start_iso", ""),
                ))
            except Exception:
                continue
        return out


class NBAScoreboardSource(GameSource):
    @property
    def name(self) -> str:
        return "nba_scoreboard"

    def fetch(self) -> List[Game]:
        try:
            from src.live.pregame_probe import fetch_scoreboard  # lazy + network
            sb = fetch_scoreboard(timeout=10.0) or {}
        except Exception:
            return []
        games = ((sb.get("scoreboard") or {}).get("games")) or []
        out = []
        for g in games:
            try:
                out.append(Game(
                    sport="nba",
                    home=g["homeTeam"]["teamTricode"],
                    away=g["awayTeam"]["teamTricode"],
                    game_id=str(g.get("gameId", "")),
                    start_iso=g.get("gameEt", "") or "",
                ))
            except Exception:
                continue
        return out


class MLBStatsAPISource(GameSource):
    """Keyless public MLB schedule -- the summer live source."""

    def __init__(self, date: str = "") -> None:
        self.date = date  # YYYY-MM-DD; "" => today on the server

    @property
    def name(self) -> str:
        return "mlb_statsapi"

    def fetch(self) -> List[Game]:
        url = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
        if self.date:
            url += "&date=%s" % self.date
        try:
            with urllib.request.urlopen(url, timeout=10.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []
        out = []
        for d in data.get("dates", []):
            for g in d.get("games", []):
                try:
                    teams = g["teams"]
                    hname = teams["home"]["team"]["name"]
                    aname = teams["away"]["team"]["name"]
                    out.append(Game(
                        sport="mlb",
                        home=MLB_NAME_TO_ABBR.get(hname, hname),
                        away=MLB_NAME_TO_ABBR.get(aname, aname),
                        game_id=str(g.get("gamePk", "")),
                        game_date=d.get("date", ""),
                        start_iso=g.get("gameDate", "") or "",
                    ))
                except Exception:
                    continue
        return out


def collect_games(sources: Sequence[GameSource]) -> List[Game]:
    out: List[Game] = []
    for src in sources:
        try:
            out.extend(src.fetch())
        except Exception:
            continue
    return out


__all__ = [
    "MLB_NAME_TO_ABBR",
    "Game", "GameSource",
    "MockGamesSource", "JSONFileSource",
    "NBAScoreboardSource", "MLBStatsAPISource",
    "collect_games",
]
