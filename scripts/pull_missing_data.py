"""
pull_missing_data.py -- Phase A bulk data pull.

Fetches all missing NBA API data for 3 seasons in order of priority:
  A1  PlayerDashPtShots   -- contested%, pull-up%, defender dist (HIGHEST PRIORITY)
  A2  PlayerTrackingStats -- season-level speed, distance, touches
  A3  SynergyPlayTypes    -- backfill 2022-23 + 2023-24 (2024-25 already exists)
  A4  Full schedules      -- all 30 teams x 3 seasons
  A5  Referee tendencies  -- foul rate, home win%, pace per ref

Usage:
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system
    python scripts/pull_missing_data.py               # all phases
    python scripts/pull_missing_data.py --phase A1    # single phase
    python scripts/pull_missing_data.py --check       # show coverage summary
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_DATA = os.path.join(PROJECT_DIR, "data", "nba")
_SEASONS  = ["2024-25", "2023-24", "2022-23"]

_ALL_TEAMS = [
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS",
]


# ─────────────────────────────────────────────────────────────────────────────
# Coverage check
# ─────────────────────────────────────────────────────────────────────────────

def check_coverage() -> None:
    """Print a summary of what Phase A data exists vs. what's missing."""
    print("\n=== Phase A Data Coverage ===\n")

    # A1 -- shot dashboards
    print("A1 -- Shot Dashboard (PlayerDashPtShots):")
    for s in _SEASONS:
        path = os.path.join(_NBA_DATA, f"shot_dashboard_all_{s.replace('-', '-')}.json")
        exists = os.path.exists(path)
        count  = len(json.load(open(path))) if exists else 0
        status = f"[OK] {count} players" if exists else "[MISSING]"
        print(f"  {s}: {status}")

    # A2 -- season tracking stats
    print("\nA2 -- Season Tracking Stats (PlayerTrackingStats):")
    for s in _SEASONS:
        path = os.path.join(_NBA_DATA, f"player_tracking_{s.replace('-', '-')}.json")
        exists = os.path.exists(path)
        count  = len(json.load(open(path))) if exists else 0
        status = f"[OK] {count} players" if exists else "[MISSING]"
        print(f"  {s}: {status}")

    # A3 -- synergy
    print("\nA3 -- Synergy Play Types:")
    for s in _SEASONS:
        path = os.path.join(_NBA_DATA, f"synergy_offensive_all_{s.replace('-', '-')}.json")
        exists = os.path.exists(path)
        count  = len(json.load(open(path))) if exists else 0
        status = f"[OK] {count} records" if exists else "[MISSING]"
        print(f"  {s}: {status}")

    # A4 -- schedules
    print("\nA4 -- Schedules (all 30 teams x 3 seasons):")
    sched_dir = os.path.join(_NBA_DATA, "schedule")
    for s in _SEASONS:
        found = 0
        for t in _ALL_TEAMS:
            p = os.path.join(sched_dir, f"schedule_{t}_{s}_v2.json")
            if not os.path.exists(p):
                p = os.path.join(sched_dir, f"schedule_{t}_{s}.json")
            if os.path.exists(p):
                found += 1
        status = f"[OK] {found}/30 teams" if found == 30 else f"[PARTIAL] {found}/30 teams"
        print(f"  {s}: {status}")

    # A5 -- referee tendencies
    print("\nA5 -- Referee Tendencies:")
    path = os.path.join(_NBA_DATA, "ref_tendencies.json")
    if os.path.exists(path):
        data  = json.load(open(path))
        count = len(data)
        print(f"  [OK] {count} referees")
    else:
        print("  [MISSING]")

    print()


# ─────────────────────────────────────────────────────────────────────────────
# A1 -- Shot Dashboard
# ─────────────────────────────────────────────────────────────────────────────

def pull_a1_shot_dashboards() -> None:
    """Pull PlayerDashPtShots for all players x 3 seasons."""
    from src.data.nba_tracking_stats import get_shot_dashboard_all_players

    print("\n=== A1: Shot Dashboard (PlayerDashPtShots) ===")
    print("Estimated time: ~8 min/season (569 players x 0.8s)")

    for season in _SEASONS:
        cache_path = os.path.join(_NBA_DATA, f"shot_dashboard_all_{season}.json")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                existing = json.load(f)
            print(f"  {season}: already cached ({len(existing)} players) -- skipping")
            continue

        print(f"  {season}: fetching...", flush=True)
        result = get_shot_dashboard_all_players(season=season, delay=0.8)
        print(f"  {season}: [OK] {len(result)} players saved")


# ─────────────────────────────────────────────────────────────────────────────
# A2 -- Season Tracking Stats
# ─────────────────────────────────────────────────────────────────────────────

