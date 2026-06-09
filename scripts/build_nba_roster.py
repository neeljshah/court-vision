"""build_nba_roster.py — one-shot script to generate data/players_nba_active.json.

Pulls active NBA player names from nba_api.stats.static.players and writes
a JSON array of full_name strings to data/players_nba_active.json.

Usage:
    python scripts/build_nba_roster.py

The resulting file is used by api/_courtvision_odds.py to filter non-NBA
(e.g. WNBA) players out of the consolidated odds feed.
Run refresh_nba_roster.py for in-season updates (adds rookies, drops released).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT  = _ROOT / "data" / "players_nba_active.json"


def build() -> int:
    try:
        from nba_api.stats.static import players  # type: ignore[import]
    except ImportError:
        print("ERROR: nba_api not installed.  Run: pip install nba_api", file=sys.stderr)
        sys.exit(1)

    active = players.get_active_players()
    names  = sorted({p["full_name"] for p in active if p.get("full_name")})

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with _OUT.open("w", encoding="utf-8") as f:
        json.dump(names, f, indent=2)

    print(f"Wrote {len(names)} NBA active players -> {_OUT}")
    return len(names)


if __name__ == "__main__":
    build()
