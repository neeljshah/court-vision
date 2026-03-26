"""
fetch_games.py — Auto-download NBA game footage via yt-dlp, no OBS needed.

Pulls recent games from the NBA schedule API, searches YouTube for each
game's full broadcast, downloads a segment (default: first 15 min of Q1),
and saves to data/videos/full_games/{game_id}.mp4.

Usage:
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    # Download 5 recent games (default)
    python scripts/fetch_games.py

    # Download 10 games, full game video (long)
    python scripts/fetch_games.py --count 10 --full

    # Download specific date range
    python scripts/fetch_games.py --from 2025-03-01 --to 2025-03-20

    # Download and immediately process with run_phase_g
    python scripts/fetch_games.py --count 5 --process
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

VIDEOS_DIR = PROJECT_DIR / "data" / "videos" / "full_games"

# YouTube search templates — ordered by reliability for full broadcast footage
# These target extended highlights and full game replays (8-15 min segments)
_YT_SEARCH_TEMPLATES = [
    "{away} vs {home} {date_str} full game highlights NBA",
    "NBA {away} {home} {month_year} full game replay",
    "{away} {home} NBA {season} full quarter broadcast",
]

# Team name abbreviation → full name map for search
_TEAM_NAMES = {
    "ATL": "Hawks",  "BOS": "Celtics", "BKN": "Nets",   "CHA": "Hornets",
    "CHI": "Bulls",  "CLE": "Cavaliers","DAL": "Mavericks","DEN": "Nuggets",
    "DET": "Pistons","GSW": "Warriors", "HOU": "Rockets", "IND": "Pacers",
    "LAC": "Clippers","LAL": "Lakers",  "MEM": "Grizzlies","MIA": "Heat",
    "MIL": "Bucks",  "MIN": "Timberwolves","NOP": "Pelicans","NYK": "Knicks",
    "OKC": "Thunder","ORL": "Magic",   "PHI": "76ers",   "PHX": "Suns",
    "POR": "Trail Blazers","SAC": "Kings","SAS": "Spurs", "TOR": "Raptors",
    "UTA": "Jazz",   "WAS": "Wizards",
}

# Channels known to post full/extended NBA game content
# We prefer longer videos (>600s) to ensure enough continuous gameplay for the tracker
_PREFERRED_CHANNELS = [
    "NBA",
    "ESPN",
    "NBA Full Games",
]


def _team_full(abbrev: str) -> str:
    return _TEAM_NAMES.get(abbrev.upper(), abbrev)


def _get_recent_games(count: int, from_date: Optional[str],
                      to_date: Optional[str]) -> list[dict]:
    """Fetch recent completed games from nba_api."""
    try:
        from nba_api.stats.endpoints import LeagueGameLog
        from nba_api.stats.static import teams as nba_teams
    except ImportError:
        print("[fetch_games] nba_api not installed. Falling back to manual list.")
        return []

    season = "2024-25"
    print(f"Fetching game log for {season}...")
    try:
        log = LeagueGameLog(season=season, season_type_all_star="Regular Season")
        df = log.get_data_frames()[0]
    except Exception as e:
        print(f"[fetch_games] NBA API error: {e}")
        return []

    # Filter columns
    df = df[["GAME_ID", "GAME_DATE", "TEAM_ABBREVIATION", "MATCHUP"]].copy()
    df["GAME_DATE"] = df["GAME_DATE"].str[:10]  # YYYY-MM-DD

    if from_date:
        df = df[df["GAME_DATE"] >= from_date]
    if to_date:
        df = df[df["GAME_DATE"] <= to_date]

    # Get unique games (each game appears twice — once per team)
    seen = set()
    games = []
    for _, row in df.iterrows():
        gid = row["GAME_ID"]
        if gid in seen:
            continue
        seen.add(gid)
        matchup = row["MATCHUP"]  # e.g. "LAL vs. GSW" or "LAL @ GSW"
        parts = matchup.replace("vs.", "vs").replace("@", "vs").split("vs")
        away = parts[0].strip()
        home = parts[1].strip() if len(parts) > 1 else parts[0].strip()
        games.append({
            "game_id":   gid,
            "date":      row["GAME_DATE"],
            "away":      away,
            "home":      home,
        })
        if len(games) >= count * 3:  # grab extra in case some downloads fail
            break

    # Sort newest first so we get recent broadcast-quality footage
    games.sort(key=lambda g: g["date"], reverse=True)
    return games[:count * 2]


def _search_and_download(game: dict, out_path: Path,
                         segment_seconds: int) -> bool:
    """Search YouTube for the game and download to out_path. Returns True on success."""
    date_obj = datetime.strptime(game["date"], "%Y-%m-%d")
    date_str  = date_obj.strftime("%B %d %Y")
    month_year = date_obj.strftime("%B %Y")
    away_full = _team_full(game["away"])
    home_full = _team_full(game["home"])

    # Try each search template
    for tmpl in _YT_SEARCH_TEMPLATES:
        query = tmpl.format(
            away=away_full, home=home_full,
            date_str=date_str, month_year=month_year,
            season="2024-25",
        )
        search_url = f"ytsearch5:{query}"  # top 5 results

        print(f"  Searching: {query}")

        # yt-dlp: search, pick longest result ≥ segment_seconds, download segment
        cookies_file = PROJECT_DIR / "data" / "videos" / "youtube_cookies.txt"
        base_cmd = [
            "yt-dlp",
            "--no-playlist",
            "--format", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
            "--merge-output-format", "mp4",
            "--quiet",
            "--no-warnings",
        ]
        if cookies_file.exists():
            base_cmd += ["--cookies", str(cookies_file)]

        # First pass: get video info only (no download) to pick best result
        info_cmd = base_cmd + [
            "--dump-json",
            "--flat-playlist",
            search_url,
        ]
        try:
            info_proc = subprocess.run(
                info_cmd, capture_output=True, text=True, timeout=30
            )
            candidates = []
            for line in info_proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    info = json.loads(line)
                    dur = info.get("duration") or 0
                    vid_id = info.get("id") or info.get("url", "")
                    title = info.get("title", "")
                    candidates.append((dur, vid_id, title))
                except json.JSONDecodeError:
                    continue

            # Prefer longest video (most likely full game / extended highlights)
            # but reject anything under 5 minutes (short clip) or over 3 hours (menu/playlist)
            candidates = [c for c in candidates if 300 <= c[0] <= 10800]
            if not candidates:
                continue
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_dur, best_id, best_title = candidates[0]

            print(f"  Found: {best_title[:60]} ({best_dur}s)")

            # Download — if segment_seconds is set and video > 2x that, download section only
            dl_cmd = base_cmd + [
                "--output", str(out_path),
            ]
            if segment_seconds and best_dur > segment_seconds * 2:
                # Skip intro (~60s) then grab segment_seconds of live play
                start_sec = 60
                dl_cmd += [
                    "--download-sections", f"*{start_sec}-{start_sec + segment_seconds}",
                    "--force-keyframes-at-cuts",
                ]

            dl_cmd.append(f"https://www.youtube.com/watch?v={best_id}")

            print(f"  Downloading {'segment ' if segment_seconds else 'full '}"
                  f"from {best_id} ...")
            dl_proc = subprocess.run(
                dl_cmd, capture_output=True, text=True, timeout=300
            )
            if dl_proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1_000_000:
                print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
                return True
            else:
                if dl_proc.stderr:
                    print(f"  yt-dlp error: {dl_proc.stderr[-200:]}")

        except subprocess.TimeoutExpired:
            print("  Search timed out, trying next template...")
            continue
        except Exception as e:
            print(f"  Error: {e}")
            continue

    return False


def main():
    ap = argparse.ArgumentParser(description="Download NBA games for tracker benchmarking")
    ap.add_argument("--count",    type=int, default=5,
                    help="Number of games to download (default 5)")
    ap.add_argument("--from",     dest="from_date", default=None,
                    help="Start date YYYY-MM-DD (default: 30 days ago)")
    ap.add_argument("--to",       dest="to_date",   default=None,
                    help="End date YYYY-MM-DD (default: today)")
    ap.add_argument("--full",     action="store_true",
                    help="Download full game instead of first-quarter segment")
    ap.add_argument("--segment",  type=int, default=900,
                    help="Seconds to download per game in segment mode (default 900 = 15 min)")
    ap.add_argument("--process",  action="store_true",
                    help="Run run_phase_g.py on downloaded games after download")
    args = ap.parse_args()

    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    from_date = args.from_date or (
        datetime.now() - timedelta(days=30)
    ).strftime("%Y-%m-%d")
    to_date   = args.to_date or datetime.now().strftime("%Y-%m-%d")

    print(f"Fetching {args.count} games ({from_date} → {to_date}) ...")
    games = _get_recent_games(args.count, from_date, to_date)

    if not games:
        print("No games returned from NBA API. Check your internet connection.")
        return

    segment_s = 0 if args.full else args.segment
    downloaded = []

    for game in games:
        if len(downloaded) >= args.count:
            break
        gid  = game["game_id"]
        out  = VIDEOS_DIR / f"{gid}.mp4"
        if out.exists() and out.stat().st_size > 500_000:
            print(f"[skip] {gid} already downloaded")
            downloaded.append(gid)
            continue

        print(f"\n── {game['away']} @ {game['home']}  {game['date']}  ({gid})")
        ok = _search_and_download(game, out, segment_s)
        if ok:
            downloaded.append(gid)
        else:
            print(f"  [WARN] Could not download {gid} — skipping")
        time.sleep(2)  # polite rate limiting

    print(f"\nDownloaded {len(downloaded)}/{args.count} games:")
    for gid in downloaded:
        p = VIDEOS_DIR / f"{gid}.mp4"
        mb = p.stat().st_size // 1024 // 1024 if p.exists() else 0
        print(f"  {gid}  ({mb} MB)")

    if args.process and downloaded:
        print("\nRunning run_phase_g.py on downloaded games ...")
        subprocess.run(
            [sys.executable, str(PROJECT_DIR / "scripts" / "run_phase_g.py"),
             "--game-ids", *downloaded],
            cwd=str(PROJECT_DIR),
        )


if __name__ == "__main__":
    main()