def pull_a2_tracking_stats() -> None:
    """Pull season-level PlayerTrackingStats for all 3 seasons."""
    from src.data.nba_tracking_stats import get_season_tracking_stats

    print("\n=== A2: Season Tracking Stats ===")

    for season in _SEASONS:
        cache_path = os.path.join(_NBA_DATA, f"player_tracking_{season}.json")
        if os.path.exists(cache_path):
            with open(cache_path) as f:
                existing = json.load(f)
            print(f"  {season}: already cached ({len(existing)} players) -- skipping")
            continue

        print(f"  {season}: fetching...", flush=True)
        result = get_season_tracking_stats(season=season)
        if result:
            print(f"  {season}: [OK] {len(result)} players saved")
        else:
            print(f"  {season}: [WARN] Empty response -- endpoint may not support 'Tracking' measure type")
        time.sleep(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# A3 -- Synergy Backfill
# ─────────────────────────────────────────────────────────────────────────────

def pull_a3_synergy() -> None:
    """Backfill SynergyPlayTypes for 2022-23 and 2023-24 (2024-25 already exists)."""
    from src.data.nba_tracking_stats import get_synergy_all_types

    print("\n=== A3: Synergy Backfill (2022-23, 2023-24) ===")
    print("Estimated time: ~4 min/season (10 play types x 2 sides x 1s delay)")

    backfill_seasons = ["2023-24", "2022-23"]

    for season in backfill_seasons:
        for side in ("offensive", "defensive"):
            cache_path = os.path.join(_NBA_DATA, f"synergy_{side}_all_{season}.json")
            if os.path.exists(cache_path):
                with open(cache_path) as f:
                    existing = json.load(f)
                print(f"  {season} {side}: already cached ({len(existing)} records) -- skipping")
                continue

            print(f"  {season} {side}: fetching...", flush=True)
            records = get_synergy_all_types(season=season, offense_defense=side, delay=1.0)
            print(f"  {season} {side}: [OK] {len(records)} records saved")
            time.sleep(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# A4 -- Full Schedule Backfill
# ─────────────────────────────────────────────────────────────────────────────

def pull_a4_schedules() -> None:
    """Pull schedules for all 30 teams x 3 seasons."""
    from src.data.schedule_context import get_season_schedule

    print("\n=== A4: Full Schedule Pull (30 teams x 3 seasons) ===")
    print("Estimated time: ~4 min (90 team-season calls x 0.8s)")

    sched_dir = os.path.join(_NBA_DATA, "schedule")
    os.makedirs(sched_dir, exist_ok=True)

    for season in _SEASONS:
        missing_teams = []
        for team in _ALL_TEAMS:
            # Check if any version exists
            found = any(
                os.path.exists(os.path.join(sched_dir, f"schedule_{team}_{season}{sfx}.json"))
                for sfx in ("_v2", "")
            )
            if not found:
                missing_teams.append(team)

        if not missing_teams:
            print(f"  {season}: all 30 teams cached -- skipping")
            continue

        print(f"  {season}: fetching {len(missing_teams)} missing teams...", flush=True)
        success = 0
        for team in missing_teams:
            try:
                schedule = get_season_schedule(team, season)
                if schedule:
                    success += 1
            except Exception as e:
                print(f"    [WARN] {team} {season}: {e}")
            time.sleep(0.5)  # get_season_schedule has its own delay, this is extra cushion

        print(f"  {season}: [OK] {success}/{len(missing_teams)} teams fetched")


# ─────────────────────────────────────────────────────────────────────────────
# A5 -- Referee Tendencies
# ─────────────────────────────────────────────────────────────────────────────

def pull_a5_referee_tendencies() -> None:
    """Pull referee tendencies for all 3 seasons."""
    from src.data.ref_tracker import scrape_ref_tendencies

    print("\n=== A5: Referee Tendencies ===")
    print("Estimated time: ~10 min (200 games x 3 seasons x API calls)")

    for season in _SEASONS:
        print(f"  {season}: fetching (force=True to accumulate seasons)...", flush=True)
        try:
            result = scrape_ref_tendencies(season=season, max_games=300, force=True)
            print(f"  {season}: [OK] {len(result)} referees in cache")
        except Exception as e:
            print(f"  {season}: [WARN] Error -- {e}")
        time.sleep(1.0)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase A -- Pull all missing NBA data")
    parser.add_argument(
        "--phase",
        choices=["A1", "A2", "A3", "A4", "A5"],
        help="Run only a specific phase (default: all)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Show coverage summary without fetching",
    )
    args = parser.parse_args()

    if args.check:
        check_coverage()
        return

    print("=" * 60)
    print("Phase A -- Complete Data Collection")
    print("=" * 60)
    start = time.time()

    phases = {
        "A1": pull_a1_shot_dashboards,
        "A2": pull_a2_tracking_stats,
        "A3": pull_a3_synergy,
        "A4": pull_a4_schedules,
        "A5": pull_a5_referee_tendencies,
    }

    if args.phase:
        phases[args.phase]()
    else:
        for name, fn in phases.items():
            fn()

    elapsed = time.time() - start
    print(f"\n[OK] Phase A complete in {elapsed/60:.1f} min")
    check_coverage()


if __name__ == "__main__":
    main()
