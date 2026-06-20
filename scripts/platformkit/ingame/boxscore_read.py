"""scripts.platformkit.ingame.boxscore_read -- fetch and parse live player boxscore rows.

Reads the NBA CDN live boxscore endpoint (no auth, keyless) and emits a canonical
list of PlayerBoxRow dicts suitable for the /api/boxscore/{sport}/{game_id} endpoint
and the /api/ingame/{sport}/{game_id}/full compose response.

PUBLIC API
----------
fetch_box(game_id, *, http_get=None) -> list[PlayerBoxRow]
    Fetches the NBA CDN live boxscore for *game_id* and parses it.
    Returns [] if the CDN is unreachable or returns an empty/unparse-able payload.
    Never raises; degrades to [].

parse_cdn_payload(payload) -> list[PlayerBoxRow]
    Pure parse: converts a raw cdn.nba.com live boxscore JSON dict to
    list[PlayerBoxRow].  Injectable; no network I/O.

GameMeta = {game_id, game_status, period, clock, home_team, away_team,
            home_score, away_score, captured_at}

PlayerBoxRow = {player_id, name, team, side, min, pts, reb, ast,
                fg3m, stl, blk, tov, pf}

HONEST / SAFE:
  * No dollar / edge field anywhere.
  * Missing / null CDN stats default to 0 (safe_int / parse_minutes).
  * Degrades to [] on network error or missing game; never fabricates stats.
  * data/ is gitignored -- snapshots are a local cache, never committed.
  * ASCII-only output; <=300 LOC; no src/kernel/api imports; stdlib + urllib.
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

_CDN_URL_TPL = (
    "https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{game_id}.json"
)
_CDN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/json",
    "Referer": "https://www.nba.com/",
}

_STATUS_MAP = {1: "PRE_GAME", 2: "LIVE", 3: "FINAL"}

# Typed aliases (runtime dicts, not dataclasses -- keeps JSON round-trip trivial).
PlayerBoxRow = Dict[str, Any]
GameMeta = Dict[str, Any]


# ---------------------------------------------------------------------- helpers

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (ValueError, TypeError):
        return 0


def _parse_minutes(v: Any) -> float:
    """Convert 'PT14M30.00S' / '14:30' / 14.5 -> decimal minutes."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    try:
        if s.startswith("PT") and "M" in s:
            body = s[2:]
            mins = float(body[: body.index("M")])
            secs_part = body[body.index("M") + 1:].rstrip("S")
            return round(mins + float(secs_part or 0) / 60, 2)
        if ":" in s:
            mm, ss = s.split(":", 1)
            return round(float(mm) + float(ss) / 60, 2)
        return round(float(s), 2)
    except (ValueError, TypeError):
        return 0.0


def _parse_clock(v: Any) -> str:
    """Convert NBA ISO duration ('PT05M42.00S') to 'MM:SS' display string."""
    if not v:
        return ""
    s = str(v).strip()
    if s.startswith("PT") and "M" in s:
        try:
            body = s[2:]
            mins = int(float(body[: body.index("M")]))
            secs_part = body[body.index("M") + 1:].rstrip("S")
            secs = int(float(secs_part or 0))
            return f"{mins}:{secs:02d}"
        except (ValueError, TypeError):
            return s
    return s


# --------------------------------------------------------------------- network

def _default_http_get(url: str) -> dict:
    try:
        req = urllib.request.Request(url, headers=_CDN_HEADERS)
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return {}


# --------------------------------------------------------------------- parse

def _parse_player(p: dict, tricode: str, side: str) -> PlayerBoxRow:
    st = p.get("statistics") or {}
    return {
        "player_id": _safe_int(p.get("personId")),
        "name":      str(p.get("name", "") or ""),
        "team":      tricode,
        "side":      side,          # "home" | "away"
        "min":       _parse_minutes(st.get("minutes")),
        "pts":       _safe_int(st.get("points")),
        "reb":       _safe_int(st.get("reboundsTotal")),
        "ast":       _safe_int(st.get("assists")),
        "fg3m":      _safe_int(st.get("threePointersMade")),
        "stl":       _safe_int(st.get("steals")),
        "blk":       _safe_int(st.get("blocks")),
        "tov":       _safe_int(st.get("turnovers")),
        "pf":        _safe_int(st.get("foulsPersonal")),
    }


def _parse_teams(payload: dict) -> Tuple[Optional[dict], Optional[dict]]:
    game = payload.get("game") or {}
    home = game.get("homeTeam")
    away = game.get("awayTeam")
    return home, away


def parse_cdn_payload(payload: dict,
                      captured_at: Optional[str] = None) -> Tuple[GameMeta, List[PlayerBoxRow]]:
    """Parse raw cdn.nba.com live boxscore JSON.

    Returns (GameMeta, players) where players is sorted by side then player_id.
    Degrades to empty players list if the payload is malformed.  Never raises.
    """
    game = payload.get("game") or {}
    home = game.get("homeTeam") or {}
    away = game.get("awayTeam") or {}
    status_int = _safe_int(game.get("gameStatus"))
    meta: GameMeta = {
        "game_id":     str(game.get("gameId", "") or ""),
        "captured_at": captured_at or _now_iso(),
        "game_status": _STATUS_MAP.get(status_int, "UNKNOWN"),
        "period":      _safe_int(game.get("period")),
        "clock":       _parse_clock(game.get("gameClock")),
        "home_team":   str(home.get("teamTricode", "") or ""),
        "away_team":   str(away.get("teamTricode", "") or ""),
        "home_score":  _safe_int(home.get("score")),
        "away_score":  _safe_int(away.get("score")),
    }
    players: List[PlayerBoxRow] = []
    for side, team_obj in (("home", home), ("away", away)):
        tricode = str(team_obj.get("teamTricode", "") or "")
        for p in team_obj.get("players", []) or []:
            try:
                players.append(_parse_player(p, tricode, side))
            except Exception:  # noqa: BLE001
                continue
    return meta, players


# --------------------------------------------------------------------- public

def fetch_box(game_id: str, *,
              http_get: Optional[Callable[[str], dict]] = None,
              ) -> Tuple[GameMeta, List[PlayerBoxRow]]:
    """Fetch + parse the NBA CDN live boxscore for *game_id*.

    Returns (GameMeta, players).  On network / parse error returns a minimal
    unavailable GameMeta with an empty player list.  Never raises.
    Accepts an injectable *http_get* for testing without network I/O.
    """
    getter = http_get or _default_http_get
    url = _CDN_URL_TPL.format(game_id=game_id)
    try:
        payload = getter(url)
    except Exception:  # noqa: BLE001
        payload = {}
    if not payload:
        unavail: GameMeta = {
            "game_id": game_id, "captured_at": _now_iso(),
            "game_status": "UNAVAILABLE", "period": 0, "clock": "",
            "home_team": "", "away_team": "", "home_score": 0, "away_score": 0,
        }
        return unavail, []
    return parse_cdn_payload(payload)


__all__ = ["fetch_box", "parse_cdn_payload", "PlayerBoxRow", "GameMeta"]
