"""scripts.platformkit.ingame.ingame_box_soccer -- LIVE soccer realized-stat reader.

The in-game prop re-pricer needs, per player, two LIVE inputs: realized_so_far (the
running tally for the stat) and frac_elapsed (how much of the match is gone). For MLB
the rich keyless statsapi boxscore supplies every batting/pitching count. ESPN's keyless
soccer feed is far thinner: the `boxscore.players` block is EMPTY and the team stat block
is empty, so there is NO per-player shots / shots-on-target / saves / fouls feed.

What ESPN DOES expose keyless and reliably per player is the discrete EVENT stream
(`summary.keyEvents`) -- every goal, assist and card emits an event naming the athlete --
plus the matchday `rosters`. So this module reads ONLY the stats that decompose cleanly
from those events and are HONESTLY zero in their absence (a player on the pitch with no
goal event genuinely has 0 goals -- unlike shots, where no data != zero):

  * live_games()            -> in-progress WC/international matches (event id + frac)
  * boxscore_stat_map(eid)  -> {player_norm: {"Goals","Assists","Cards"}} (rostered=0-seeded)
  * realized_for(stat, m, p)-> the player's running Goals / Assists / Goal+Assist / Cards
  * is_known_stat(stat)     -> True ONLY for those event-derivable families (else skip)

Shots / Shots On Target / Saves / Fouls are NOT knowable per-player from this keyless feed
(absence != 0), so is_known_stat returns False for them and the trader skips them rather
than re-pricing on a fabricated zero. That is the honest boundary, not a missing feature.

HONEST RAILS (binding): keyless public ESPN site API; supplies realized state, never a
price or an edge. NEVER fabricates -- a player not on the matchday roster -> None (clean
skip), never a guessed 0. frac_elapsed is the VALIDATED freshness lever (match minute / 90),
approximate by design. Pure except the injectable http_get; public fns NEVER raise.

RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_box_soccer.py -q
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional

from scripts.platformkit.bestbets.prop_settler_mlb import _norm

logger = logging.getLogger(__name__)

_SITE = "https://site.api.espn.com/apis/site/v2/sports"
# ESPN league paths for the in-game soccer reader (mirrors inplay_espn._INPLAY_LEAGUE_PATHS).
_LEAGUE_PATHS: Dict[str, List[str]] = {
    "soccer_intl": ["soccer/fifa.world"],
    "soccer": ["soccer/eng.1"],
}
_FRAC_CAP = 0.97  # never report a still-live match as fully elapsed
_TOTAL_MIN = 90.0
# keyEvent type texts that count as a GOAL for the scorer (own goals excluded -- they
# count against, never for, the player's goal prop).
_GOAL_TYPES = ("goal", "penalty - scored")
_CARD_TYPES = ("yellow card", "red card", "second yellow card", "yellow-red card")
# canonical stats this reader can honestly resolve (match the prop-board stat names).
_KNOWN = frozenset({"Goals", "Assists", "Goal+Assist", "Cards"})


def _default_http_get(url: str) -> Dict[str, Any]:
    """Keyless cached GET (reuses the odds-provider disk cache). {} on any failure."""
    try:
        from scripts.platformkit.odds_provider.http_cache import disk_cache_get
        out = disk_cache_get(url)
        return out if isinstance(out, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.debug("ingame_box_soccer http_get failed %s: %s", url, exc)
        return {}


def _http(http_get: Optional[Callable[[str], Dict[str, Any]]]):
    return http_get or _default_http_get


def _minutes_from_status(status: Dict[str, Any]) -> Optional[float]:
    """Elapsed match minutes from a competition status. None when unreadable."""
    if not isinstance(status, dict):
        return None
    disp = str(status.get("displayClock") or "")
    m = re.search(r"(\d+)", disp)
    if m:
        try:
            return float(m.group(1))
        except (TypeError, ValueError):
            pass
    clk = status.get("clock")
    try:
        return float(clk) / 60.0 if clk is not None and float(clk) > 90 else (
            float(clk) if clk is not None else None)
    except (TypeError, ValueError):
        return None


def live_games(sport: str = "soccer_intl",
               *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
               ) -> List[Dict[str, Any]]:
    """In-progress soccer matches for *sport* (status.type.state == 'in').

    Each entry: {game_pk (event id), home, away, frac_elapsed, state, league_path}.
    frac_elapsed = elapsed minutes / 90, capped. Returns [] on any failure."""
    get = _http(http_get)
    out: List[Dict[str, Any]] = []
    for path in _LEAGUE_PATHS.get(str(sport).lower(), []):
        board = get("%s/%s/scoreboard" % (_SITE, path)) or {}
        for ev in board.get("events", []) or []:
            comp = (ev.get("competitions") or [{}])[0]
            status = (comp.get("status") or {})
            if str((status.get("type") or {}).get("state", "")).lower() != "in":
                continue
            eid = str(ev.get("id") or "")
            if not eid:
                continue
            home = away = ""
            for c in comp.get("competitors", []) or []:
                nm = ((c.get("team") or {}).get("displayName")
                      or (c.get("team") or {}).get("name") or "")
                if c.get("homeAway") == "home":
                    home = nm
                elif c.get("homeAway") == "away":
                    away = nm
            mins = _minutes_from_status(status)
            frac = 0.0 if mins is None else min(_FRAC_CAP, max(0.0, mins / _TOTAL_MIN))
            out.append({"game_pk": eid, "home": home, "away": away,
                        "frac_elapsed": frac, "state": "in", "league_path": path})
    return out


def _seed_from_rosters(summary: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """{player_norm: {Goals,Assists,Cards: 0}} for every player who is on the pitch
    (started or subbed in). A bench player who never enters is omitted -> the trader
    skips their prop rather than re-pricing as if they were playing (honest)."""
    out: Dict[str, Dict[str, float]] = {}
    for team in summary.get("rosters", []) or []:
        for p in team.get("roster", []) or []:
            if not (p.get("starter") or p.get("subbedIn")):
                continue
            name = ((p.get("athlete") or {}).get("displayName") or "").strip()
            key = _norm(name)
            if key:
                out[key] = {"Goals": 0.0, "Assists": 0.0, "Cards": 0.0}
    return out


def boxscore_stat_map(game_pk: Any,
                      *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
                      sport: str = "soccer_intl"
                      ) -> Dict[str, Dict[str, float]]:
    """{player_norm: {Goals, Assists, Cards}} for a live match's running event tally.

    Players on the pitch are seeded to 0 then incremented from keyEvents (every goal /
    assist / card names its athlete). Empty dict on any failure -- never raises."""
    get = _http(http_get)
    summary: Dict[str, Any] = {}
    for path in _LEAGUE_PATHS.get(str(sport).lower(), []):
        summary = get("%s/%s/summary?event=%s" % (_SITE, path, game_pk)) or {}
        if summary.get("keyEvents") or summary.get("rosters"):
            break
    tally = _seed_from_rosters(summary)
    for e in summary.get("keyEvents", []) or []:
        ttype = str((e.get("type") or {}).get("text") or "").lower()
        parts = e.get("participants") or []
        scoring = bool(e.get("scoringPlay"))
        is_goal = (scoring or any(t in ttype for t in _GOAL_TYPES)) and "own goal" not in ttype
        is_card = any(t in ttype for t in _CARD_TYPES)
        if not (is_goal or is_card):
            continue
        names = [str(((p.get("athlete") or {}).get("displayName") or "")).strip()
                 for p in parts]
        if is_goal and names:
            tally.setdefault(_norm(names[0]),
                             {"Goals": 0.0, "Assists": 0.0, "Cards": 0.0})["Goals"] += 1.0
            if len(names) > 1 and names[1] and "penalty" not in ttype:
                tally.setdefault(_norm(names[1]), {"Goals": 0.0, "Assists": 0.0,
                                                   "Cards": 0.0})["Assists"] += 1.0
        elif is_card and names:
            tally.setdefault(_norm(names[0]),
                             {"Goals": 0.0, "Assists": 0.0, "Cards": 0.0})["Cards"] += 1.0
    return tally


def realized_for(stat: str, stat_map: Dict[str, Dict[str, float]],
                 player: str) -> Optional[float]:
    """The player's running value of *stat*, or None (NOT 0) when the player is not on
    the pitch / the stat is not event-derivable -- so the trader never re-prices on a
    fabricated zero for someone whose realized state we cannot honestly read."""
    if not is_known_stat(stat):
        return None
    key = _norm(player)
    if not key or not stat_map:
        return None
    entry = stat_map.get(key)
    if entry is None:  # loose contains-match (handles abbreviations / accents)
        for k, v in stat_map.items():
            if key in k or k in key:
                entry = v
                break
    if entry is None:
        return None
    if stat == "Goal+Assist":
        return float(entry.get("Goals", 0.0)) + float(entry.get("Assists", 0.0))
    return float(entry.get(stat, 0.0))


def is_known_stat(stat: str) -> bool:
    """True only for the event-derivable families (Goals / Assists / Goal+Assist / Cards);
    Shots / SOT / Saves / Fouls are not per-player readable keyless -> False (skip)."""
    return str(stat or "").strip() in _KNOWN


__all__ = ["live_games", "boxscore_stat_map", "realized_for", "is_known_stat"]
