"""scripts.platformkit.omni.box_store_refresh -- BOX-REFRESH lane.

STEP 0 PREMISE CHECK (2026-07-13, see .planning/omni/handoff/BOXREFRESH_result.md
for the full writeup): the K sweep's player-box source
(data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet,
max date 2026-04-12) is a snapshot copy of
data/domains/basketball_nba/player_boxscores.parquet -- SAME row count (77744),
SAME max date. The upstream store itself is stale, not just the snapshot; its
writer lives under a human-gated tree this lane may not touch. 2026-04-12 is
the 2025-26 REGULAR SEASON end (games.parquet, the schedule index, also stops
there) -- so every date after it is, by construction, a playoff date.

A player-level box source THAT DOES exist on disk past that cutoff:
data/cache/team_system/box/*.json (raw nba.cloud boxscore payloads, one file
per game_id). Of 196 cached games, 34 have gameEt > 2026-04-12 and ALL 34 carry
a "0042" (playoff) game_id prefix -- through 2026-06-05 (Finals Gm2). This
module extracts those 34 games' player rows into a same-schema extension
parquet WITHOUT touching the snapshot or player_boxscores.parquet.

This is a PARTIAL fix: data/cache/team_system/box/ is itself a spot sample
(not every playoff game is cached), so the extension covers only what is
already on disk today. A full nightly refresh needs a job that calls the
nba.cloud boxscore endpoint directly -- that job would live in a human-gated
tree (scripts/team_system/** builds this cache today), so the daemon proposal
is written to .planning/omni/proposed/box_refresh_PROPOSED.md instead of built
here.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Never writes
data/registry/ or the original snapshot/player_boxscores stores. No $/edge
claims.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_omni_box_store_refresh.py -q
"""
from __future__ import annotations

import glob
import json
import os
import pathlib
import tempfile
from typing import List, Optional

import pandas as pd

SNAPSHOT_PATH = pathlib.Path(
    "data/cache/intel_claims/nba_player_box_rate__career_to_date_snapshot.parquet"
)
BOX_CACHE_GLOB = "data/cache/team_system/box/*.json"
EXTENSION_PATH = pathlib.Path("data/cache/omni_box_refresh/nba_player_box_extension.parquet")

_SCHEMA_COLS = [
    "game_id", "date", "season", "team", "opp", "is_home", "player_id",
    "player_name", "starter", "min", "pts", "reb", "oreb", "dreb", "ast",
    "stl", "blk", "tov", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "pf",
    "plus_minus",
]

# nba.cloud statistics-dict key -> our column name.
_STAT_MAP = {
    "points": "pts", "reboundsTotal": "reb", "reboundsOffensive": "oreb",
    "reboundsDefensive": "dreb", "assists": "ast", "steals": "stl",
    "blocks": "blk", "turnovers": "tov", "fieldGoalsMade": "fgm",
    "fieldGoalsAttempted": "fga", "threePointersMade": "fg3m",
    "threePointersAttempted": "fg3a", "freeThrowsMade": "ftm",
    "freeThrowsAttempted": "fta", "foulsPersonal": "pf",
    "plusMinusPoints": "plus_minus",
}


def _parse_minutes(iso_dur: Optional[str]) -> float:
    """"PT36M01.00S" -> 36.02 decimal minutes. Missing/empty -> 0.0."""
    if not iso_dur or not iso_dur.startswith("PT"):
        return 0.0
    body = iso_dur[2:]
    mins, _, rest = body.partition("M")
    secs = rest.rstrip("S") or "0"
    try:
        return round(float(mins) + float(secs) / 60.0, 2)
    except ValueError:
        return 0.0


def _season_from_game_id(game_id: str) -> str:
    """"0042500401" -> "2025-26" (chars 3:5 are the season start year, 2-digit)."""
    yy = int(game_id[3:5])
    start_year = 2000 + yy
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def is_playoff_game_id(game_id: str) -> bool:
    """NBA game_id prefix convention: 0042=playoffs, 0052=play-in, 0022=regular season."""
    return game_id[:4] in ("0042", "0052")


