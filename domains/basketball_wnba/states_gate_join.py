"""domains.basketball_wnba.states_gate_join -- CDN checkpoint-states <-> ESPN
linescores join map (LANE 5 step 1).

WHY A SEPARATE JOIN MODULE
--------------------------
data/domains/wnba/cdn_backfill_states.parquet keys rows by the CDN's own
`game_id` (stats.wnba.com numeric id, e.g. "1012600001"). data/domains/wnba/
linescores.parquet keys rows by ESPN's `event_id` (e.g. "401649378"). There is
no shared id column -- this module builds the crosswalk from each backfilled
game's boxscore.json (teamCity+teamName + gameEt date), joined against
linescores' (date, home_team, away_team) tuple. Unmatched games (preseason
exhibitions vs national teams, or games newer than the linescores corpus) are
DROPPED, never fabricated -- see build_join_map's returned unmatched list.

PROVENANCE: this join is validation-only glue for LANE 5's states gate; it
does not touch or mutate cdn_backfill_states.parquet or linescores.parquet.

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network (reads
already-backfilled boxscore.json files off disk); never raises on a single
malformed game (skipped, counted in `unmatched`).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_states_gate_join.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from domains.basketball_wnba.cdn_backfill import game_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]
LINESCORES_PARQUET = _REPO_ROOT / "data" / "domains" / "wnba" / "linescores.parquet"
STATES_PARQUET = _REPO_ROOT / "data" / "domains" / "wnba" / "cdn_backfill_states.parquet"


def _team_full_name(team: dict) -> str:
    city = str(team.get("teamCity") or "").strip()
    name = str(team.get("teamName") or "").strip()
    return f"{city} {name}".strip()


def _boxscore_join_key(box_game: dict) -> Optional[Tuple[str, str, str]]:
    """(date, home_team, away_team) tuple matching linescores' schema, or None
    if the boxscore is malformed (missing date/team fields)."""
    et = str(box_game.get("gameEt") or "")[:10]
    home = _team_full_name(box_game.get("homeTeam") or {})
    away = _team_full_name(box_game.get("awayTeam") or {})
    if not et or not home or not away:
        return None
    return (et, home, away)


def _linescores_key_map(linescores_df: pd.DataFrame) -> Dict[Tuple[str, str, str], str]:
    """(date_str, home_team, away_team) -> event_id, for every linescores row."""
    df = linescores_df.copy()
    df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    out: Dict[Tuple[str, str, str], str] = {}
    for _, r in df.iterrows():
        key = (str(r["date_str"]), str(r["home_team"]), str(r["away_team"]))
        out[key] = str(r["event_id"])
    return out


def build_join_map(
    cdn_game_ids: List[str],
    linescores_df: Optional[pd.DataFrame] = None,
    backfill_dir_getter=game_dir,
) -> Dict[str, object]:
    """Build {cdn_game_id -> event_id} for every CDN game_id whose backfilled
    boxscore.json matches exactly one linescores row on (date, home, away).

    Returns:
      {
        "game_id_to_event_id": {cdn_game_id: event_id, ...},
        "matched": int, "unmatched": [{"game_id":..., "reason":...}, ...],
      }
    Never raises -- a missing/malformed boxscore is recorded as unmatched.
    """
    lines = linescores_df if linescores_df is not None else pd.read_parquet(LINESCORES_PARQUET)
    key_map = _linescores_key_map(lines)

    game_id_to_event_id: Dict[str, str] = {}
    unmatched: List[Dict[str, str]] = []

    for gid in cdn_game_ids:
        box_path = backfill_dir_getter(gid) / "boxscore.json"
        if not box_path.exists():
            unmatched.append({"game_id": gid, "reason": "no_boxscore_file"})
            continue
        try:
            payload = json.loads(box_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            unmatched.append({"game_id": gid, "reason": "malformed_boxscore"})
            continue
        box_game = payload.get("game")
        if not isinstance(box_game, dict):
            unmatched.append({"game_id": gid, "reason": "no_game_key"})
            continue
        key = _boxscore_join_key(box_game)
        if key is None:
            unmatched.append({"game_id": gid, "reason": "missing_join_fields"})
            continue
        event_id = key_map.get(key)
        if event_id is None:
            unmatched.append({"game_id": gid, "reason": "no_linescores_match", "key": str(key)})
            continue
        game_id_to_event_id[gid] = event_id

    return {
        "game_id_to_event_id": game_id_to_event_id,
        "matched": len(game_id_to_event_id),
        "unmatched": unmatched,
    }


def all_backfilled_game_ids(states_df: Optional[pd.DataFrame] = None) -> List[str]:
    """Every distinct game_id present in cdn_backfill_states.parquet, sorted."""
    df = states_df if states_df is not None else pd.read_parquet(STATES_PARQUET)
    return sorted(df["game_id"].astype(str).unique().tolist())


__all__ = [
    "build_join_map", "all_backfilled_game_ids",
    "LINESCORES_PARQUET", "STATES_PARQUET",
]
