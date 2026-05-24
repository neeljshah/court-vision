"""src/data/lineups.py — shared loader for projected starting lineups (cycle 62).

Cycle 61's fetch_lineups.py writes data/lineups_<date>.json with the schema
documented there. This module flattens that game-by-game structure into
per-player lookups that compare_to_lines, predict_player, predict_slate,
and any future consumer can use without re-parsing the JSON.

Mirrors the cycle-53 src/data/injuries.py pattern: single source of truth,
diacritic-insensitive lookup, tolerant of missing/malformed files.

Status taxonomy (from rotowire, matches what fetch_lineups writes):
  Confirmed → confidence high (lineup released, ~30min pre-tip)
  Expected  → confidence medium-high (writer's best guess)
  Projected → confidence medium (more speculative)
  Unknown   → no status header — treat like Projected
"""
from __future__ import annotations

import json
import os
import unicodedata
from datetime import date as _date
from typing import Dict, List, Optional


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _name_key(name: str) -> str:
    return _strip_accents(name or "").lower().strip()


def default_path(d: Optional[_date] = None) -> str:
    if d is None:
        d = _date.today()
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_dir, "data", f"lineups_{d.isoformat()}.json")


def load_lineups(path: Optional[str] = None) -> dict:
    """Read a lineups JSON; return full payload or {} on missing/malformed."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def build_starter_index(path: Optional[str] = None) -> Dict[str, dict]:
    """Return {canonical_name_key: {team, pos, play_pct, injury, lineup_status}}
    for every starter in the lineup JSON. Skips empty / unparseable files.
    """
    payload = load_lineups(path)
    out: Dict[str, dict] = {}
    for g in payload.get("games", []) or []:
        for side in ("away", "home"):
            lu = g.get(f"{side}_lineup", {}) or {}
            team = g.get(f"{side}_team", "")
            status = lu.get("status", "Unknown")
            for s in lu.get("starters", []) or []:
                key = _name_key(s.get("name", ""))
                if not key:
                    continue
                out[key] = {
                    "team":           team,
                    "pos":            s.get("pos", ""),
                    "play_pct":       int(s.get("play_pct", 0) or 0),
                    "injury":         s.get("injury"),
                    "lineup_status":  status,
                }
    return out


def lookup_starter(name: str, index: Dict[str, dict]) -> Optional[dict]:
    """Return the starter record for `name`, or None if not in tonight's lineups.

    'Not in tonight's lineups' means EITHER (a) the player's team isn't
    playing tonight, OR (b) the player isn't projected to start. The
    distinction needs a separate schedule check — use teams_playing() below.
    """
    return index.get(_name_key(name))


def teams_playing(path: Optional[str] = None) -> List[str]:
    """Return the list of team abbrevs playing on the lineups JSON's date."""
    payload = load_lineups(path)
    teams: List[str] = []
    for g in payload.get("games", []) or []:
        for side in ("away", "home"):
            t = g.get(f"{side}_team", "")
            if t and t not in teams:
                teams.append(t)
    return teams


def classify_starter(name: str, index: Dict[str, dict],
                      teams_tonight: Optional[List[str]] = None,
                      player_team: Optional[str] = None) -> str:
    """Coarse one-word classification useful for CLI decisions.

    Returns one of:
      "starter"        - in lineup, play_pct >= 80, no questionable tag
      "questionable"   - in lineup, play_pct < 80 OR injury == "Ques"/"GTD"
      "bench"          - team is playing tonight but player not in starting 5
      "no-game"        - team is not playing tonight (or teams_tonight unknown)
      "unknown"        - lineup data unavailable
    """
    rec = lookup_starter(name, index)
    if rec is not None:
        inj = (rec.get("injury") or "").lower()
        if rec["play_pct"] >= 80 and inj not in ("ques", "gtd", "questionable"):
            return "starter"
        return "questionable"
    # Player not in any starting lineup.
    if not index:
        return "unknown"
    if teams_tonight is None and player_team is None:
        return "bench"     # lineup data exists; player just not starting
    if player_team and teams_tonight and player_team in teams_tonight:
        return "bench"
    return "no-game"
