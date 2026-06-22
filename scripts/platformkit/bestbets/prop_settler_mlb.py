"""scripts.platformkit.bestbets.prop_settler_mlb -- resolve the REAL post-game stat for an
MLB player-prop row from the keyless MLB Stats API boxscore. Best-effort: ANY failure
(no final game / player not found / network / unknown stat) returns None so the prop stays
PENDING and is NEVER fabricated.

Flow: matchup teams + game_date -> schedule gamePk (FINAL only) -> boxscore -> match the
prop_player by normalized name -> read the canonical prop_stat from batting/pitching.

INJECTABLE: http_get(url)->dict is overridable so the resolver is offline-testable; the
default fetches statsapi via urllib (keyless), returning {} on any error.

RAILS: build only under scripts/platformkit/; ASCII; <=300 LOC; never raises.
Per-file test: scripts/platformkit/bestbets/test_prop_settler_mlb.py
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_SCHEDULE = "https://statsapi.mlb.com/api/v1/schedule?sportId=1"
_BOXSCORE = "https://statsapi.mlb.com/api/v1/game/%s/boxscore"
_FINAL_STATES = ("final", "completed", "game over")


def _http_get_json(url: str) -> Dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=10.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.debug("prop_settler_mlb: GET %s failed: %s", url, exc)
        return {}


def _norm(name: Any) -> str:
    """Case/space/punct-insensitive name key ('J.T. Realmuto' -> 'jtrealmuto')."""
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _matchup_teams(matchup: Any) -> Optional[tuple]:
    s = str(matchup or "").strip()
    for sep in (" @ ", " vs ", " vs. ", " v ", "@"):
        if sep in s:
            a, b = (p.strip() for p in s.split(sep, 1))
            if a and b:
                return a, b
    return None


# Canonical prop_stat (domains/mlb MLB_CANON values) -> boxscore extractor.
def _hrr(b: Dict[str, Any]) -> float:
    return float(b.get("hits", 0)) + float(b.get("runs", 0)) + float(b.get("rbi", 0))


_BATTING = {
    "Hits": "hits", "Total Bases": "totalBases", "RBIs": "rbi", "Runs": "runs",
    "Home Runs": "homeRuns", "Walks": "baseOnBalls", "Batter Strikeouts": "strikeOuts",
    "Stolen Bases": "stolenBases",
}
_PITCHING = {
    "Pitcher Strikeouts": "strikeOuts", "Outs": "outs", "Walks Allowed": "baseOnBalls",
}


def _stat_value(stat: str, batting: Dict[str, Any], pitching: Dict[str, Any]) -> Optional[float]:
    """Read the canonical *stat* from a player's batting/pitching stat dicts, or None."""
    s = str(stat or "").strip()
    if s == "Hits+Runs+RBIs":
        return _hrr(batting) if batting else None
    if s in _BATTING and batting:
        try:
            return float(batting.get(_BATTING[s], 0))
        except (TypeError, ValueError):
            return None
    if s in _PITCHING and pitching:
        try:
            return float(pitching.get(_PITCHING[s], 0))
        except (TypeError, ValueError):
            return None
    return None


def _find_final_gamepk(teams: tuple, game_date: str,
                       http_get: Callable[[str], Dict[str, Any]]) -> Optional[str]:
    """The FINAL game's gamePk whose two teams match *teams*; None if absent/not final."""
    url = _SCHEDULE + ("&date=%s" % game_date if game_date else "")
    data = http_get(url)
    want = {_norm(teams[0]), _norm(teams[1])}
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            state = str((g.get("status", {}) or {}).get("abstractGameState", "")).lower()
            detailed = str((g.get("status", {}) or {}).get("detailedState", "")).lower()
            if state not in ("final",) and detailed not in _FINAL_STATES:
                continue
            t = g.get("teams", {}) or {}
            hn = _norm((t.get("home", {}) or {}).get("team", {}).get("name"))
            an = _norm((t.get("away", {}) or {}).get("team", {}).get("name"))
            # token-subset match: prop matchup may use abbr / short names
            if _team_hit(want, hn, an):
                gp = g.get("gamePk")
                if gp is not None:
                    return str(gp)
    return None


def _team_hit(want: set, home_norm: str, away_norm: str) -> bool:
    """True when both prop-matchup team tokens map onto the game's two teams."""
    def _one(label: str) -> bool:
        return any(label and (label in gn or gn in label) for gn in (home_norm, away_norm))
    return all(_one(w) for w in want if w)


def _player_stats(box: Dict[str, Any], player: str) -> Optional[tuple]:
    """(batting, pitching) stat dicts for the named player in a boxscore, or None."""
    pkey = _norm(player)
    if not pkey:
        return None
    for side in ("home", "away"):
        players = ((box.get("teams", {}) or {}).get(side, {}) or {}).get("players", {}) or {}
        for _pid, pdat in players.items():
            full = (pdat.get("person", {}) or {}).get("fullName", "")
            nm = _norm(full)
            if nm and (nm == pkey or pkey in nm or nm in pkey):
                stats = pdat.get("stats", {}) or {}
                return (stats.get("batting", {}) or {}, stats.get("pitching", {}) or {})
    return None


def mlb_realized_stat(row: Dict[str, Any],
                      *, http_get: Optional[Callable[[str], Dict[str, Any]]] = None
                      ) -> Optional[float]:
    """Realized value of an MLB prop row's stat, or None (game not final / unresolved).

    Never raises. Reads row: matchup, game_date, prop_player, prop_stat. None on ANY gap so
    the prop stays PENDING -- never a fabricated outcome.
    """
    get = http_get or _http_get_json
    teams = _matchup_teams(row.get("matchup"))
    player = str(row.get("prop_player") or "")
    stat = str(row.get("prop_stat") or "")
    if not teams or not player or not stat:
        return None
    game_date = str(row.get("game_date") or "")[:10]
    gamepk = _find_final_gamepk(teams, game_date, get)
    if not gamepk:
        return None
    box = get(_BOXSCORE % gamepk)
    if not box:
        return None
    ps = _player_stats(box, player)
    if ps is None:
        return None  # player not in boxscore -> DNP / wrong game -> pending (not 0!)
    batting, pitching = ps
    return _stat_value(stat, batting, pitching)


__all__ = ["mlb_realized_stat"]
