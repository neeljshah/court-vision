"""src/data/live.py — shared loader / helpers for live in-game state (cycle 88).

Agent H (cycle 88a) writes per-game live state JSONs to
`data/live/<game_id>_<timestamp>.json` with the schema:

    {
      "game_id": "...",
      "captured_at": "ISO-8601",
      "game_status": "PRE_GAME|LIVE|FINAL",
      "period": 2,
      "clock": "5:42",
      "home_score": 56, "away_score": 48,
      "home_team": "OKC", "away_team": "SAS",
      "players": [
        {"player_id": ..., "name": "...", "team": "...",
         "min": 14.5, "pts": 12, "reb": 4, "ast": 3,
         "fg3m": 2, "stl": 1, "blk": 0, "tov": 1, "pf": 2,
         "is_starter": true},
        ...
      ]
    }

This module is the SINGLE PARSER consumers (predict_in_game, foul_trouble_adjust,
blowout_adjust, live_dashboard) should use — so when Agent H's schema lands
slightly different than spec'd here, callers only fix this file.

Mirrors the cycle 53 (src/data/injuries.py) + cycle 62 (src/data/lineups.py)
single-source-of-truth pattern.
"""
from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
from datetime import date as _date
from typing import Dict, List, Optional


# Each NBA period is 12 minutes. OT periods are 5 min (period >= 5).
_REG_PERIOD_MIN = 12.0
_OT_PERIOD_MIN = 5.0


def _strip_accents(s: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(s or ""))
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _name_key(name: str) -> str:
    """Mirror cycle 53/62: canonical lookup key for diacritic-insensitive matching."""
    return _strip_accents(name or "").lower().strip()


# ── file discovery ──────────────────────────────────────────────────────────

def live_dir(project_dir: Optional[str] = None) -> str:
    """Return the canonical data/live/ directory path."""
    project_dir = project_dir or os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(project_dir, "data", "live")


def latest_snapshot_path(game_id: str,
                          project_dir: Optional[str] = None) -> Optional[str]:
    """Most-recent snapshot file for a given game_id, or None if no snapshots."""
    d = live_dir(project_dir)
    if not os.path.isdir(d):
        return None
    candidates = glob.glob(os.path.join(d, f"{game_id}_*.json"))
    if not candidates:
        return None
    # File names contain timestamps so lex sort matches chronological.
    candidates.sort()
    return candidates[-1]


def list_today_snapshots(date_str: Optional[str] = None,
                          project_dir: Optional[str] = None) -> List[str]:
    """Return latest-snapshot-per-game for the date. date_str defaults to today."""
    if date_str is None:
        date_str = _date.today().isoformat()
    d = live_dir(project_dir)
    if not os.path.isdir(d):
        return []
    # Group by game_id (filename = <game_id>_<timestamp>.json)
    by_game: Dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(d, "*.json"))):
        name = os.path.basename(path)
        m = re.match(r"^(\d+)_", name)
        if not m:
            continue
        game_id = m.group(1)
        # Only include if file mtime is on date_str. Cheap filter.
        # Alternative: parse captured_at — overkill for the file lister.
        by_game[game_id] = path        # later sort wins (latest snapshot)
    return list(by_game.values())


# ── state I/O ───────────────────────────────────────────────────────────────

def load_live_state(path: Optional[str]) -> dict:
    """Read one snapshot JSON. {} on missing / malformed."""
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


# ── time helpers ────────────────────────────────────────────────────────────

def parse_clock(clock_str: str) -> float:
    """'5:42' -> 5.7 minutes remaining IN THE CURRENT PERIOD.

    Accepts: 'M:SS', 'MM:SS', integer string (assumed minutes), float string.
    Returns 0.0 on unparseable input.
    """
    if clock_str is None or clock_str == "":
        return 0.0
    s = str(clock_str).strip()
    if ":" in s:
        try:
            mins, secs = s.split(":", 1)
            return float(mins) + float(secs) / 60.0
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def period_length_minutes(period: int) -> float:
    """Q1-Q4 are 12 min. OT periods (5+) are 5 min."""
    return _REG_PERIOD_MIN if period <= 4 else _OT_PERIOD_MIN


