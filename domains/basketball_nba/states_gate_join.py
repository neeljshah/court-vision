"""domains.basketball_nba.states_gate_join -- CDN checkpoint-states <-> ESPN
linescores join map, PORTED from domains.basketball_wnba.states_gate_join.

WHY A SEPARATE JOIN MODULE
--------------------------
An NBA CDN checkpoint-states corpus (lane 4 backfills it) keys rows by the
CDN's own `game_id` (cdn.nba.com / stats.nba.com 10-digit format, e.g.
"0022500003" -- see data/cache/team_system/box/<game_id>.json for the
existing boxscore cache in this exact id space). data/domains/basketball_nba/
linescores.parquet keys rows by ESPN's `event_id` (e.g. "401809243"). There
is no shared id column (verified: zero overlap between games.parquet's
game_id and linescores.parquet's event_id) -- this module builds the
crosswalk from each game's cached CDN boxscore JSON (teamCity+teamName +
gameEt date), joined against linescores' (date, home_team, away_team) tuple,
mirroring the WNBA join exactly. Unmatched games (preseason, or games newer
than the linescores corpus) are DROPPED, never fabricated -- see
build_join_map's returned unmatched list.

CDN BOX CACHE LAYOUT DIFFERS FROM WNBA: WNBA's cdn_backfill/<game_id>/
boxscore.json is a per-game SUBDIRECTORY; NBA's existing cache is a FLAT
file data/cache/team_system/box/<game_id>.json (same {"game": {...}} inner
schema: gameEt, homeTeam.teamCity/teamName, awayTeam.teamCity/teamName --
verified against a real cached file). box_path_getter is injectable so
lane 4's eventual backfill directory (whatever shape it lands in) can be
wired in without editing this module.

PROVENANCE: this join is validation-only glue for the states gate; it does
not touch or mutate any checkpoint-states corpus or linescores.parquet.

INVARIANTS: <=300 LOC; ASCII only; pandas + stdlib only; no network (reads
already-cached boxscore JSON off disk); never raises on a single malformed
game (skipped, counted in `unmatched`).

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_nba/test_states_gate_join.py -q
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[2]
LINESCORES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "linescores.parquet"
# Placeholder path for lane 4's eventual NBA CDN checkpoint-states corpus.
# Does not exist yet at authoring time -- see states_gate_runner.py's
# NO_CORPUS honest path, which checks this exact path.
STATES_PARQUET = _REPO_ROOT / "data" / "domains" / "basketball_nba" / "cdn_checkpoint_states.parquet"
# Existing flat CDN boxscore JSON cache (verified on disk, 196 files at
# authoring time): data/cache/team_system/box/<game_id>.json
_DEFAULT_BOX_DIR = _REPO_ROOT / "data" / "cache" / "team_system" / "box"


def _default_box_path(game_id: str) -> Path:
    return _DEFAULT_BOX_DIR / f"{game_id}.json"


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
    """(date_str, home_team, away_team) -> event_id, for every linescores row.
    NBA linescores.parquet carries home_abbr/away_abbr, not full team names --
    callers of build_join_map must pass a linescores_df with home_team/
    away_team full-name columns (e.g. joined from games.parquet) if the
    default parquet lacks them; this function only reads whatever columns
    are present, matching the WNBA contract exactly."""
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
    box_path_getter=_default_box_path,
) -> Dict[str, object]:
    """Build {cdn_game_id -> event_id} for every CDN game_id whose cached
    boxscore JSON matches exactly one linescores row on (date, home, away).

    Returns:
      {
        "game_id_to_event_id": {cdn_game_id: event_id, ...},
        "matched": int, "unmatched": [{"game_id":..., "reason":...}, ...],
      }
    Never raises -- a missing/malformed boxscore is recorded as unmatched.
    """
    if linescores_df is None:
        linescores_df = pd.read_parquet(LINESCORES_PARQUET)
    key_map = _linescores_key_map(linescores_df)

    game_id_to_event_id: Dict[str, str] = {}
    unmatched: List[Dict[str, str]] = []

    for gid in cdn_game_ids:
        box_path = box_path_getter(gid)
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
    """Every distinct game_id present in the checkpoint-states corpus,
    sorted. Callers should check STATES_PARQUET.exists() first (or catch
    FileNotFoundError) -- the corpus does not exist until lane 4 backfills
    it; see states_gate_runner.py's NO_CORPUS path."""
    df = states_df if states_df is not None else pd.read_parquet(STATES_PARQUET)
    return sorted(df["game_id"].astype(str).unique().tolist())


__all__ = [
    "build_join_map", "all_backfilled_game_ids",
    "LINESCORES_PARQUET", "STATES_PARQUET",
]
