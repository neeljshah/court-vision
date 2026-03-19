"""
pbp_scraper.py — Scrape PlayByPlayV2 for all games and derive per-player clutch stats.

Caches to data/nba/pbp_{game_id}.json.
Derives: clutch_fg_pct, clutch_pts, foul_drawn_rate per player.
Saves aggregate to data/nba/player_clutch_{season}.json.

Usage:
    python src/data/pbp_scraper.py --season 2024-25 --max 50
    python src/data/pbp_scraper.py --season 2024-25 --derive-clutch
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_DELAY     = 0.8
_TTL_HOURS = 168  # PBP doesn't change — 7-day TTL

# Clutch = Q4 or OT with margin ≤5 points
_CLUTCH_PERIODS = {4, 5, 6, 7}  # Q4 + OT periods
_CLUTCH_MARGIN  = 5


# ── helpers ───────────────────────────────────────────────────────────────────

def _pbp_path(game_id: str) -> str:
    return os.path.join(_NBA_CACHE, f"pbp_{game_id}.json")


def _is_fresh(path: str) -> bool:
    return (
        os.path.exists(path)
        and (time.time() - os.path.getmtime(path)) < _TTL_HOURS * 3600
    )


def _load_game_ids(season: str) -> List[str]:
    """Load game IDs from season_games cache."""
    path = os.path.join(_NBA_CACHE, f"season_games_{season}.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
        rows = data.get("rows", data) if isinstance(data, dict) else data
        return [str(r["game_id"]) for r in rows if r.get("game_id")]
    except Exception as e:
        print(f"  [pbp] Could not load game IDs: {e}")
        return []


# ── core scraper ──────────────────────────────────────────────────────────────

_V3_ACTION_TO_EVT = {
    "Made Shot":   1,
    "Missed Shot": 2,
    "Free Throw":  3,
    "Foul":        6,
}


def _normalize_v3_rows(df: "pd.DataFrame") -> List[dict]:
    """Convert PlayByPlayV3 DataFrame to V2-compatible row dicts."""
    # Forward-fill scoreHome / scoreAway so every row has the current score.
    df = df.copy()
    df["scoreHome"] = df["scoreHome"].replace("", None)
    df["scoreAway"] = df["scoreAway"].replace("", None)
    df["scoreHome"] = df["scoreHome"].ffill()
    df["scoreAway"] = df["scoreAway"].ffill()

    rows = []
    for _, r in df.iterrows():
        evt = _V3_ACTION_TO_EVT.get(str(r.get("actionType", "")), 0)
        # Compute score margin (signed: home - away)
        try:
            margin = int(r["scoreHome"]) - int(r["scoreAway"])
        except (TypeError, ValueError):
            margin = None

        desc = str(r.get("description", ""))
        rows.append({
            "GAME_ID":          str(r.get("gameId", "")),
            "EVENTNUM":         int(r.get("actionNumber", 0)),
            "EVENTMSGTYPE":     evt,
            "PERIOD":           int(r.get("period", 0)),
            "HOMEDESCRIPTION":  desc,
            "VISITORDESCRIPTION": "",
            "SCOREMARGIN":      str(margin) if margin is not None else "",
            "PLAYER1_ID":       str(r.get("personId", "0")),
            "PLAYER1_NAME":     str(r.get("playerName", "")),
            "PLAYER1_TEAM_ID":  str(r.get("teamId", "")),
            "PLAYER2_ID":       "0",   # V3 has no direct fouled-player field
            "PLAYER2_NAME":     "",
        })
    return rows


def scrape_game_pbp(game_id: str, force: bool = False) -> Optional[List[dict]]:
    """
    Fetch PlayByPlayV3 for a single game. Cached.

    Returns list of play dicts (V2-compatible schema) or None on failure.
    """
    path = _pbp_path(game_id)
    if not force and _is_fresh(path):
        with open(path) as f:
            return json.load(f)

    try:
        from nba_api.stats.endpoints import playbyplayv3
        time.sleep(_DELAY)
        df = playbyplayv3.PlayByPlayV3(game_id=game_id).get_data_frames()[0]

        if len(df) == 0:
            os.makedirs(_NBA_CACHE, exist_ok=True)
            with open(path, "w") as f:
                json.dump([], f)
            return []

        rows = _normalize_v3_rows(df)
        os.makedirs(_NBA_CACHE, exist_ok=True)
        with open(path, "w") as f:
            json.dump(rows, f)
        return rows

    except Exception as e:
        print(f"  [pbp] game {game_id} failed: {e}")
        return None


def scrape_season_pbp(
    season: str = "2024-25",
    max_games: int = 999,
    force: bool = False,
) -> dict:
    """
    Scrape PBP for all games in a season.

    Returns {"total": int, "scraped": int, "skipped": int, "failed": int}
    """
    game_ids = _load_game_ids(season)
    if not game_ids:
        print(f"[pbp] No game IDs found for {season}")
        return {"total": 0, "scraped": 0, "skipped": 0, "failed": 0}

    scraped = skipped = failed = processed = 0

    for gid in game_ids:
        if processed >= max_games:
            break

        path = _pbp_path(gid)
        if not force and _is_fresh(path):
            skipped += 1
            continue

        rows = scrape_game_pbp(gid, force=force)
        if rows is None:
            failed += 1
        else:
            scraped += 1
            if scraped % 50 == 0:
                print(f"  [pbp] {season}: {scraped} scraped so far...")
        processed += 1

    total = len(game_ids)
    cached = sum(1 for gid in game_ids if os.path.exists(_pbp_path(gid)))
    print(f"\n[pbp] {season}: {scraped} new, {skipped} cached, {failed} failed | {cached}/{total} total cached")
    return {"total": total, "scraped": scraped, "skipped": skipped, "failed": failed}


# ── clutch stats derivation ───────────────────────────────────────────────────

def _is_clutch(row: dict) -> bool:
    """Return True if this play occurred in a clutch situation."""
    period = int(row.get("PERIOD", 0))
    if period not in _CLUTCH_PERIODS:
        return False
    margin_str = str(row.get("SCOREMARGIN", "")).strip()
    if not margin_str or margin_str.upper() in ("", "TIE", "NONE", "NULL"):
        return True  # tied = clutch
    try:
        return abs(int(margin_str)) <= _CLUTCH_MARGIN
    except (ValueError, TypeError):
        return False


# NBA PlayByPlay EVENTMSGTYPE codes
_EVT_MADE_SHOT   = 1
_EVT_MISSED_SHOT = 2
_EVT_FREE_THROW  = 3
_EVT_FOUL        = 6


def derive_clutch_stats(season: str = "2024-25") -> dict:
    """
    Derive per-player clutch stats from all cached PBP files for a season.

    Clutch = Q4/OT with margin ≤5.
    Computed stats:
        clutch_fga, clutch_fgm, clutch_fg_pct, clutch_pts,
        clutch_fta, clutch_ftm, foul_drawn_rate (fouls drawn per game)

    Saves to data/nba/player_clutch_{season}.json.
    Returns the stats dict {player_id: {stats}}.
    """
    import glob
    pattern = os.path.join(_NBA_CACHE, f"pbp_*.json")
    # Filter to games in this season by checking game IDs
    game_ids_in_season = set(_load_game_ids(season))

    stats: Dict[str, dict] = defaultdict(lambda: {
        "clutch_fga": 0, "clutch_fgm": 0,
        "clutch_fta": 0, "clutch_ftm": 0,
        "clutch_pts": 0,
        "fouls_drawn": 0, "games_with_clutch": 0,
    })

    games_processed = 0
    for fp in sorted(glob.glob(pattern)):
        game_id = os.path.basename(fp).replace("pbp_", "").replace(".json", "")
        if game_ids_in_season and game_id not in game_ids_in_season:
            continue
        try:
            with open(fp) as f:
                plays = json.load(f)
        except Exception:
            continue

        if not plays:
            continue

        games_processed += 1
        players_seen_clutch = set()

        for play in plays:
            if not _is_clutch(play):
                continue
            evt = int(play.get("EVENTMSGTYPE", 0))
            pid = str(play.get("PLAYER1_ID", ""))
            if not pid or pid == "0":
                continue

            players_seen_clutch.add(pid)

            if evt == _EVT_MADE_SHOT:
                stats[pid]["clutch_fgm"] += 1
                stats[pid]["clutch_fga"] += 1
                # Estimate pts: check description for 3pt
                desc = str(play.get("HOMEDESCRIPTION", "") or play.get("VISITORDESCRIPTION", "")).upper()
                stats[pid]["clutch_pts"] += 3 if "3PT" in desc else 2

            elif evt == _EVT_MISSED_SHOT:
                stats[pid]["clutch_fga"] += 1

            elif evt == _EVT_FREE_THROW:
                desc = str(play.get("HOMEDESCRIPTION", "") or play.get("VISITORDESCRIPTION", "")).upper()
                stats[pid]["clutch_fta"] += 1
                if "MISS" not in desc:
                    stats[pid]["clutch_ftm"] += 1
                    stats[pid]["clutch_pts"] += 1

            elif evt == _EVT_FOUL:
                # PLAYER2 draws the foul
                pid2 = str(play.get("PLAYER2_ID", ""))
                if pid2 and pid2 != "0":
                    stats[pid2]["fouls_drawn"] += 1

        for pid in players_seen_clutch:
            stats[pid]["games_with_clutch"] += 1

    # Derive rates
    result = {}
    for pid, s in stats.items():
        fga = s["clutch_fga"]
        fta = s["clutch_fta"]
        gpg = max(s["games_with_clutch"], 1)
        result[pid] = {
            "clutch_fga":       fga,
            "clutch_fgm":       s["clutch_fgm"],
            "clutch_fg_pct":    round(s["clutch_fgm"] / fga, 3) if fga > 0 else 0.0,
            "clutch_pts":       s["clutch_pts"],
            "clutch_pts_pg":    round(s["clutch_pts"] / gpg, 2),
            "clutch_fta":       fta,
            "clutch_ftm":       s["clutch_ftm"],
            "foul_drawn_rate":  round(s["fouls_drawn"] / gpg, 2),
            "games_with_clutch": s["games_with_clutch"],
        }

    out_path = os.path.join(_NBA_CACHE, f"player_clutch_{season}.json")
    os.makedirs(_NBA_CACHE, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"[pbp] Clutch stats: {len(result)} players, {games_processed} games → {out_path}")
    return result


def coverage_report(seasons: List[str] = None) -> dict:
    """Return PBP coverage stats per season."""
    if seasons is None:
        seasons = ["2022-23", "2023-24", "2024-25"]
    report = {}
    for season in seasons:
        game_ids = _load_game_ids(season)
        cached = sum(1 for gid in game_ids if os.path.exists(_pbp_path(gid)))
        report[season] = {"total_games": len(game_ids), "cached_games": cached,
                          "pct": round(cached / len(game_ids) * 100, 1) if game_ids else 0}
    return report


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="NBA PBP Scraper")
    ap.add_argument("--season",        default="2024-25")
    ap.add_argument("--all-seasons",   action="store_true")
    ap.add_argument("--max",           type=int, default=999, help="Max games to scrape")
    ap.add_argument("--game-id",       type=str, help="Single game ID to scrape")
    ap.add_argument("--force",         action="store_true")
    ap.add_argument("--derive-clutch", action="store_true", help="Derive clutch stats from cached PBP")
    ap.add_argument("--report",        action="store_true")
    args = ap.parse_args()

    if args.report:
        rep = coverage_report()
        for s, info in rep.items():
            print(f"  {s}: {info['cached_games']}/{info['total_games']} games ({info['pct']}%)")

    elif args.game_id:
        plays = scrape_game_pbp(args.game_id, force=args.force)
        print(f"Game {args.game_id}: {len(plays) if plays else 0} plays")

    elif args.derive_clutch:
        season = args.season
        stats = derive_clutch_stats(season)
        print(f"Derived clutch stats for {len(stats)} players")

    elif args.all_seasons:
        for season in ["2022-23", "2023-24", "2024-25"]:
            scrape_season_pbp(season, max_games=args.max, force=args.force)

    else:
        scrape_season_pbp(args.season, max_games=args.max, force=args.force)