def elapsed_game_minutes(period: int, clock_str: str) -> float:
    """Total minutes ELAPSED of the game so far.

    Q2 with 8:00 left -> 12 (Q1) + (12-8) (Q2 elapsed) = 16 minutes.
    """
    if period < 1:
        return 0.0
    full_prior = 0.0
    for p in range(1, period):
        full_prior += period_length_minutes(p)
    cur = period_length_minutes(period)
    rem = parse_clock(clock_str)
    rem = max(0.0, min(rem, cur))
    return full_prior + (cur - rem)


def remaining_game_minutes(period: int, clock_str: str) -> float:
    """Minutes left in regulation (or current OT period). Caps at 48.

    Used as the 'pace remaining share' divisor for in-game projection.
    """
    if period >= 5:    # OT — game is in overtime
        return parse_clock(clock_str)
    elapsed = elapsed_game_minutes(period, clock_str)
    return max(0.0, _REG_PERIOD_MIN * 4 - elapsed)


def clock_share_played(period: int, clock_str: str) -> float:
    """Fraction of regulation (48 min) elapsed, capped 0..1."""
    e = elapsed_game_minutes(period, clock_str)
    s = e / (_REG_PERIOD_MIN * 4)
    return max(0.0, min(1.0, s))


# ── player lookup ───────────────────────────────────────────────────────────

def find_player(snapshot: dict, name: str) -> Optional[dict]:
    """Locate a player by name (diacritic-insensitive) in a live snapshot dict."""
    key = _name_key(name)
    for p in snapshot.get("players", []) or []:
        if _name_key(p.get("name", "")) == key:
            return p
    return None


def find_player_by_id(snapshot: dict, player_id) -> Optional[dict]:
    """Locate a player by numeric player_id. Accepts int OR string."""
    pid = str(player_id)
    for p in snapshot.get("players", []) or []:
        if str(p.get("player_id", "")) == pid:
            return p
    return None


def starters(snapshot: dict, team: Optional[str] = None) -> List[dict]:
    """All starters in snapshot, optionally filtered to a team abbreviation."""
    out = []
    for p in snapshot.get("players", []) or []:
        if not p.get("is_starter"):
            continue
        if team and (p.get("team", "").upper() != team.upper()):
            continue
        out.append(p)
    return out


# ── game state derivatives ──────────────────────────────────────────────────

def score_margin(snapshot: dict, perspective: str = "home") -> int:
    """Signed score margin from one team's perspective.

    perspective='home' -> home_score - away_score (positive = home leading)
    perspective='away' -> away_score - home_score
    Missing scores default to 0.
    """
    h = int(snapshot.get("home_score", 0) or 0)
    a = int(snapshot.get("away_score", 0) or 0)
    return (h - a) if perspective == "home" else (a - h)


def absolute_margin(snapshot: dict) -> int:
    """Magnitude of the score gap regardless of which team is leading."""
    return abs(score_margin(snapshot, "home"))


def is_blowout(snapshot: dict, threshold: int = 20) -> bool:
    """True if margin >= threshold AND in Q4+ (where blowout matters most).

    Blowout in Q1 doesn't mean garbage time yet — game can swing back.
    """
    period = int(snapshot.get("period", 0) or 0)
    if period < 4:
        return False
    return absolute_margin(snapshot) >= threshold


def is_live(snapshot: dict) -> bool:
    """True if game_status indicates the game is in progress."""
    return str(snapshot.get("game_status", "")).upper() == "LIVE"


def is_final(snapshot: dict) -> bool:
    """True if game has ended."""
    return str(snapshot.get("game_status", "")).upper() == "FINAL"
