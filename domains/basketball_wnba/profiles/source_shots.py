"""domains.basketball_wnba.profiles.source_shots -- one row per shot ATTEMPT
(offense side, i.e. keyed to the SHOOTER's own team_id) across the 168-game
2026 WNBA cdn_backfill PBP corpus, for the zone-shooting player attributes in
ingredients_zone.py.

Verified on real WNBA actions before building this: x/y are the same 0-100
percent, 2-ended court convention as the NBA cdn PBP (e.g. a "9' driving"
shot at x=14.99,y=49.98 backs out to 8.84ft via composition.zone_geometry's
formula -- within rounding of the description's own distance label; a layup
at x=93.16 backs out to 1.87ft, correctly landing in "rim"). No coordinate
transform needed -- classify_zone is reused UNMODIFIED, cross-domain, same
precedent as on_off_wnba.py reusing NBA lineup machinery unmodified.

assistPersonId is present (nullable) on made shots exactly like the NBA cdn
schema -- is_assisted is 1 iff that field is a non-null person id.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from domains.basketball_nba.composition.zone_geometry import classify_zone

REPO_ROOT = Path(__file__).resolve().parents[3]
_PBP_DIR = REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill"


def load_game_shots(game_json: dict[str, Any]) -> pd.DataFrame:
    """One row per shot attempt, offense-keyed (team_id = shooter's team)."""
    game_id = str(game_json["game"]["gameId"])
    actions = game_json["game"]["actions"]
    rows = []
    for a in actions:
        if a.get("actionType") not in ("2pt", "3pt") or not a.get("teamId") or a.get("x") is None or not a.get("personId"):
            continue
        is_3 = a["actionType"] == "3pt"
        made = 1 if a.get("shotResult") == "Made" else 0
        rows.append({
            "game_id": game_id, "team_id": int(a["teamId"]), "person_id": int(a["personId"]),
            "zone": classify_zone(float(a["x"]), float(a["y"]), is_3),
            "fgm": made, "fga": 1,
            "is_assisted": 1 if made and a.get("assistPersonId") else 0,
        })
    return pd.DataFrame(rows)


def load_all_shots(pbp_dir: Path = _PBP_DIR, limit: int | None = None) -> pd.DataFrame:
    game_dirs = sorted(d for d in pbp_dir.iterdir() if d.is_dir() and (d / "playbyplay.json").exists())
    if limit:
        game_dirs = game_dirs[:limit]
    frames = [load_game_shots(json.loads((d / "playbyplay.json").read_text(encoding="utf-8"))) for d in game_dirs]
    cols = ["game_id", "team_id", "person_id", "zone", "fgm", "fga", "is_assisted"]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=cols)
