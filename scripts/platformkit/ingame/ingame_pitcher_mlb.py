"""scripts.platformkit.ingame.ingame_pitcher_mlb -- DEEP pitcher/batter in-game state (MLB).

The base-out extractor (ingame_baseout_mlb) gives the runners + count; this adds the OTHER
classic high-signal in-game variables a score+inning summary discards: WHO is pitching /
batting, the pitcher's PITCH COUNT (fatigue proxy), and the TIMES-THROUGH-THE-ORDER the
current batter is facing (the well-documented "third time through the order" penalty).

These are PURE adapters over already-fetched statsapi payloads (the resolver fetches the
linescore + boxscore once per game per tick and hands them here), so this module does NO
network and never duplicates the resolver's id work:

  * linescore.defense.pitcher / linescore.offense.batter -> current pitcher / batter.
  * boxscore pitching line for the current pitcher -> numberOfPitches (pitch_count) +
    battersFaced -> tto = battersFaced // 9 + 1 (the order-turn the batter NOW up is in).

Leak-free / honest: reads only the CURRENT live state (no future info); returns {} when the
inputs are absent (pregame / between-pitch gaps); never raises; ASCII; no src/kernel imports.
Descriptive state for the in-game model to later be GATED on -- NOT an edge claim.

INVARIANTS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_pitcher_mlb.py -q
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def tto_for(batters_faced: Any) -> Optional[int]:
    """Times-through-order the batter CURRENTLY up is in, from the pitcher's batters-faced.

    battersFaced is the count the pitcher has ALREADY retired/faced; the batter now up is the
    (battersFaced+1)-th, i.e. order-turn = battersFaced // 9 + 1 (1 = first time through, 3 =
    the third-time-through-order zone).  None when the count is unreadable/negative (honest).

    APPROXIMATION caveat: battersFaced (boxscore) and the displayed batter (linescore
    offense.batter) come from two SEPARATELY-fetched statsapi payloads, so across a
    plate-appearance boundary the tto attached to the shown batter can be off by +/-1. tto is
    a DESCRIPTIVE segment label only -- never an exact input to any probability/units/CLV
    math -- so this is immaterial; no consumer should treat it as exact."""
    try:
        bf = int(batters_faced)
    except (TypeError, ValueError):
        return None
    if bf < 0:
        return None
    return bf // 9 + 1


def _person(block: Any, key: str) -> Tuple[Optional[str], Optional[Any]]:
    """(fullName, id) for a person under *block[key]* (a statsapi person ref), or (None,None)."""
    p = (block or {}).get(key) if isinstance(block, dict) else None
    if not isinstance(p, dict):
        return None, None
    return p.get("fullName"), p.get("id")


def _pitching_line(boxscore: Dict[str, Any], pid: Any) -> Dict[str, Any]:
    """The pitching stat line for player *pid* from a statsapi boxscore, or {} (not found).

    statsapi keys boxscore players as 'ID<personId>' under teams.home/away.players; the
    pitching stats live at players['ID<pid>'].stats.pitching.  Searches both sides."""
    if pid is None:
        return {}
    key = "ID%s" % pid
    for side in ("home", "away"):
        players = ((boxscore.get("teams", {}) or {}).get(side, {}) or {}).get("players", {}) or {}
        entry = players.get(key)
        if isinstance(entry, dict):
            return (entry.get("stats", {}) or {}).get("pitching", {}) or {}
    return {}


def pitcher_batter_fields(linescore: Dict[str, Any],
                          boxscore: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ADDITIVE deep pitcher/batter fields from an already-fetched linescore (+ boxscore).

    Returns any of {pitcher, batter, pitch_count, batters_faced, tto} that are readable; {}
    when the linescore is absent.  pitch_count/tto need the boxscore (the linescore alone
    names the pitcher/batter but not the count) -- absent boxscore -> names only, never a
    fabricated count.  Never raises."""
    if not isinstance(linescore, dict) or not linescore:
        return {}
    out: Dict[str, Any] = {}
    bname, _bid = _person(linescore.get("offense"), "batter")
    pname, pid = _person(linescore.get("defense"), "pitcher")
    if pname:
        out["pitcher"] = pname
    if bname:
        out["batter"] = bname
    line = _pitching_line(boxscore if isinstance(boxscore, dict) else {}, pid)
    pc = line.get("numberOfPitches")
    if pc is None:
        pc = line.get("pitchesThrown")
    try:
        out["pitch_count"] = int(pc)
    except (TypeError, ValueError):
        pass
    tto = tto_for(line.get("battersFaced"))
    if tto is not None:
        out["tto"] = tto
        try:
            out["batters_faced"] = int(line.get("battersFaced"))
        except (TypeError, ValueError):
            pass
    return out


__all__ = ["tto_for", "pitcher_batter_fields"]
