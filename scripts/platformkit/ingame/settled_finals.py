"""scripts.platformkit.ingame.settled_finals -- keyless ESPN settled-finals provider
for the LIVING in-game refresh loop. Turns the loop from a NO-OP into a real feed.

The refresh svc imported scripts.platformkit.ingame.settled_finals, which DID NOT
EXIST, so the loop returned [] forever. This module supplies it:

  settled_since(sport, seen_ids) -> the newly-FINAL in-season games for `sport` whose
      game_id is NOT in seen_ids, ascending by key. DEDUP-BY-game_id is the PRIMARY
      guard (NOT a high-water key over scheduled commence time -- a game that finals OUT
      OF ORDER, earlier commence + later final, would have key < high-water and be
      WRONGLY SKIPPED). Each returned game carries its own sortable key for display /
      ordering, but folding is decided by id membership so no unseen game is ever lost.

  states_for_game(sport, game) -> that game's frozen-schema in-game state rows
      {sport,game_id,asof_idx,state_diff,frac_elapsed,p0,outcome}, via the sport's own
      ingest adapter when present; else [] (the game is skipped, NEVER fabricated).

Keyless: reuses the public ESPN scoreboard (odds_provider.http_cache.http_get_json +
disk_cache_get). All network is injectable (http_get) so offline tests drive canned
boards with ZERO network. A dead/odd feed degrades to [] -- never raises, never a fake.

INVARIANTS: never edit src/ or kernel/; <=300 LOC; ASCII-only; stdlib + repo-internal.
No $ anywhere -- this only supplies inputs to a CALIBRATION gate.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger("settled_finals")

_SITE = "https://site.api.espn.com/apis/site/v2/sports"
_LEAGUE_PATH: Dict[str, str] = {
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
    "soccer": "soccer/eng.1",
    "soccer_intl": "soccer/fifa.world",
    "tennis": "tennis/atp",
}

# A game is "settled" only when ESPN reports its status as completed/final.
_FINAL_STATES = frozenset({"STATUS_FINAL", "STATUS_FULL_TIME",
                           "STATUS_FINAL_PEN", "STATUS_FINAL_OVERTIME"})


def game_key(game: Dict[str, Any]) -> str:
    """Sortable DISPLAY/order key for a settled game: '<commence_iso>|<event_id>'.

    Used only to ORDER returned games (ISO dates sort lexicographically, id breaks
    same-date ties). It is NOT a skip filter: folding is decided by game_id dedup, so a
    low-commence late-final game is never dropped by this key.
    """
    return "%s|%s" % (str(game.get("commence") or ""), str(game.get("game_id") or ""))


def _status_state(ev: Dict[str, Any]) -> str:
    comp = (ev.get("competitions") or [{}])[0]
    st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
    return str(st.get("name") or st.get("state") or "").upper()


def _is_final(ev: Dict[str, Any]) -> bool:
    comp = (ev.get("competitions") or [{}])[0]
    st = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
    if bool(st.get("completed")):
        return True
    return _status_state(ev) in _FINAL_STATES


def _team(comp: Dict[str, Any], side: str) -> str:
    for c in comp.get("competitors", []) or []:
        if c.get("homeAway") == side:
            t = c.get("team") or {}
            return str(t.get("displayName") or t.get("name")
                       or t.get("abbreviation") or "").strip()
    return ""


def _final_games_from_board(board: Any, sport: str) -> List[Dict[str, Any]]:
    """Parse a scoreboard payload into settled-final game dicts (ascending by key)."""
    if not isinstance(board, dict):
        return []
    events = board.get("events")
    if not isinstance(events, list):
        return []
    out: List[Dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict) or not _is_final(ev):
            continue
        eid = str(ev.get("id") or "")
        if not eid:
            continue
        comp = (ev.get("competitions") or [{}])[0]
        g = {
            "sport": sport, "game_id": eid,
            "commence": str(ev.get("date") or ""),
            "home": _team(comp, "home"), "away": _team(comp, "away"),
        }
        g["key"] = game_key(g)
        out.append(g)
    out.sort(key=lambda g: g["key"])
    return out


def settled_since(sport: str, *, since: Optional[str] = None,
                  seen_ids: Optional[Sequence[str]] = None,
                  http_get: Optional[Callable[[str], Any]] = None,
                  dates: Optional[Sequence[str]] = None,
                  use_cache: bool = True) -> List[Dict[str, Any]]:
    """Newly-FINAL in-season games for `sport` NOT YET FOLDED (ascending by key).

    DEDUP is keyed on game_id (the PRIMARY guard), NOT on the high-water key. A prior
    version filtered `key > since` where the key = SCHEDULED commence time; a game that
    finals OUT OF ORDER (earlier commence, later final -- e.g. extra innings while a
    later-scheduled game already advanced the cursor) then had key < high-water and was
    SILENTLY DROPPED, never folded. So we now return every FINAL game whose game_id is
    not in `seen_ids`, regardless of commence ordering -- a low-commence late-final game
    IS surfaced. `since` survives only as an optional FETCH-WINDOW hint for `dates`
    callers; it is NEVER used to drop a game. NEVER raises.
    """
    path = _LEAGUE_PATH.get(str(sport).lower())
    if not path:
        return []
    get = http_get or _default_http_get
    urls = ([f"{_SITE}/{path}/scoreboard?dates={d}" for d in dates]
            if dates else [f"{_SITE}/{path}/scoreboard"])
    games: Dict[str, Dict[str, Any]] = {}
    for url in urls:
        try:
            board = _cached(url, get) if use_cache else get(url)
        except Exception as exc:  # noqa: BLE001 -- dead feed: skip this url, never raise
            logger.debug("settled_since(%s) board fetch failed: %s", sport, exc)
            continue
        for g in _final_games_from_board(board, str(sport).lower()):
            games[g["game_id"]] = g  # dedup within the window by id
    seen = set(str(s) for s in (seen_ids or ()))
    fresh = [g for g in games.values() if str(g["game_id"]) not in seen]
    fresh.sort(key=lambda g: g["key"])
    return fresh


def _cached(url: str, get: Callable[[str], Any]) -> Any:
    try:
        from scripts.platformkit.odds_provider.http_cache import disk_cache_get
        return disk_cache_get(url, http_get=get)
    except Exception:  # noqa: BLE001 -- cache layer optional; fall back to direct get
        return get(url)


def _default_http_get(url: str) -> Any:
    from scripts.platformkit.odds_provider.http_cache import http_get_json
    return http_get_json(url)


# ----------------------------------------------------------------- per-game states
def states_for_game(sport: str, game: Dict[str, Any],
                    **_kw) -> List[Dict[str, Any]]:
    """Frozen-schema in-game state rows for one settled game.

    Delegates to the sport's own ingest adapter when one is wired
    (scripts.platformkit.ingame.settled_ingest.states_for_game); absent -> [] so the
    game is SKIPPED, never fabricated. NEVER raises.
    """
    try:
        from scripts.platformkit.ingame import settled_ingest as _ing  # type: ignore
    except Exception:  # noqa: BLE001 -- no real ingest adapter present yet
        return []
    try:
        rows = list(_ing.states_for_game(sport, game))  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.debug("states_for_game(%s) unavailable: %s", sport, exc)
        return []
    return rows


__all__ = ["settled_since", "states_for_game", "game_key"]
