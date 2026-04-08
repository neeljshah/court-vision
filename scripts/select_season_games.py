"""
select_season_games.py -- Pick 2025-26 season games for batch CV processing.

Fetches all completed 2025-26 regular season games from the NBA API,
selects 2 games per team (30 teams x 2 = 60 slots, ~50 unique games),
and writes data/season_2025-26_targets.json.

Usage:
    conda activate basketball_ai
    python scripts/select_season_games.py
    python scripts/select_season_games.py --games-per-team 3
    python scripts/select_season_games.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Set

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
GAMES_DIR = DATA_DIR / "games"
OUTPUT_PATH = DATA_DIR / "season_2025-26_targets.json"
SEASON = "2025-26"
LEAGUE_ID = "00"  # NBA
SEASON_TYPE = "Regular Season"


def _already_processed() -> Set[str]:
    """Return game IDs that already have tracking_data.csv with >10K rows."""
    done: Set[str] = set()
    if not GAMES_DIR.exists():
        return done
    for d in GAMES_DIR.iterdir():
        if not d.is_dir() or d.name.startswith("_"):
            continue
        csv_path = d / "tracking_data.csv"
        if csv_path.exists():
            try:
                with open(csv_path, encoding="utf-8", errors="replace") as f:
                    lines = sum(1 for _ in f)
                if lines > 10_000:
                    done.add(d.name.lstrip("0") or d.name)
                    done.add(d.name)  # zero-padded form too
            except Exception:
                pass
    return done


def _fetch_season_games(retries: int = 3) -> list:
    """Fetch all 2025-26 regular season game records via direct NBA stats API."""
    import urllib.request
    import urllib.parse

    params = urllib.parse.urlencode({
        "LeagueID": LEAGUE_ID,
        "Season": SEASON,
        "SeasonType": SEASON_TYPE,
    })
    url = f"https://stats.nba.com/stats/leaguegamefinder?{params}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nba.com/",
        "Accept": "application/json, text/plain, */*",
        "Host": "stats.nba.com",
        "Origin": "https://www.nba.com",
    }

    for attempt in range(1, retries + 1):
        try:
            time.sleep(0.8)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            rs = data["resultSets"][0]
            cols = rs["headers"]
            rows = rs["rowSet"]
            return [dict(zip(cols, row)) for row in rows]
        except Exception as exc:
            print(f"  [attempt {attempt}/{retries}] NBA API error: {exc}")
            if attempt < retries:
                time.sleep(2.0 * attempt)
    return []


def _select_games(records: list, games_per_team: int) -> List[dict]:
    """
    Pick up to games_per_team games per team from completed games.
    Prefers most-recent games (better YouTube availability).
    Returns deduplicated list of game dicts.
    """
    from collections import defaultdict

    # Each record has one team's perspective; a game appears twice (home + away).
    # Deduplicate by GAME_ID and sort newest-first.
    seen_ids: Set[str] = set()
    unique: List[dict] = []
    for r in records:
        gid = str(r.get("GAME_ID", "")).strip()
        if not gid or gid in seen_ids:
            continue
        # Filter: completed games have WL field set (W or L)
        if not r.get("WL"):
            continue
        seen_ids.add(gid)
        unique.append(r)

    # Sort newest first -- recent games have better YouTube availability
    unique.sort(key=lambda x: x.get("GAME_DATE", ""), reverse=True)

    # Pick up to games_per_team per team
    team_counts: Dict[str, int] = defaultdict(int)
    selected: List[dict] = []
    selected_ids: Set[str] = set()

    for r in unique:
        team_abbr = str(r.get("TEAM_ABBREVIATION", "")).strip()
        gid = str(r.get("GAME_ID", "")).strip()
        if not team_abbr:
            continue
        if team_counts[team_abbr] >= games_per_team:
            continue
        if gid in selected_ids:
            # Game already selected via the opponent's record -- still credit this team
            team_counts[team_abbr] += 1
            continue
        team_counts[team_abbr] += 1
        selected_ids.add(gid)
        selected.append(r)

    return selected


def _build_output(records: list, already_done: Set[str]) -> dict:
    """Build the targets JSON structure."""
    targets = []
    skipped = []

    for r in records:
        gid = str(r.get("GAME_ID", "")).strip()
        padded = gid.zfill(10)  # standard NBA zero-padded form
        if padded in already_done or gid in already_done:
            skipped.append(gid)
            continue
        targets.append({
            "game_id": padded,
            "game_date": r.get("GAME_DATE", ""),
            "matchup": r.get("MATCHUP", ""),
            "team_abbreviation": r.get("TEAM_ABBREVIATION", ""),
            "season": SEASON,
        })

    return {
        "season": SEASON,
        "generated": time.strftime("%Y-%m-%d"),
        "total_targets": len(targets),
        "skipped_already_processed": len(skipped),
        "targets": targets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Select 2025-26 season games for batch processing")
    parser.add_argument("--games-per-team", type=int, default=2,
                        help="Games per team to select (default: 2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print selection without writing JSON")
    args = parser.parse_args()

    print(f"=== select_season_games.py -- {SEASON} ===")

    already_done = _already_processed()
    print(f"Already processed: {len(already_done)} game dirs with >10K tracking rows")

    print(f"Fetching {SEASON} game log from NBA API...")
    raw_records = _fetch_season_games()

    if not raw_records:
        print("ERROR: No games returned from NBA API. Check network or try again later.")
        print("Writing empty targets file so batch_season.py can still run safely.")
        output = {
            "season": SEASON,
            "generated": time.strftime("%Y-%m-%d"),
            "total_targets": 0,
            "skipped_already_processed": 0,
            "targets": [],
            "error": "NBA API returned no data -- re-run when network is available",
        }
    else:
        print(f"Raw records: {len(raw_records)} game-team rows")
        selected = _select_games(raw_records, games_per_team=args.games_per_team)
        print(f"Selected: {len(selected)} unique games ({args.games_per_team}/team target)")
        output = _build_output(selected, already_done)
        print(f"Targets after dedup/skip: {output['total_targets']} games")
        print(f"Skipped (already processed): {output['skipped_already_processed']}")

    if args.dry_run:
        print("\n[dry-run] Output preview:")
        print(json.dumps(output, indent=2)[:2000])
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {OUTPUT_PATH}")
    if output.get("targets"):
        print("First 5 targets:")
        for t in output["targets"][:5]:
            print(f"  {t['game_id']}  {t['game_date']}  {t['matchup']}")


if __name__ == "__main__":
    main()