def _rows_from_game_json(payload: dict) -> List[dict]:
    game = payload["game"]
    game_id = game["gameId"]
    date_str = (game.get("gameEt") or game.get("gameTimeLocal") or "")[:10]
    season = _season_from_game_id(game_id)
    rows: List[dict] = []
    for side_key, is_home in (("homeTeam", 1.0), ("awayTeam", 0.0)):
        side = game[side_key]
        other = game["awayTeam" if is_home else "homeTeam"]
        team, opp = side["teamTricode"], other["teamTricode"]
        for p in side.get("players", []):
            stats = p.get("statistics", {})
            row = {
                "game_id": game_id, "date": date_str, "season": season,
                "team": team, "opp": opp, "is_home": is_home,
                "player_id": int(p["personId"]), "player_name": p.get("name", ""),
                "starter": p.get("starter") == "1",
                "min": _parse_minutes(stats.get("minutes")),
            }
            for src_key, col in _STAT_MAP.items():
                row[col] = float(stats.get(src_key, 0.0) or 0.0)
            rows.append(row)
    return rows


def _snapshot_max_date(snapshot_path: pathlib.Path) -> pd.Timestamp:
    df = pd.read_parquet(snapshot_path, columns=["date"])
    return df["date"].max()


def build_extension(snapshot_path=None, box_cache_glob: str = BOX_CACHE_GLOB) -> pd.DataFrame:
    """Scan the raw box-cache JSONs, keep only games strictly after the
    snapshot's max date, return a DataFrame matching _SCHEMA_COLS plus
    is_playoffs. Empty (but correctly-typed) frame if nothing qualifies."""
    snap_path = pathlib.Path(snapshot_path) if snapshot_path is not None else SNAPSHOT_PATH
    cutoff = _snapshot_max_date(snap_path)
    rows: List[dict] = []
    for fp in sorted(glob.glob(box_cache_glob)):
        with open(fp, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        game_rows = _rows_from_game_json(payload)
        if not game_rows:
            continue
        game_date = pd.Timestamp(game_rows[0]["date"])
        if pd.isna(game_date) or game_date <= cutoff:
            continue
        is_playoffs = is_playoff_game_id(game_rows[0]["game_id"])
        for r in game_rows:
            r["is_playoffs"] = is_playoffs
        rows.extend(game_rows)

    out = pd.DataFrame(rows, columns=_SCHEMA_COLS + ["is_playoffs"])
    if not out.empty:
        out["date"] = pd.to_datetime(out["date"])
        out = out.drop_duplicates(subset=["game_id", "player_id"]).sort_values(
            ["date", "game_id", "player_id"]
        ).reset_index(drop=True)
    return out


def write_extension(df: pd.DataFrame, path=None) -> pathlib.Path:
    """Atomic tmp-file + os.replace write, same-dir tmp so os.replace is atomic
    on Windows too. Overwrites only the EXTENSION file, never the snapshot."""
    target = pathlib.Path(path) if path is not None else EXTENSION_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp_", suffix=".parquet")
    os.close(fd)
    tmp = pathlib.Path(tmp_name)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink()
    return target


def load_box_full(snapshot_path=None, extension_path=None) -> pd.DataFrame:
    """Concat snapshot + extension for consumers (k_sweeps adopt later).
    Snapshot rows get is_playoffs=False (regular-season-only store by
    construction); extension rows keep their derived flag."""
    snap_path = pathlib.Path(snapshot_path) if snapshot_path is not None else SNAPSHOT_PATH
    ext_path = pathlib.Path(extension_path) if extension_path is not None else EXTENSION_PATH
    snap = pd.read_parquet(snap_path)
    snap = snap.copy()
    snap["is_playoffs"] = False
    if not ext_path.exists():
        return snap
    ext = pd.read_parquet(ext_path)
    if ext.empty:
        return snap
    return pd.concat([snap, ext[snap.columns]], ignore_index=True)


def run_refresh(snapshot_path=None, box_cache_glob: str = BOX_CACHE_GLOB, out_path=None) -> dict:
    ext = build_extension(snapshot_path, box_cache_glob)
    target = write_extension(ext, out_path)
    return {
        "rows_written": int(len(ext)),
        "games": int(ext["game_id"].nunique()) if not ext.empty else 0,
        "playoff_games": int(ext.loc[ext["is_playoffs"], "game_id"].nunique()) if not ext.empty else 0,
        "path": str(target),
    }


if __name__ == "__main__":
    print(f"[box_store_refresh] {run_refresh()}")


__all__ = [
    "build_extension", "write_extension", "load_box_full", "run_refresh",
    "is_playoff_game_id", "SNAPSHOT_PATH", "EXTENSION_PATH",
]
