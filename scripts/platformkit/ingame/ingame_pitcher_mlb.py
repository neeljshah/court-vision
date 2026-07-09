"""scripts.platformkit.ingame.ingame_pitcher_mlb -- DEEP pitcher/batter in-game state (MLB).

The base-out extractor (ingame_baseout_mlb) gives the runners + count; this adds the OTHER
classic high-signal in-game variables a score+inning summary discards: WHO is pitching /
batting (by id, so a future replay can condition on player identity, not just names), the
pitcher's PITCH COUNT (fatigue proxy), the TIMES-THROUGH-THE-ORDER the current batter is
facing (the well-documented "third time through the order" penalty), who is ON DECK, and
which pitchers the defending team has ALREADY USED this game (bullpen exposure).

These are PURE adapters over already-fetched statsapi payloads (the resolver fetches the
linescore + boxscore once per game per tick and hands them here), so this module does NO
network and never duplicates the resolver's id work:

  * linescore.defense.pitcher / linescore.offense.batter / linescore.offense.onDeck ->
    current pitcher / batter / on-deck batter (name + id -- the SAME person dict, id was
    already parsed for the pitching-line lookup and previously discarded).
  * boxscore pitching line for the current pitcher -> numberOfPitches (pitch_count) +
    battersFaced -> tto = battersFaced // 9 + 1 (the order-turn the batter NOW up is in).
  * boxscore.teams.<defending side>.pitchers -> every pitcher id that side has used so far
    this game (the SAME boxscore payload already fetched for pitch_count -- no extra GET).

Leak-free / honest: reads only the CURRENT live state (no future info); returns {} when the
inputs are absent (pregame / between-pitch gaps); never raises; ASCII; no src/kernel imports.
Descriptive state for the in-game model to later be GATED on -- NOT an edge claim.

INVARIANTS: build only under scripts/platformkit/; ASCII; <=300 LOC; no edge claims.
Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      scripts/platformkit/ingame/test_ingame_pitcher_mlb.py -q
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


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


def _find_side(boxscore: Dict[str, Any], pid: Any) -> Optional[str]:
    """Which side ('home'/'away') has player *pid* on its roster, or None (not found /
    pid absent). Used both to locate the pitching line and to know which side's
    already-used-pitchers list is the DEFENDING team's (the side the current pitcher is
    ON)."""
    if pid is None:
        return None
    key = "ID%s" % pid
    for side in ("home", "away"):
        players = ((boxscore.get("teams", {}) or {}).get(side, {}) or {}).get("players", {}) or {}
        if key in players:
            return side
    return None


def _pitching_line(boxscore: Dict[str, Any], pid: Any, side: Optional[str]) -> Dict[str, Any]:
    """The pitching stat line for player *pid* on *side*, or {} (not found).

    statsapi keys boxscore players as 'ID<personId>' under teams.home/away.players; the
    pitching stats live at players['ID<pid>'].stats.pitching."""
    if side is None:
        return {}
    players = ((boxscore.get("teams", {}) or {}).get(side, {}) or {}).get("players", {}) or {}
    entry = players.get("ID%s" % pid)
    return (entry.get("stats", {}) or {}).get("pitching", {}) or {} if isinstance(entry, dict) else {}


def _bullpen_used(boxscore: Dict[str, Any], side: Optional[str]) -> Optional[List[int]]:
    """Every pitcher id *side* has used so far this game (statsapi boxscore.teams.<side>.
    pitchers -- the SAME boxscore payload already fetched for pitch_count, no extra GET).
    None when *side* is unresolved or the list is absent/unreadable -- never fabricated."""
    if side is None:
        return None
    pitchers = ((boxscore.get("teams", {}) or {}).get(side, {}) or {}).get("pitchers")
    if not isinstance(pitchers, list):
        return None
    try:
        return [int(p) for p in pitchers]
    except (TypeError, ValueError):
        return None


def pitcher_batter_fields(linescore: Dict[str, Any],
                          boxscore: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """ADDITIVE deep pitcher/batter fields from an already-fetched linescore (+ boxscore).

    Returns any of {pitcher, batter, pitcher_id, batter_id, ondeck_id, pitch_count,
    batters_faced, tto, bullpen_used} that are readable; {} when the linescore is absent.
    pitch_count/tto/bullpen_used need the boxscore (the linescore alone names the pitcher/
    batter but not the count) -- absent boxscore -> names/ids only, never a fabricated
    count. Never raises."""
    if not isinstance(linescore, dict) or not linescore:
        return {}
    out: Dict[str, Any] = {}
    bname, bid = _person(linescore.get("offense"), "batter")
    pname, pid = _person(linescore.get("defense"), "pitcher")
    _odname, odid = _person(linescore.get("offense"), "onDeck")
    if pname:
        out["pitcher"] = pname
    if bname:
        out["batter"] = bname
    if pid is not None:
        out["pitcher_id"] = pid
    if bid is not None:
        out["batter_id"] = bid
    if odid is not None:
        out["ondeck_id"] = odid
    box = boxscore if isinstance(boxscore, dict) else {}
    side = _find_side(box, pid)
    line = _pitching_line(box, pid, side)
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
    bullpen = _bullpen_used(box, side)
    if bullpen is not None:
        out["bullpen_used"] = bullpen
    return out


__all__ = ["tto_for", "pitcher_batter_fields"]
