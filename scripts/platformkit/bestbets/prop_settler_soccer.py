"""scripts.platformkit.bestbets.prop_settler_soccer -- resolve the REAL post-match stat for
a soccer (World Cup / international) player-prop row from the keyless ESPN site API. Best-
effort: ANY gap (match not final / player not found / stat not keyless-readable) returns None
so the prop stays PENDING and is NEVER fabricated.

WHAT IS KEYLESS-RESOLVABLE (the honest boundary):
  * Goals / Assists / Goal+Assist / Cards -- from summary.keyEvents (every goal/assist/card
    emits an event naming the athlete, so absence is a genuine 0 for a player on the pitch).
  * Shots / Saves -- ONLY for the match LEADER in that category (summary.leaders gives the top
    player per category, not a full per-player table). A non-leader -> None (pending).
  * Shots On Target -- NOT keyless-resolvable (no per-player SOT in the feed) -> always None.

Flow: matchup teams + game_date -> ESPN scoreboard (FINAL only) event id -> summary -> read
the player's stat. Reuses ingame_box_soccer for the keyEvents tally (no parallel parse).

INJECTABLE http_get(url)->dict so the resolver is offline-testable.
RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; never raises.
Per-file test: scripts/platformkit/bestbets/test_prop_settler_soccer.py
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, Optional

from scripts.platformkit.bestbets.prop_settler_mlb import _matchup_teams, _norm, _team_hit
from scripts.platformkit.ingame import ingame_box_soccer as _box

logger = logging.getLogger(__name__)

_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUE_PATHS = {"soccer_intl": ["soccer/fifa.world"], "soccer": ["soccer/eng.1"]}
_FINAL_STATES = ("post",)  # ESPN status.type.state for a completed match
# canonical prop_stat -> ESPN summary.leaders category name (leader-only resolution).
_LEADER_CAT = {"Shots": "totalShots", "Saves": "saves"}


def _http_get_json(url: str) -> Dict[str, Any]:
    """Keyless GET, preferring the shared disk cache (a FINAL match's scoreboard/summary is
    immutable, so caching it spares the settle daemon from re-fetching every tick). Falls
    back to a direct request; {} on any failure."""
    try:
        from scripts.platformkit.odds_provider.http_cache import disk_cache_get
        out = disk_cache_get(url)
        if isinstance(out, dict) and out:
            return out
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settler_soccer: cache GET %s failed: %s", url, exc)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settler_soccer: GET %s failed: %s", url, exc)
        return {}


def _find_final_event(teams: tuple, game_date: str, sport: str,
                      get: Callable[[str], Dict[str, Any]]) -> Optional[tuple]:
    """(event_id, league_path) of the FINAL match whose two teams match *teams*, else None."""
    want = {_norm(teams[0]), _norm(teams[1])}
    date_q = ("?dates=%s" % game_date.replace("-", "")) if game_date else ""
    for path in _LEAGUE_PATHS.get(str(sport).lower(), []):
        board = get("%s/%s/scoreboard%s" % (_SITE, path, date_q)) or {}
        for ev in board.get("events", []) or []:
            comp = (ev.get("competitions") or [{}])[0]
            state = str(((comp.get("status") or {}).get("type") or {}).get("state", "")).lower()
            if state not in _FINAL_STATES:
                continue
            hn = an = ""
            for c in comp.get("competitors", []) or []:
                nm = _norm((c.get("team") or {}).get("displayName")
                           or (c.get("team") or {}).get("name"))
                if c.get("homeAway") == "home":
                    hn = nm
                elif c.get("homeAway") == "away":
                    an = nm
            if _team_hit(want, hn, an):
                eid = str(ev.get("id") or "")
                if eid:
                    return eid, path
    return None


def _leader_value(summary: Dict[str, Any], cat_name: str, player: str) -> Optional[float]:
    """The player's value for ESPN leader category *cat_name*, ONLY if they are the listed
    leader (the feed exposes the top player only). None otherwise -- never a fabricated 0."""
    pkey = _norm(player)
    for tb in summary.get("leaders", []) or []:
        for cat in tb.get("leaders", []) or []:
            if str(cat.get("name")) != cat_name:
                continue
            for a in cat.get("leaders", []) or []:
                nm = _norm((a.get("athlete") or {}).get("displayName"))
                if nm and (nm == pkey or pkey in nm or nm in pkey):
                    val = a.get("value")
                    if val is None:
                        val = a.get("displayValue")
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return None
    return None


def soccer_realized_stat(row: Dict[str, Any],
                         *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
                         ) -> Optional[float]:
    """Realized value of a soccer prop row's stat, or None (match not final / unresolvable).

    Never raises. Reads row: matchup, game_date, prop_player, prop_stat, sport. None on ANY
    gap so the prop stays PENDING -- never a fabricated outcome.
    """
    get = http_get or _http_get_json
    sport = str(row.get("sport") or "soccer_intl").strip().lower()
    teams = _matchup_teams(row.get("matchup"))
    player = str(row.get("prop_player") or "")
    stat = str(row.get("prop_stat") or "").strip()
    if not teams or not player or not stat:
        return None
    found = _find_final_event(teams, str(row.get("game_date") or "")[:10], sport, get)
    if not found:
        return None  # no FINAL match for this matchup/date -> pending (not 0!)
    eid, path = found
    # event-derivable families: goals / assists / goal+assist / cards (full coverage).
    if _box.is_known_stat(stat):
        stat_map = _box.boxscore_stat_map(eid, http_get=get, sport=sport)
        return _box.realized_for(stat, stat_map, player)
    # leader-only families: shots / saves (resolved only for the match leader).
    cat = _LEADER_CAT.get(stat)
    if cat is None:
        return None  # e.g. Shots On Target: no per-player feed -> permanently unresolvable
    summary = get("%s/%s/summary?event=%s" % (_SITE, path, eid)) or {}
    return _leader_value(summary, cat, player)


__all__ = ["soccer_realized_stat"]
