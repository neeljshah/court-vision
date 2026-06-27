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

import datetime as _dt
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


def _next_day(game_date: str) -> Optional[str]:
    """YYYY-MM-DD -> the next calendar day (same format), or None if unparseable."""
    try:
        d = _dt.datetime.strptime(str(game_date)[:10], "%Y-%m-%d").date()
        return (d + _dt.timedelta(days=1)).isoformat()
    except Exception:  # noqa: BLE001
        return None


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
    for d in data.get("dates", []) or []:
        for g in d.get("games", []) or []:
            state = str((g.get("status", {}) or {}).get("abstractGameState", "")).lower()
            detailed = str((g.get("status", {}) or {}).get("detailedState", "")).lower()
            if state not in ("final",) and detailed not in _FINAL_STATES:
                continue
            t = g.get("teams", {}) or {}
            hn = (t.get("home", {}) or {}).get("team", {}).get("name")
            an = (t.get("away", {}) or {}).get("team", {}).get("name")
            # nickname-word match: prop matchup may use a city ABBREVIATION
            if _team_hit(teams, hn, an):
                gp = g.get("gamePk")
                if gp is not None:
                    return str(gp)
    return None


def _name_words(label: Any) -> set:
    """Distinctive nickname word-set for a team label. Drops a leading city
    ABBREVIATION (an all-caps alpha token like 'MIL'/'BOS'/'NY'/'CHC') so an
    abbreviated prop matchup ('MIL Brewers') still maps onto the schedule's full
    name ('Milwaukee Brewers'); full-name labels keep every word."""
    toks = str(label or "").split()
    if len(toks) >= 2 and toks[0].isalpha() and toks[0].isupper():
        toks = toks[1:]
    return {_norm(t) for t in toks if _norm(t)}


def _team_hit(teams: tuple, home_name: Any, away_name: Any) -> bool:
    """True when the two prop-matchup teams map onto the game's two teams (in
    either home/away orientation). A prop side matches a schedule team when ALL
    its nickname words are present in that team -- robust to city abbreviations
    and unambiguous for shared-suffix nicknames (Red Sox vs White Sox)."""
    a, b = _name_words(teams[0]), _name_words(teams[1])
    h, w = _name_words(home_name), _name_words(away_name)

    def hit(side: set, team: set) -> bool:
        return bool(side) and side <= team

    return (hit(a, w) and hit(b, h)) or (hit(a, h) and hit(b, w))


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
        # A bet placed late on the placement ET-day can carry game_date = day-before
        # the ACTUAL (next-day) game. If the exact date has NO final for these teams,
        # try date+1 ONLY. _find_final_gamepk's FINAL-only guard means an in-progress
        # next-day game still returns None (stays pending), so this never mis-settles a
        # live game -- it only resolves the one-day mis-tag once that game is final.
        nxt = _next_day(game_date)
        gamepk = _find_final_gamepk(teams, nxt, get) if nxt else None
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
