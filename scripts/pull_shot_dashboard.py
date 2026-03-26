"""
pull_shot_dashboard.py -- Phase A1: Pull PlayerDashPtShots for all players.

Calls get_shot_dashboard() for every player_id in data/nba/player_avgs_*.json
across all 3 seasons (2022-23, 2023-24, 2024-25).

Saves combined output to data/nba/shot_dashboard_all_<season>.json
format: {player_id: {contested_pct, uncontested_pct, pull_up_pct,
         catch_shoot_pct, avg_defender_dist_contested, avg_defender_dist_catch_shoot}}

Respects NBA API rate limit (0.6s delay between calls).
Skips players already in individual cache (TTL=7 days).
Prints progress: "X/Y players fetched" every 50 players.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Dict, List

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_TTL_7DAYS = 7 * 24 * 3600
_DELAY = 0.6
_SEASONS = ["2022-23", "2023-24", "2024-25"]


def _get_player_ids(season: str) -> List[int]:
    """Load all player IDs from the season's player_avgs cache."""
    avgs_path = os.path.join(_NBA_CACHE, f"player_avgs_{season}.json")
    if not os.path.exists(avgs_path):
        print(f"  [pull_shot_dashboard] player_avgs_{season}.json not found, skipping")
        return []
    with open(avgs_path) as f:
        avgs = json.load(f)
    ids = []
    for entry in avgs.values():
        if isinstance(entry, dict) and "player_id" in entry:
            ids.append(int(entry["player_id"]))
    return list(set(ids))


def _individual_cache_path(player_id: int, season: str) -> str:
    """Path to individual player shot_dashboard cache (nba_tracking_stats.py format)."""
    safe_season = season  # nba_tracking_stats._safe() keeps dashes
    return os.path.join(_NBA_CACHE, f"shot_dashboard_{player_id}_{safe_season}.json")


def _is_fresh(path: str, ttl: float) -> bool:
    """Check if a file exists and is younger than ttl seconds."""
    if not os.path.exists(path):
        return False
    return (time.time() - os.path.getmtime(path)) < ttl


def _save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def pull_season(season: str) -> Dict[str, dict]:
    """
    Pull shot dashboard for all players in a season.

    Returns:
        {player_id_str: shot_dashboard_dict}
    """
    from src.data.nba_tracking_stats import get_shot_dashboard

    output_path = os.path.join(_NBA_CACHE, f"shot_dashboard_all_{season}.json")

    # Load any existing combined results
    existing: Dict[str, dict] = {}
    if os.path.exists(output_path):
        try:
            loaded = json.load(open(output_path))
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            pass

    player_ids = _get_player_ids(season)
    if not player_ids:
        return existing

    total = len(player_ids)
    fetched = 0
    skipped = 0

    print(f"\n[pull_shot_dashboard] Season {season}: {total} players to check")

    for i, pid in enumerate(player_ids):
        pid_str = str(pid)

        # Skip if already in combined cache with real data (7-day TTL)
        if pid_str in existing and isinstance(existing[pid_str], dict) and existing[pid_str]:
            cached_path = _individual_cache_path(pid, season)
            if _is_fresh(cached_path, _TTL_7DAYS):
                skipped += 1
                if (i + 1) % 50 == 0:
                    print(f"  {i+1}/{total} players processed ({fetched} fetched, {skipped} cached)")
                continue

        # Fetch from NBA API (get_shot_dashboard handles its own 24h TTL per player)
        try:
            data = get_shot_dashboard(pid, season)
            if data:
                existing[pid_str] = data
                fetched += 1
            else:
                # Record empty result to avoid repeated 404s
                existing[pid_str] = {}
        except Exception as e:
            print(f"  [pull_shot_dashboard] Error player {pid}: {e}")

        if (i + 1) % 50 == 0:
            pct = round((i + 1) / total * 100)
            print(f"  {i+1}/{total} players processed ({fetched} fetched, {skipped} cached) {pct}%")
            _save(output_path, existing)

        time.sleep(_DELAY)

    # Final save
    _save(output_path, existing)
    has_data = sum(1 for v in existing.values() if isinstance(v, dict) and v.get("contested_pct", 0) > 0)
    print(f"  [pull_shot_dashboard] {season} complete: {len(existing)} total, {has_data} with data, {fetched} newly fetched")
    return existing


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Pull PlayerDashPtShots for all players")
    parser.add_argument(
        "--seasons", nargs="+", default=_SEASONS,
        help="Seasons to pull (default: all 3)",
    )
    args = parser.parse_args()

    total_players = 0
    for season in args.seasons:
        results = pull_season(season)
        total_players += sum(1 for v in results.values() if isinstance(v, dict) and v.get("contested_pct", 0) > 0)

    print(f"\n[pull_shot_dashboard] Done. {total_players} player-seasons with shot data.")


if __name__ == "__main__":
    main()
