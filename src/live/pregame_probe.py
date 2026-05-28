"""pregame_probe.py — fetch scheduled-game info from cdn.nba.com.

The live-game CDN endpoint (`boxscore_<id>.json`) only publishes
JSON once the game tips off. Until then it 403s. This probe hits
the always-available `todaysScoreboard_00.json` (and the static
league schedule as a fallback) to surface:

  * official matchup
  * tipoff time (ET / UTC)
  * the API's current game-status text (e.g. "8:30 pm ET", "PPD")

Used by the orchestrator to broadcast a ``pregame.info`` event so
the web dashboard has something meaningful to show before tipoff.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

log = logging.getLogger("pregame_probe")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.nba.com/",
    "Origin": "https://www.nba.com",
}

_SCOREBOARD_URL = (
    "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
)
_SCHEDULE_URL = (
    "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
)


def fetch_scoreboard(*, timeout: float = 10.0) -> Dict[str, Any]:
    """Return today's full scoreboard JSON, or empty dict on failure."""
    try:
        r = requests.get(_SCOREBOARD_URL, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json() or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("scoreboard fetch failed: %s", exc)
        return {}


def fetch_schedule(*, timeout: float = 20.0) -> Dict[str, Any]:
    """Return the static-data full season schedule. Heavy (~8 MB)."""
    try:
        r = requests.get(_SCHEDULE_URL, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        return r.json() or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("schedule fetch failed: %s", exc)
        return {}


def probe_game(game_id: str) -> Dict[str, Any]:
    """Build a pregame-info payload for ``game_id``.

    Looks first at the live scoreboard (today's slate). Falls back
    to the static schedule if the game isn't on today's slate yet
    (offseason / future-day testing).

    Returns
    -------
    dict
        Shape::

            {
              "game_id":      "0042500315",
              "home_team":    "OKC",
              "away_team":    "SAS",
              "home_team_id": 1610612760,
              "away_team_id": 1610612759,
              "game_status_text": "8:30 pm ET" | "Live" | "Final" | ...,
              "tipoff_iso":   "2026-05-26T20:30:00-04:00" | None,
              "scheduled":    True/False,
              "found_in":     "scoreboard" | "schedule" | None,
              "fetched_at":   <unix sec>,
            }
    """
    out: Dict[str, Any] = {
        "game_id": game_id,
        "home_team": None,
        "away_team": None,
        "home_team_id": None,
        "away_team_id": None,
        "game_status_text": None,
        "tipoff_iso": None,
        "scheduled": False,
        "found_in": None,
        "fetched_at": time.time(),
    }
    sb = fetch_scoreboard()
    sb_games = (sb.get("scoreboard") or {}).get("games") or []
    for g in sb_games:
        if g.get("gameId") == game_id:
            _fill_from_scoreboard(out, g)
            out["found_in"] = "scoreboard"
            return out

    # Fallback: static schedule (only need it if game isn't on today's slate).
    sched = fetch_schedule()
    for d in (sched.get("leagueSchedule") or {}).get("gameDates") or []:
        for g in d.get("games") or []:
            if g.get("gameId") == game_id:
                _fill_from_schedule(out, g)
                out["found_in"] = "schedule"
                return out
    return out


def _fill_from_scoreboard(out: Dict[str, Any], g: Dict[str, Any]) -> None:
    home = g.get("homeTeam") or {}
    away = g.get("awayTeam") or {}
    out["home_team"] = home.get("teamTricode")
    out["away_team"] = away.get("teamTricode")
    out["home_team_id"] = home.get("teamId")
    out["away_team_id"] = away.get("teamId")
    out["game_status_text"] = g.get("gameStatusText")
    out["tipoff_iso"] = g.get("gameEt") or g.get("gameTimeUTC")
    out["scheduled"] = bool(out["tipoff_iso"])


def _fill_from_schedule(out: Dict[str, Any], g: Dict[str, Any]) -> None:
    home = g.get("homeTeam") or {}
    away = g.get("awayTeam") or {}
    out["home_team"] = home.get("teamTricode")
    out["away_team"] = away.get("teamTricode")
    out["home_team_id"] = home.get("teamId")
    out["away_team_id"] = away.get("teamId")
    out["game_status_text"] = g.get("gameStatusText") or g.get("gameStatus")
    out["tipoff_iso"] = g.get("gameDateTimeEst") or g.get("gameDateTimeUTC")
    out["scheduled"] = bool(out["tipoff_iso"])
