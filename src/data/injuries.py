"""src/data/injuries.py — shared loader for NBA injury report JSON (cycle 53).

The cycle-43 scraper writes `data/injuries_<date>.json` with the schema:
    {
        "date": "...",
        "source_pdf": "...",
        "fetched_at": "...",
        "players": [
            {"team": "LAL", "name": "LeBron James", "status": "OUT", "reason": "..."},
            ...
        ]
    }

Three scripts (compare_to_lines, predict_player, predict_slate) want to
filter / warn on injured players. Single source of truth lives here.

Status taxonomy from official.nba.com:
  OUT, DOUBTFUL, NOT WITH TEAM   → unavailable (skip / hard-warn)
  QUESTIONABLE                    → soft-warn (player still likely to play)
  PROBABLE, AVAILABLE             → ignore
"""
from __future__ import annotations

import json
import os
import unicodedata
from datetime import date as _date
from typing import Dict, Optional


# Statuses that mean "don't bet this player". QUESTIONABLE is intentionally
# not here — the player is more likely than not to play, and L5/L10 features
# already partially account for limited minutes. NOT-LISTED never blocks.
UNAVAILABLE_STATUSES = frozenset({"OUT", "DOUBTFUL", "NOT WITH TEAM"})

# Statuses that warrant a non-blocking warning (player available but at risk).
SOFT_WARN_STATUSES = frozenset({"QUESTIONABLE"})


def _strip_accents(s: str) -> str:
    """Drop non-ASCII diacritics so 'Jokić' matches 'Jokic' in name lookups."""
    nfkd = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _name_key(name: str) -> str:
    """Canonical lookup key for player names: diacritic-stripped lowercase."""
    return _strip_accents(name or "").lower().strip()


def default_path(d: Optional[_date] = None) -> str:
    """Return data/injuries_<date>.json under the project root."""
    if d is None:
        d = _date.today()
    project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_dir, "data", f"injuries_{d.isoformat()}.json")


def load_injuries(path: Optional[str] = None) -> dict:
    """Read an injury JSON; return the full payload or {} on missing/malformed file."""
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def load_unavailable_players(path: Optional[str] = None) -> Dict[str, str]:
    """Return {canonical_name_key: status} for OUT/DOUBTFUL/NOT-WITH-TEAM players."""
    payload = load_injuries(path)
    out: Dict[str, str] = {}
    for p in payload.get("players", []) or []:
        status = str(p.get("status", "")).upper().strip()
        name = p.get("name", "")
        if not name or status not in UNAVAILABLE_STATUSES:
            continue
        out[_name_key(name)] = status
    return out


def load_soft_warn_players(path: Optional[str] = None) -> Dict[str, str]:
    """Return {canonical_name_key: status} for QUESTIONABLE players."""
    payload = load_injuries(path)
    out: Dict[str, str] = {}
    for p in payload.get("players", []) or []:
        status = str(p.get("status", "")).upper().strip()
        name = p.get("name", "")
        if not name or status not in SOFT_WARN_STATUSES:
            continue
        out[_name_key(name)] = status
    return out


def lookup_status(name: str, unavailable: Dict[str, str],
                   soft_warn: Optional[Dict[str, str]] = None) -> Optional[str]:
    """Return the player's status if listed, else None. Diacritic-insensitive."""
    key = _name_key(name)
    if key in unavailable:
        return unavailable[key]
    if soft_warn and key in soft_warn:
        return soft_warn[key]
    return None
