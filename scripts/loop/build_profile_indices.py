"""Regenerate PLAYER_INDEX.json and TEAM_INDEX.json deterministically.

Reads the built profile JSONs under ``data/cache/profiles/players/`` and
``data/cache/profiles/teams/`` and emits the two roll-up index files that
the intelligence layer / memory_writer uses for discovery.

PLAYER_INDEX.json shape (verified against 2026-05-30 baseline):
  {
    "built": "YYYY-MM-DD",
    "n_players": <int>,
    "max_sections": <int>,
    "fully_loaded_15plus": <int>,
    "players": [
      {"player_id": <int>, "name": <str>, "n_sections": <int>,
       "sections": [<str>, ...], "as_of": <str>,
       "pts_pg": <float|null>, "min_pg": <float|null>,
       "n_games": <int|null>,
       "has_clutch": <bool>, "has_coverage_faced": <bool>,
       "has_prop_cal": <bool>},
      ...
    ]
  }

TEAM_INDEX.json shape (verified):
  {
    "built": "YYYY-MM-DD",
    "n_teams": <int>,
    "teams": [
      {"team": <str>, "n_sections": <int>,
       "off_rtg": <float|null>, "def_rtg": <float|null>,
       "pace": <float|null>, "scheme": <str|null>,
       "scheme_conf": <str|null>},
      ...
    ]
  }

Run:
    python scripts/loop/build_profile_indices.py
    NBA_OFFLINE=1 python scripts/loop/build_profile_indices.py
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Script-relative root — always use this pattern, never hardcode C:/...
ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "data" / "cache" / "profiles"
PLAYERS_DIR = PROFILES / "players"
TEAMS_DIR = PROFILES / "teams"
PLAYER_INDEX = PROFILES / "PLAYER_INDEX.json"
TEAM_INDEX = PROFILES / "TEAM_INDEX.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(d: dict, *keys: str) -> Optional[float]:
    """Walk nested dict with a dotted key sequence and return a float or None."""
    val: Any = d
    for k in keys:
        if not isinstance(val, dict):
            return None
        val = val.get(k)
    if val is None:
        return None
    try:
        return round(float(val), 4)
    except (TypeError, ValueError):
        return None


def _safe_int(d: dict, *keys: str) -> Optional[int]:
    """Walk nested dict and return an int or None."""
    val = _safe_float(d, *keys)
    return int(val) if val is not None else None


# ---------------------------------------------------------------------------
# Player index builder
# ---------------------------------------------------------------------------

def _player_row(path: Path) -> Optional[Dict[str, Any]]:
    """Parse one player profile JSON into an index row."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    sections_dict: dict = d.get("sections", {})
    sections_list = sorted(sections_dict.keys())
    n_sections = len(sections_list)

    # Scoring stats live in scoring_usage.scoring sub-dict.
    scoring = sections_dict.get("scoring_usage", {}).get("scoring", {})
    pts_pg = _safe_float(scoring, "pts_pg")
    min_pg = _safe_float(scoring, "min_per_game")
    n_games = _safe_int(scoring, "n_games")

    # Fallback: some profiles store top-level pts/min directly.
    if pts_pg is None:
        pts_pg = _safe_float(sections_dict.get("scoring_usage", {}), "pts_pg")
    if min_pg is None:
        min_pg = _safe_float(sections_dict.get("scoring_usage", {}), "min_per_game")

    has_clutch = "clutch" in sections_dict
    has_coverage_faced = "coverage_faced" in sections_dict
    has_prop_cal = "prop_calibration" in sections_dict

    as_of: Optional[str] = d.get("as_of_game_date")

    # player_id is either the filename stem or a field in the JSON.
    try:
        player_id = int(d.get("player_id", path.stem))
    except (TypeError, ValueError):
        player_id = int(path.stem) if path.stem.isdigit() else None

    name: str = d.get("player_name", "")

    return {
        "player_id": player_id,
        "name": name,
        "n_sections": n_sections,
        "sections": sections_list,
        "as_of": as_of,
        "pts_pg": pts_pg,
        "min_pg": min_pg,
        "n_games": n_games,
        "has_clutch": has_clutch,
        "has_coverage_faced": has_coverage_faced,
        "has_prop_cal": has_prop_cal,
    }


def build_player_index() -> Dict[str, Any]:
    """Scan players/ and return the index dict (not yet written to disk)."""
    rows: List[Dict[str, Any]] = []
    for p in sorted(PLAYERS_DIR.glob("*.json")):
        row = _player_row(p)
        if row is not None:
            rows.append(row)

    # Sort by player_id for determinism.
    rows.sort(key=lambda r: (r.get("player_id") or 0))

    max_sections = max((r["n_sections"] for r in rows), default=0)
    fully_loaded = sum(1 for r in rows if r["n_sections"] >= 15)

    return {
        "built": _dt.date.today().isoformat(),
        "n_players": len(rows),
        "max_sections": max_sections,
        "fully_loaded_15plus": fully_loaded,
        "players": rows,
    }


# ---------------------------------------------------------------------------
# Team index builder
# ---------------------------------------------------------------------------

def _team_row(path: Path) -> Optional[Dict[str, Any]]:
    """Parse one team profile JSON into an index row."""
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    sections_dict: dict = d.get("sections", {})

    # Ratings live in sections.ratings
    ratings = sections_dict.get("ratings", {})
    off_rtg = _safe_float(ratings, "off_rtg")
    def_rtg = _safe_float(ratings, "def_rtg")
    pace = _safe_float(ratings, "pace")

    # Scheme lives in sections.defense_scheme
    scheme_section = sections_dict.get("defense_scheme", {})
    scheme: Optional[str] = scheme_section.get("primary_scheme")
    scheme_conf: Optional[str] = None
    prov = d.get("_provenance", {})
    if scheme_section:
        scheme_conf = prov.get("defense_scheme", {}).get("confidence")

    team: str = d.get("team_tricode", path.stem)
    n_sections = len(sections_dict)

    return {
        "team": team,
        "n_sections": n_sections,
        "off_rtg": off_rtg,
        "def_rtg": def_rtg,
        "pace": pace,
        "scheme": scheme,
        "scheme_conf": scheme_conf,
    }


def build_team_index() -> Dict[str, Any]:
    """Scan teams/ and return the index dict."""
    rows: List[Dict[str, Any]] = []
    for p in sorted(TEAMS_DIR.glob("*.json")):
        row = _team_row(p)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: r.get("team", ""))

    return {
        "built": _dt.date.today().isoformat(),
        "n_teams": len(rows),
        "teams": rows,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Regenerate both indices and write to disk."""
    if not PLAYERS_DIR.exists():
        print(f"ERROR: players dir not found: {PLAYERS_DIR}", file=sys.stderr)
        return 1

    print(f"Scanning {PLAYERS_DIR} ...")
    player_idx = build_player_index()
    PLAYER_INDEX.write_text(
        json.dumps(player_idx, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"  PLAYER_INDEX.json: {player_idx['n_players']} players, "
          f"max_sections={player_idx['max_sections']}, "
          f"fully_loaded_15plus={player_idx['fully_loaded_15plus']}")

    if TEAMS_DIR.exists():
        print(f"Scanning {TEAMS_DIR} ...")
        team_idx = build_team_index()
        TEAM_INDEX.write_text(
            json.dumps(team_idx, indent=1, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  TEAM_INDEX.json: {team_idx['n_teams']} teams")
    else:
        print(f"WARN: teams dir not found: {TEAMS_DIR}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
