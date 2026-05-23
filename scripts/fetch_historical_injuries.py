"""fetch_historical_injuries.py — derive per-game stars-available from gamelogs.

The WinProb model has `home_stars_available` / `away_stars_available` columns
declared in FEATURE_COLS but defaulted to the constant 3 across every cached
row (since `_get_stars_available` only worked at INFERENCE time, not in the
row builder). Result: the model had zero historical injury awareness.

This script fixes that by deriving a per-game stars-available count from
player game logs:

  1. For each season, pull `leaguedashplayerstats` to identify the top N
     players per team by total minutes (default N=8 — captures the starting
     lineup + ~3 key bench rotation).
  2. For each of those players, pull their `playergamelog` for the season
     (one API call per player → the set of game_ids they appeared in).
  3. For each game in the season, count how many of the home team's top-N
     and how many of the away team's top-N actually played in that game.

Output: data/nba/stars_available_{season}.json
    {game_id: {team_abbreviation: int_count, ...}, ...}

Read at row-build time by fetch_historical_seasons.py (and the production
_build_features at predict time later if we want).

Run:
    python scripts/fetch_historical_injuries.py 2021-22 2022-23 2023-24 2024-25
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Set

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.data import nba_api_headers_patch  # noqa: F401, E402

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")

# How many players per team to count as "stars". Captures starting 5 +
# the 3 most-used rotation pieces. Top-8 balances coverage vs noise from
# very-low-minute bench players whose absence rarely matters.
_TOP_N = 8

# Polite delay between API calls (the NBA stats API rate-limits aggressively).
_DELAY = 0.5


def _fetch_top_players(season: str) -> Dict[str, List[int]]:
    """Return {team_abbrev: [player_ids ordered by minutes desc]} for season."""
    from nba_api.stats.endpoints import leaguedashplayerstats
    time.sleep(_DELAY)
    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season, season_type_all_star="Regular Season",
        measure_type_detailed_defense="Base", per_mode_detailed="Totals",
    ).get_data_frames()[0]
    out: Dict[str, List[int]] = {}
    for team, grp in df.sort_values("MIN", ascending=False).groupby("TEAM_ABBREVIATION"):
        out[str(team)] = [int(pid) for pid in grp["PLAYER_ID"].head(_TOP_N).tolist()]
    return out


def _fetch_player_gamelog(player_id: int, season: str) -> Set[str]:
    """Return the set of game_ids a player appeared in this season."""
    from nba_api.stats.endpoints import playergamelog
    time.sleep(_DELAY)
    try:
        df = playergamelog.PlayerGameLog(
            player_id=player_id, season=season,
            season_type_all_star="Regular Season",
        ).get_data_frames()[0]
        return set(str(g) for g in df["Game_ID"].tolist())
    except Exception as e:
        print(f"    [warn] playergamelog {player_id}/{season}: {e}")
        return set()


def fetch_season(season: str) -> int:
    """Build stars_available_{season}.json. Returns number of game rows."""
    out_path = os.path.join(_NBA_CACHE, f"stars_available_{season}.json")
    if os.path.exists(out_path):
        try:
            with open(out_path) as f:
                existing = json.load(f)
            if existing:
                print(f"  [skip] {season}: stars_available already cached "
                      f"({len(existing)} games)")
                return 0
        except Exception:
            pass

    print(f"  [{season}] fetching team top-{_TOP_N} players...", flush=True)
    team_top = _fetch_top_players(season)
    print(f"  [{season}] got top-{_TOP_N} for {len(team_top)} teams", flush=True)

    # Build per-team set of game_ids each top player appeared in.
    print(f"  [{season}] fetching gamelogs for {sum(len(v) for v in team_top.values())} "
          f"players...", flush=True)
    player_games: Dict[int, Set[str]] = {}
    n_done = 0
    total = sum(len(v) for v in team_top.values())
    for team, pids in team_top.items():
        for pid in pids:
            player_games[pid] = _fetch_player_gamelog(pid, season)
            n_done += 1
            if n_done % 30 == 0:
                print(f"    {n_done}/{total} players done", flush=True)

    # Load the season's game list to enumerate (game_id, home_team, away_team).
    games_path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(games_path):
        print(f"  [{season}] season_games cache missing — cannot index games")
        return 0
    with open(games_path) as f:
        payload = json.load(f)
    rows = payload["rows"] if isinstance(payload, dict) else payload

    # For each game, count team top-N players who actually appeared.
    out: Dict[str, Dict[str, int]] = {}
    for row in rows:
        gid = str(row.get("game_id", ""))
        if not gid:
            continue
        home = str(row.get("home_team", ""))
        away = str(row.get("away_team", ""))
        h_count = sum(1 for pid in team_top.get(home, []) if gid in player_games.get(pid, set()))
        a_count = sum(1 for pid in team_top.get(away, []) if gid in player_games.get(pid, set()))
        out[gid] = {home: h_count, away: a_count}

    with open(out_path, "w") as f:
        json.dump(out, f)
    print(f"  [{season}] wrote {len(out)} game stars-available rows -> {out_path}",
          flush=True)
    return len(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("seasons", nargs="+")
    args = ap.parse_args()
    print(f"Historical injury (stars-available) fetcher for {args.seasons}\n")
    t0 = time.time()
    for s in args.seasons:
        print(f"=== {s} ===", flush=True)
        fetch_season(s)
    print(f"\nDONE in {time.time()-t0:.1f}s")


if __name__ == "__main__":
    main()
