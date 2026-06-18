"""scripts.platformkit.odds_provider.prop_prizepicks -- keyless PrizePicks props.

PrizePicks publishes its DFS pick'em projections at a KEYLESS public JSON API.
Two calls: enumerate leagues, then pull projections for one league id. We look the
World Cup league id up BY NAME (not hardcoded) so it survives season changes.

REAL shapes (probed 2026-06-17):
  /leagues -> data[]: each {id, attributes.name}. World Cup league name == "WORLD
      CUP" (id was 241 today, but we resolve by name to stay durable).
  /projections?league_id=<id>&per_page=250&single_stat=true ->
    data[]    : one projection. attributes.stat_type (e.g. "Shots on Target"),
        attributes.line_score (the numeric line), attributes.odds_type
        ("standard" | "goblin" | "demon" -- flex variants), attributes.description
        (often the opponent), relationships.new_player.data.id, relationships.game.
    included[]: type "new_player" {id -> attributes.name, attributes.team};
        type "game" {id -> attributes.metadata.game_info.teams.{home,away}}.

Pricing: PrizePicks standard lines are PICK'EM -- no explicit two-sided American
odds in the payload. goblin/demon flex variants carry adjusted_odds=True but still
expose NO numeric two-sided price here. So we NEVER fabricate a price: over_price /
under_price = None and payout_type = "dfs_pickem" for every row. The honest
odds_type label is preserved by mapping it onto the canonical stat is NOT done; we
keep the raw odds_type only implicitly (rows are all pick'em). stat -> canon_stat.

No network at import. http_get is injectable; the default does keyless urllib GETs
with a browser UA + 12s timeout and returns {} on any error. fetch_props NEVER
raises -> returns the UNAVAILABLE sentinel instead.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from .base import is_unavailable, unavailable
from .prop_base import PropLine, canon_stat

logger = logging.getLogger(__name__)

_LEAGUES_URL = "https://api.prizepicks.com/leagues"
_PROJ_URL = ("https://api.prizepicks.com/projections"
             "?league_id={lid}&per_page=250&single_stat=true")
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# Our sport key -> the PrizePicks league NAME to look up (case-insensitive),
# resolved BY NAME (not id) so it survives id churn. Probed 2026-06-18: "MLB"
# (id 2 today, distinct from MLBLIVE/MLBSZN/MLBSZN2 -- exact-name match avoids the
# collision), "NBA" (id 7; empty in the off-season but wired and ready).
_LEAGUE_NAME: Dict[str, str] = {
    "soccer_intl": "WORLD CUP",
    "mlb": "MLB",
    "nba": "NBA",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_http_get(url: str) -> Dict[str, Any]:
    """One keyless GET with a browser UA; returns parsed JSON or {} on any error."""
    req = urllib.request.Request(
        url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001 -- never bubble a network error
        logger.warning("prizepicks GET failed: %s", exc)
        return {}


def _to_float(val: Any) -> Optional[float]:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def find_league_id(leagues_body: Dict[str, Any], name: str) -> Optional[str]:
    """Resolve a league NAME to its id from a /leagues payload (case-insensitive).

    Exact (normalized) name match first, so "WORLD CUP" does not collide with
    "WORLD CUP 1H" / "WORLD CUP TRNY". Returns None if not found.
    """
    if not isinstance(leagues_body, dict):
        return None
    want = " ".join(str(name).strip().lower().split())
    for d in leagues_body.get("data", []):
        if not isinstance(d, dict):
            continue
        nm = (d.get("attributes") or {}).get("name")
        if nm and " ".join(str(nm).strip().lower().split()) == want:
            return str(d.get("id")) if d.get("id") is not None else None
    return None


def _match_title(game: Optional[Dict[str, Any]]) -> Optional[str]:
    """Build a 'Home v Away' title from a game's nested metadata teams."""
    if not isinstance(game, dict):
        return None
    teams = (((game.get("attributes") or {}).get("metadata") or {})
             .get("game_info") or {}).get("teams") or {}
    home = (teams.get("home") or {}).get("abbreviation")
    away = (teams.get("away") or {}).get("abbreviation")
    if home and away:
        return "%s v %s" % (home, away)
    return None


