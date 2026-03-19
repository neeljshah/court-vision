"""
shot_chart_scraper.py — Scrape ShotChartDetail per player for NBA seasons.

Caches to data/nba/shotchart_{player_id}_{season}.json.
Columns: player_id, game_id, period, action_type, shot_zone_basic,
         shot_zone_area, shot_distance, loc_x, loc_y, shot_made_flag,
         game_date, htm, vtm, minutes_remaining, seconds_remaining

Usage:
    python src/data/shot_chart_scraper.py --season 2024-25 --max 50
    python src/data/shot_chart_scraper.py --all-seasons --max 200
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_COVERAGE  = os.path.join(_NBA_CACHE, "scraper_coverage.json")
_DELAY     = 0.8        # seconds between NBA API calls
_TTL_HOURS = 24         # cache freshness


# ── helpers ───────────────────────────────────────────────────────────────────

def _cache_path(player_id: int, season: str) -> str:
    return os.path.join(_NBA_CACHE, f"shotchart_{player_id}_{season}.json")


def _is_fresh(path: str) -> bool:
    return (
        os.path.exists(path)
        and (time.time() - os.path.getmtime(path)) < _TTL_HOURS * 3600
    )


def _load_coverage() -> dict:
    if os.path.exists(_COVERAGE):
        try:
            with open(_COVERAGE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_coverage(cov: dict) -> None:
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(_COVERAGE, "w") as f:
        json.dump(cov, f, indent=2)


def _player_ids_from_coverage() -> List[tuple]:
    """Return list of (player_id, player_name) from scraper_coverage.json."""
    cov = _load_coverage()
    result = []
    for pid_str, info in cov.items():
        try:
            result.append((int(pid_str), info.get("name", str(pid_str))))
        except (ValueError, TypeError):
            pass
    return result


# ── core scraper ──────────────────────────────────────────────────────────────

def scrape_player_shotchart(
    player_id: int,
    season: str = "2024-25",
    force: bool = False,
) -> Optional[List[dict]]:
    """
    Fetch ShotChartDetail for one player/season. Cached.

    Returns list of shot dicts, or None on failure.
    """
    path = _cache_path(player_id, season)
    if not force and _is_fresh(path):
        with open(path) as f:
            return json.load(f)

    try:
        from nba_api.stats.endpoints import shotchartdetail
        time.sleep(_DELAY)
        resp = shotchartdetail.ShotChartDetail(
            team_id=0,
            player_id=player_id,
            season_nullable=season,
            season_type_all_star="Regular Season",
            context_measure_simple="FGA",
        )
        dfs = resp.get_data_frames()
        if not dfs or len(dfs[0]) == 0:
            # Player had no FGA — save empty list so we don't re-fetch
            os.makedirs(_NBA_CACHE, exist_ok=True)
            with open(path, "w") as f:
                json.dump([], f)
            return []

        df = dfs[0]
        keep = [
            "PLAYER_ID", "GAME_ID", "PERIOD", "ACTION_TYPE",
            "SHOT_ZONE_BASIC", "SHOT_ZONE_AREA", "SHOT_DISTANCE",
            "LOC_X", "LOC_Y", "SHOT_MADE_FLAG",
            "GAME_DATE", "HTM", "VTM", "MINUTES_REMAINING", "SECONDS_REMAINING",
        ]
        keep_cols = [c for c in keep if c in df.columns]
        rows = df[keep_cols].rename(columns=str.lower).to_dict("records")

        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(path, "w") as f:
            json.dump(rows, f)
        return rows

    except Exception as e:
        print(f"  [shotchart] player {player_id} {season} failed: {e}")
        return None


def scrape_all_players(
    season: str = "2024-25",
    max_players: int = 999,
    force: bool = False,
) -> dict:
    """
    Scrape shot charts for all players in scraper_coverage.json.

    Args:
        season:      NBA season string (e.g. "2024-25").
        max_players: Maximum number of players to scrape this run.
        force:       Re-fetch even if cache is fresh.

    Returns:
        {"total": int, "scraped": int, "skipped": int, "failed": int}
    """
    players = _player_ids_from_coverage()
    if not players:
        print("[shotchart] No player IDs found in scraper_coverage.json")
        return {"total": 0, "scraped": 0, "skipped": 0, "failed": 0}

    scraped = skipped = failed = 0
    processed = 0

    for pid, name in players:
        if processed >= max_players:
            break

        path = _cache_path(pid, season)
        if not force and _is_fresh(path):
            skipped += 1
            continue

        rows = scrape_player_shotchart(pid, season, force=force)
        if rows is None:
            failed += 1
        else:
            scraped += 1
            n = len(rows)
            print(f"  [shotchart] {name} ({pid}) {season}: {n} shots")
        processed += 1

    total = len(players)
    print(f"\n[shotchart] Done — {season}: {scraped} scraped, {skipped} cached, {failed} failed / {total} total")
    return {"total": total, "scraped": scraped, "skipped": skipped, "failed": failed}


def merge_all_shotcharts(season: str = "2024-25") -> List[dict]:
    """
    Load and merge all cached shot charts for a season into one list.

    Returns list of shot dicts with player_id included.
    """
    import glob
    pattern = os.path.join(_NBA_CACHE, f"shotchart_*_{season}.json")
    files = glob.glob(pattern)
    all_shots: List[dict] = []
    for fp in files:
        try:
            with open(fp) as f:
                shots = json.load(f)
            all_shots.extend(shots)
        except Exception:
            pass
    print(f"[shotchart] Merged {len(all_shots)} shots from {len(files)} files ({season})")
    return all_shots


def get_player_shotchart(player_id: int, season: str = "2024-25") -> List[dict]:
    """
    Return cached shot chart for a player, fetching if needed.

    Returns list of shot dicts (empty if player had no shots).
    """
    shots = scrape_player_shotchart(player_id, season)
    return shots or []


def coverage_report(seasons: List[str] = None) -> dict:
    """
    Report shot chart coverage across seasons.

    Returns dict: {season: {"players_with_data": int, "total_shots": int}}
    """
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]
    import glob
    report = {}
    for season in seasons:
        pattern = os.path.join(_NBA_CACHE, f"shotchart_*_{season}.json")
        files = glob.glob(pattern)
        total_shots = 0
        players_with_data = 0
        for fp in files:
            try:
                with open(fp) as f:
                    shots = json.load(f)
                if shots:
                    players_with_data += 1
                    total_shots += len(shots)
            except Exception:
                pass
        report[season] = {"players_with_data": players_with_data, "total_shots": total_shots}
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="NBA Shot Chart Scraper")
    ap.add_argument("--season",      default="2024-25", help="NBA season string")
    ap.add_argument("--all-seasons", action="store_true", help="Scrape 2022-23, 2023-24, 2024-25")
    ap.add_argument("--max",         type=int, default=999, help="Max players per season")
    ap.add_argument("--player",      type=int, help="Single player_id to scrape")
    ap.add_argument("--force",       action="store_true", help="Re-fetch even if cached")
    ap.add_argument("--report",      action="store_true", help="Show coverage report")
    ap.add_argument("--merge",       action="store_true", help="Merge all shots for season")
    args = ap.parse_args()

    if args.report:
        rep = coverage_report()
        for s, info in rep.items():
            print(f"  {s}: {info['players_with_data']} players, {info['total_shots']:,} shots")

    elif args.player:
        shots = scrape_player_shotchart(args.player, args.season, force=args.force)
        print(f"Player {args.player}: {len(shots) if shots else 0} shots")

    elif args.merge:
        shots = merge_all_shotcharts(args.season)
        out = os.path.join(_NBA_CACHE, f"shotcharts_all_{args.season}.json")
        with open(out, "w") as f:
            json.dump(shots, f)
        print(f"Saved {len(shots)} shots → {out}")

    elif args.all_seasons:
        for season in ["2022-23", "2023-24", "2024-25"]:
            scrape_all_players(season, max_players=args.max, force=args.force)

    else:
        scrape_all_players(args.season, max_players=args.max, force=args.force)
