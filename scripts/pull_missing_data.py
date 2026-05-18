"""
pull_missing_data.py -- Phase A bulk data pull.

Fetches all missing NBA API data for 4 seasons in order of priority:
  A0  Per-player gamelogs -- training labels + live 2025-26 rolling features
  A1  PlayerDashPtShots   -- contested%, pull-up%, defender dist (HIGHEST PRIORITY)
  A2  PlayerTrackingStats -- season-level speed, distance, touches
  A3  SynergyPlayTypes    -- backfill 2022-23 + 2023-24 (2024-25 already exists)
  A4  Full schedules      -- all 30 teams x 4 seasons
  A5  Referee tendencies  -- foul rate, home win%, pace per ref

Usage:
    conda activate basketball_ai
    python scripts/pull_missing_data.py               # all phases
    python scripts/pull_missing_data.py --phase A0    # gamelogs only
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
_SEASONS  = ["2025-26", "2024-25", "2023-24", "2022-23"]

# Seasons to fetch per-player gamelogs for.
# NOTE: 2024-25 has 525 gamelog_{pid}_2024-25.json (short format, uppercase keys)
# but only 1 gamelog_full_{pid}_2024-25.json (full format needed for training).
# Running pull_a0_gamelogs() will fetch the missing gamelog_full_ files for 2024-25.
# 2025-26 = live rolling features for predictions.
# 2022-23, 2023-24 = training labels for prop models.
_GAMELOG_SEASONS = ["2022-23", "2023-24", "2024-25", "2025-26"]
_GAMELOG_MAX_PLAYERS = 600

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

    # A0 -- per-player gamelogs
    import glob as _glob
    print("A0 -- Per-player Gamelogs (PlayerGameLog, gamelog_full format):")
    for s in _GAMELOG_SEASONS:
        full_count  = len(_glob.glob(os.path.join(_NBA_DATA, f"gamelog_full_*_{s}.json")))
        short_count = len(_glob.glob(os.path.join(_NBA_DATA, f"gamelog_{s[:-6]}*_{s}.json")))
        # short files have format gamelog_{pid}_{season}.json (no _full_)
        all_count   = len(_glob.glob(os.path.join(_NBA_DATA, f"gamelog_*_{s}.json")))
        short_only  = all_count - full_count
        if full_count >= 400:
            status = f"[OK] {full_count} full"
        elif short_only > 0:
            status = f"[PARTIAL] {full_count} full + {short_only} short-format (run --phase A0 to fix)"
        else:
            status = f"[MISSING] (run --phase A0)"
        print(f"  {s}: {status}")

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
# A0 -- Per-player Gamelogs
# ─────────────────────────────────────────────────────────────────────────────

def pull_a0_gamelogs() -> None:
    """
    Pull per-player gamelogs for all seasons in _GAMELOG_SEASONS.

    2024-25 has ~525 short-format gamelog_ files (uppercase keys, no game_id)
    but is MISSING the gamelog_full_ files used for training. This function
    will fetch the missing gamelog_full_2024-25 files (per-file skip if exists).
    Saves data/nba/gamelog_full_{player_id}_{season}.json.
    Rate limit: 0.8s delay between calls.
    Cap: _GAMELOG_MAX_PLAYERS players per season from LeagueDashPlayerStats.
    """
    from nba_api.stats.endpoints import playergamelog, leaguedashplayerstats

    print("\n=== A0: Per-player Gamelogs ===")
    print(f"Seasons: {_GAMELOG_SEASONS}")
    print(f"Estimated time: ~{_GAMELOG_MAX_PLAYERS * 0.8 / 60:.0f} min/season "
          f"({_GAMELOG_MAX_PLAYERS} players x 0.8s)")

    os.makedirs(_NBA_DATA, exist_ok=True)

    for season in _GAMELOG_SEASONS:
        print(f"\n  {season}: fetching player list...", flush=True)

        # Get player IDs for this season (cap at _GAMELOG_MAX_PLAYERS)
        try:
            time.sleep(0.6)
            df = leaguedashplayerstats.LeagueDashPlayerStats(
                season=season,
                per_mode_detailed="PerGame",
            ).get_data_frames()[0]
        except Exception as e:
            print(f"  {season}: [ERR] Could not fetch player list — {e}")
            continue

        # Sort by minutes played descending so we prioritize starters
        if "MIN" in df.columns:
            df = df.sort_values("MIN", ascending=False)
        player_ids = df["PLAYER_ID"].tolist()[:_GAMELOG_MAX_PLAYERS]
        print(f"  {season}: {len(player_ids)} players to process", flush=True)

        fetched = 0
        skipped = 0
        errors  = 0

        for pid in player_ids:
            out_path = os.path.join(_NBA_DATA, f"gamelog_full_{pid}_{season}.json")
            if os.path.exists(out_path):
                skipped += 1
                continue

            try:
                time.sleep(0.8)
                gl = playergamelog.PlayerGameLog(
                    player_id=pid,
                    season=season,
                    season_type_all_star="Regular Season",
                ).get_data_frames()[0]
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "rate" in err_str.lower():
                    print(f"    [RATE LIMIT] sleeping 2s and retrying...", flush=True)
                    time.sleep(2.0)
                    try:
                        gl = playergamelog.PlayerGameLog(
                            player_id=pid,
                            season=season,
                            season_type_all_star="Regular Season",
                        ).get_data_frames()[0]
                    except Exception as e2:
                        print(f"    [SKIP] pid={pid}: {e2}")
                        errors += 1
                        continue
                else:
                    print(f"    [SKIP] pid={pid}: {e}")
                    errors += 1
                    continue

            # Normalise column names to lowercase for consistency with existing files
            gl.columns = [c.lower() for c in gl.columns]
            # Add a game_date field in a consistent format (already present as GAME_DATE -> game_date)
            if "game_date" not in gl.columns and "game_date" in gl.columns:
                pass  # already lowercased above
            rows = gl.to_dict(orient="records")

            with open(out_path, "w") as f:
                json.dump(rows, f)
            fetched += 1

            if fetched % 50 == 0:
                print(f"    {fetched} fetched, {skipped} skipped, {errors} errors...", flush=True)

        print(f"  {season}: [OK] fetched={fetched}  skipped={skipped}  errors={errors}")
        time.sleep(1.0)


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
        # get_shot_dashboard_all_players falls back to player_avgs_{season}.json for IDs.
        # If that file is missing (e.g. 2025-26), derive IDs from gamelog_full files instead.
        import glob as _glob, re as _re
        gl_files = _glob.glob(os.path.join(_NBA_DATA, f"gamelog_full_*_{season}.json"))
        extra_ids = [int(_re.search(r"gamelog_full_(\d+)_", f).group(1))
                     for f in gl_files if _re.search(r"gamelog_full_(\d+)_", f)]
        result = get_shot_dashboard_all_players(
            season=season, player_ids=extra_ids or None, delay=0.8
        )
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
    """Fetch SynergyPlayTypes for all seasons in _SEASONS that are missing."""
    from src.data.nba_tracking_stats import get_synergy_all_types

    print("\n=== A3: Synergy (all missing seasons) ===")
    print("Estimated time: ~4 min/season (10 play types x 2 sides x 1s delay)")

    for season in _SEASONS:
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
        choices=["A0", "A1", "A2", "A3", "A4", "A5"],
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
        "A0": pull_a0_gamelogs,
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