def parse_props(proj_body: Dict[str, Any], sport: str,
                ) -> Union[List[PropLine], Dict[str, str]]:
    """Parse a /projections payload into PropLine rows (pure, no network).

    Joins each projection to its player (and game) via included[]. Every row is a
    DFS pick'em line: over/under prices None, payout_type "dfs_pickem". Returns the
    UNAVAILABLE sentinel when the payload is unusable or yields no rows.
    """
    if not isinstance(proj_body, dict):
        return unavailable("prizepicks: non-dict projections payload")
    data = proj_body.get("data")
    if not isinstance(data, list):
        return unavailable("prizepicks: missing data[]")

    players: Dict[str, Dict[str, Any]] = {}
    games: Dict[str, Dict[str, Any]] = {}
    for inc in proj_body.get("included", []):
        if not isinstance(inc, dict):
            continue
        if inc.get("type") == "new_player":
            players[str(inc.get("id"))] = inc
        elif inc.get("type") == "game":
            games[str(inc.get("id"))] = inc

    as_of = _now_iso()
    out: List[PropLine] = []
    for d in data:
        if not isinstance(d, dict) or d.get("type") != "projection":
            continue
        attr = d.get("attributes") or {}
        rel = d.get("relationships") or {}
        pid = ((rel.get("new_player") or {}).get("data") or {}).get("id")
        player = players.get(str(pid)) if pid is not None else None
        name = (player.get("attributes") or {}).get("name") if player else None
        line_val = _to_float(attr.get("line_score"))
        stat = attr.get("stat_type")
        if not name or stat is None or line_val is None:
            continue
        gid = ((rel.get("game") or {}).get("data") or {}).get("id")
        game = games.get(str(gid)) if gid is not None else None
        team = (player.get("attributes") or {}).get("team") if player else None

        out.append(PropLine(
            sport=sport,
            event_id=str(d.get("id") or ""),
            match=_match_title(game),
            player=name,
            team=team,
            stat=canon_stat(stat),
            line=line_val,
            over_price=None,   # pick'em: no honest two-sided price in payload
            under_price=None,
            payout_type="dfs_pickem",
            source="prizepicks",
            as_of=as_of,
        ))
    if not out:
        return unavailable("prizepicks: no rows for sport '%s'" % sport)
    return out


class PrizePicksProvider:
    """Keyless PrizePicks prop provider. fetch_props -> list[PropLine]|UNAVAILABLE."""

    name = "prizepicks"

    def __init__(self, *, http_get: Optional[Callable[[str], Any]] = None,
                 use_cache: bool = False) -> None:
        self._http_get = http_get or _default_http_get
        self._use_cache = use_cache  # reserved; live fetch is light + keyless
        self._league_id_cache: Dict[str, Optional[str]] = {}  # name -> id

    def _resolve_league_id(self, name: str) -> Optional[str]:
        if name in self._league_id_cache:
            return self._league_id_cache[name]
        body = self._http_get(_LEAGUES_URL)
        lid = None if is_unavailable(body) else find_league_id(body, name)
        self._league_id_cache[name] = lid
        return lid

    def fetch_props(self, sport: str,
                    ) -> Union[List[PropLine], Dict[str, str]]:
        sport = (sport or "").lower()
        league_name = _LEAGUE_NAME.get(sport)
        if not league_name:
            return unavailable("prizepicks: unsupported sport '%s'" % sport)
        try:
            lid = self._resolve_league_id(league_name)
            if not lid:
                return unavailable(
                    "prizepicks: league '%s' not found" % league_name)
            body = self._http_get(_PROJ_URL.format(lid=lid))
        except Exception as exc:  # noqa: BLE001 -- degrade, never bubble
            logger.warning("prizepicks fetch failed: %s", exc)
            return unavailable("prizepicks call failed (%s)" % type(exc).__name__)
        if is_unavailable(body):
            return body
        if not isinstance(body, dict) or not body:
            return unavailable("prizepicks: empty/invalid response")
        return parse_props(body, sport)


__all__ = ["PrizePicksProvider", "parse_props", "find_league_id"]
