"""scripts.platformkit.ingame.ingame_box_mlb -- LIVE MLB realized-stat + freshness reader.

The in-game prop re-pricer (ingame_prop_repricer.reprice_prop) needs two LIVE inputs per
player it does not have on its own: realized_so_far (the player's running tally for the
stat) and frac_elapsed (how much of the game is gone). The post-game settler
(prop_settler_mlb) already knows how to read a player's canonical stat from the keyless
MLB Stats API boxscore, but it only matches FINAL games. This module is the LIVE twin:

  * live_games()           -> the in-progress MLB games today (gamePk + teams + frac_elapsed)
  * boxscore_stat_map(pk)  -> {normalized_player: (batting, pitching)} for a live game
  * realized_for(stat, m, player) -> the player's running value of *stat*, or None

It REUSES prop_settler_mlb's parsing (the canonical-stat map, name-norm, stat extractor)
verbatim so the live reprice and the post-game settle read the SAME numbers -- no parallel
stat logic that could drift (see memory: tests-mirror-real-not-parallel).

HONEST RAILS (binding):
  * Reads PUBLIC keyless statsapi only. UNITS / probability work happens downstream; this
    module supplies realized state, never a price or an edge.
  * NEVER fabricates: a missing game / player / stat / field -> None (clean skip), never 0.
  * frac_elapsed is the VALIDATED freshness lever, approximate by design (inning fraction):
    early innings -> ~pregame, late -> ~realized. It is calibration, not a $ edge.
  * Pure except the injectable http_get; public fns NEVER raise.

RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_box_mlb.py -q
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from scripts.platformkit.bestbets.prop_settler_mlb import (
    _BATTING, _PITCHING, _http_get_json, _norm, _stat_value,
)

logger = logging.getLogger(__name__)

_SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
_BOXSCORE = "https://statsapi.mlb.com/api/v1/game/%s/boxscore"
_LINESCORE = "https://statsapi.mlb.com/api/v1/game/%s/linescore"

# detailedState / abstractGameState values that mean "ball is live right now".
_LIVE_STATES = ("in progress", "live", "manager challenge", "warmup")
# A regulation game is 9 innings; an inning has a top + bottom half. We map progress to
# [0, 1) by completed half-innings / 18 (extra innings asymptote toward but never reach 1
# until the game is Final, which the caller detects via state and skips with the settler).
_REGULATION_HALVES = 18.0
_FRAC_CAP = 0.97  # never report "fully elapsed" for a still-live game


def _http(http_get: Optional[Callable[[str], Dict[str, Any]]]):
    return http_get or _http_get_json


def _is_live_state(status: Dict[str, Any]) -> bool:
    abstract = str((status or {}).get("abstractGameState", "")).lower()
    detailed = str((status or {}).get("detailedState", "")).lower()
    if abstract == "live":
        return True
    return any(s in detailed for s in _LIVE_STATES)


def _frac_from_linescore(ls: Dict[str, Any]) -> Optional[float]:
    """completed half-innings / 18, capped. None when the linescore is unusable."""
    if not ls:
        return None
    try:
        cur = int(ls.get("currentInning") or 0)
    except (TypeError, ValueError):
        return None
    if cur <= 0:
        return 0.0
    state = str(ls.get("inningState") or ls.get("inningHalf") or "").lower()
    is_top = bool(ls.get("isTopInning", state.startswith("top")))
    # half-innings fully COMPLETED before the current half:
    #   top of inning N -> (N-1) full innings done = 2*(N-1) halves
    #   bottom of N     -> 2*(N-1) + 1 halves done
    completed_halves = 2 * (cur - 1) + (0 if is_top else 1)
    frac = completed_halves / _REGULATION_HALVES
    if frac < 0.0:
        frac = 0.0
    return min(_FRAC_CAP, frac)


def live_games(*, http_get: Optional[Callable[[str], Dict[str, Any]]] = None,
               game_date: str = "") -> List[Dict[str, Any]]:
    """The MLB games that are LIVE right now (today, or *game_date* YYYY-MM-DD).

    Each entry: {game_pk, home, away, frac_elapsed, state}. frac_elapsed is read from the
    per-game linescore. Returns [] on any failure -- never raises."""
    get = _http(http_get)
    url = _SCHEDULE + ("&date=%s" % game_date if game_date else "")
    data = get(url) or {}
    out: List[Dict[str, Any]] = []
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            status = g.get("status", {}) or {}
            if not _is_live_state(status):
                continue
            gp = g.get("gamePk")
            if gp is None:
                continue
            teams = g.get("teams", {}) or {}
            home = ((teams.get("home", {}) or {}).get("team", {}) or {}).get("name")
            away = ((teams.get("away", {}) or {}).get("team", {}) or {}).get("name")
            frac = _frac_from_linescore(get(_LINESCORE % gp))
            if frac is None:
                frac = 0.0
            out.append({
                "game_pk": str(gp), "home": home, "away": away,
                "frac_elapsed": frac,
                "state": str(status.get("detailedState", "")),
            })
    return out


def boxscore_stat_map(game_pk: Any,
                      *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
                      ) -> Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]]:
    """{normalized_player_name: (batting, pitching)} for a live game's running boxscore.

    Built ONCE per game per tick so the trader can look up many props without re-fetching.
    Empty dict on any failure -- never raises."""
    get = _http(http_get)
    box = get(_BOXSCORE % game_pk) or {}
    out: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]] = {}
    for side in ("home", "away"):
        players = ((box.get("teams", {}) or {}).get(side, {}) or {}).get("players", {}) or {}
        for _pid, pdat in players.items():
            full = (pdat.get("person", {}) or {}).get("fullName", "")
            key = _norm(full)
            if not key:
                continue
            stats = pdat.get("stats", {}) or {}
            out[key] = (stats.get("batting", {}) or {}, stats.get("pitching", {}) or {})
    return out


def realized_for(stat: str, stat_map: Dict[str, Tuple[Dict[str, Any], Dict[str, Any]]],
                 player: str) -> Optional[float]:
    """The player's running value of canonical *stat* from a boxscore_stat_map, or None.

    None (NOT 0) when the player is absent (has not yet entered) or the stat is unknown --
    so the caller never re-prices on a fabricated zero for a player who simply has no row."""
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
    batting, pitching = entry
    return _stat_value(stat, batting, pitching)


def is_known_stat(stat: str) -> bool:
    """True when *stat* maps to a boxscore field this reader can read (else skip the prop)."""
    s = str(stat or "").strip()
    return s == "Hits+Runs+RBIs" or s in _BATTING or s in _PITCHING


__all__ = ["live_games", "boxscore_stat_map", "realized_for", "is_known_stat"]
