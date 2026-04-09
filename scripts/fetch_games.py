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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Optional

_print_lock = Lock()

PROJECT_DIR = Path(__file__).resolve().parent.parent


def _current_nba_season() -> str:
    """Return current NBA season string (e.g. '2025-26')."""
    from datetime import date as _d
    today = _d.today()
    start_year = today.year if today.month >= 10 else today.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"
sys.path.insert(0, str(PROJECT_DIR))

VIDEOS_DIR = PROJECT_DIR / "data" / "videos" / "full_games"

# YouTube search templates — ordered to find actual full-game broadcast replays.
# Full games (90-160 min) preferred; highlights (10-20 min) accepted as fallback.
# ytsearch10 (not 5) to widen net — NBA full games get DMCA'd fast so most
# results are re-uploads on smaller channels with different naming patterns.
_YT_SEARCH_TEMPLATES = [
    # Primary: exact matchup + date searches
    "NBA full game {away} vs {home} {date_str} replay",
    "{away} vs {home} {date_str} NBA full game",
    "NBA full game {month_year} {away} {home}",
    "{away} vs {home} NBA full game replay {month_year}",
    # Broader: team-name variants (re-uploaders often use city not team)
    "{away_city} vs {home_city} NBA full game {date_str}",
    "{away} {home} full game replay {season}",
    # Channel-specific patterns (common NBA re-upload channels)
    "NBA full game replay {away} {home} {season}",
]

# Fallback: highlights templates (used only when no full game found)
_YT_HIGHLIGHTS_TEMPLATES = [
    "{away} vs {home} {date_str} NBA full highlights",
    "{away} vs {home} highlights {date_str}",
    "NBA {away} vs {home} {month_year} highlights extended",
    "{away} vs {home} extended highlights {season}",
]

# Dailymotion search templates — NBA full games persist longer on DM than YouTube
_DM_SEARCH_TEMPLATES = [
    "{away} vs {home} NBA full game {date_str}",
    "{away} {home} full game {month_year}",
    "NBA {away} vs {home} full game replay",
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

# City names for broader search queries (re-uploaders often use city not team name)
_TEAM_CITIES = {
    "ATL": "Atlanta",  "BOS": "Boston",   "BKN": "Brooklyn", "CHA": "Charlotte",
    "CHI": "Chicago",  "CLE": "Cleveland","DAL": "Dallas",   "DEN": "Denver",
    "DET": "Detroit",  "GSW": "Golden State","HOU": "Houston","IND": "Indiana",
    "LAC": "LA Clippers","LAL": "LA Lakers","MEM": "Memphis", "MIA": "Miami",
    "MIL": "Milwaukee","MIN": "Minnesota","NOP": "New Orleans","NYK": "New York",
    "OKC": "Oklahoma City","ORL": "Orlando","PHI": "Philadelphia","PHX": "Phoenix",
    "POR": "Portland", "SAC": "Sacramento","SAS": "San Antonio","TOR": "Toronto",
    "UTA": "Utah",     "WAS": "Washington",
}

# Channels known to post full/extended NBA game content
_PREFERRED_CHANNELS = [
    "NBA",
    "ESPN",
    "NBA Full Games",
]


def _team_full(abbrev: str) -> str:
    return _TEAM_NAMES.get(abbrev.upper(), abbrev)


def _team_city(abbrev: str) -> str:
    return _TEAM_CITIES.get(abbrev.upper(), abbrev)


def _get_recent_games(count: int, from_date: Optional[str],
                      to_date: Optional[str]) -> list[dict]:
    """Fetch recent completed games from nba_api."""
    try:
        from nba_api.stats.endpoints import LeagueGameLog
        from nba_api.stats.static import teams as nba_teams
    except ImportError:
        print("[fetch_games] nba_api not installed. Falling back to manual list.")
        return []

    season = _current_nba_season()
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


def _build_base_cmd() -> list:
    """Build the base yt-dlp command with common options."""
    cookies_file = PROJECT_DIR / "data" / "videos" / "youtube_cookies.txt"
    # Use python3.11 -m yt_dlp when available (has curl_cffi impersonation support)
    import shutil
    if shutil.which("python3.11"):
        base_cmd = ["python3.11", "-m", "yt_dlp"]
    else:
        base_cmd = ["yt-dlp"]
    base_cmd += [
        "--no-playlist",
        # Force H.264 (avc1) — opencv-python's bundled ffmpeg cannot decode AV1
        # on Linux without libdav1d, and RunPod containers block NVDEC av1_cuvid.
        # Every fallback explicitly rejects av01/vp9 so we never redownload-transcode.
        "--format", "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/bestvideo[height<=720][vcodec!*=av01][vcodec!*=vp9][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][vcodec!*=av01][vcodec!*=vp9][ext=mp4]/best[height<=720][vcodec!*=av01][vcodec!*=vp9]",
        "--merge-output-format", "mp4",
        "--quiet",
        "--no-warnings",
        "--sleep-requests", "0",
        "--no-abort-on-error",
    ]
    # Point yt-dlp at conda env's ffmpeg (not on system PATH)
    _ffmpeg_dir = PROJECT_DIR.parent / "anaconda3" / "envs" / "basketball_ai" / "Library" / "bin"
    if (_ffmpeg_dir / "ffmpeg.exe").exists():
        base_cmd += ["--ffmpeg-location", str(_ffmpeg_dir)]
    if cookies_file.exists():
        try:
            content = cookies_file.read_text(encoding="utf-8", errors="ignore")
            has_auth = any(k in content for k in ("SID\t", "SAPISID\t", "LOGIN_INFO\t"))
        except Exception:
            has_auth = False
        if has_auth:
            base_cmd += ["--cookies", str(cookies_file)]
    return base_cmd


def _search_yt(query: str, base_cmd: list, min_dur: int = 300,
               max_dur: int = 14400, reject_kw: Optional[list] = None,
               num_results: int = 10) -> list:
    """Search YouTube and return filtered candidates sorted by duration desc."""
    search_url = f"ytsearch{num_results}:{query}"
    info_cmd = base_cmd + ["--dump-json", "--flat-playlist", search_url]
    try:
        info_proc = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    candidates = []
    for line in info_proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            dur = info.get("duration") or 0
            vid_id = info.get("id") or info.get("url", "")
            title = info.get("title", "")
            channel = info.get("channel", "")
            candidates.append((dur, vid_id, title, channel))
        except json.JSONDecodeError:
            continue

    _ALWAYS_REJECT = ["live stream", "scoreboard", "score update",
                      "aiscore", "simulcast", "animation", "animated",
                      "watchalong", "watch along", "reaction",
                      "2k", "nba2k", "nba 2k"]
    all_reject = list(_ALWAYS_REJECT)
    if reject_kw:
        all_reject.extend(reject_kw)

    return [
        c for c in candidates
        if min_dur <= c[0] <= max_dur
        and not any(kw in c[2].lower() for kw in all_reject)
    ]


def _download_video_yt(vid_id: str, out_path: Path, base_cmd: list,
                       segment_seconds: int, best_dur: int) -> bool:
    """Download a YouTube video by ID. Returns True on success."""
    dl_cmd = list(base_cmd)
    dl_cmd += ["--output", str(out_path)]
    if segment_seconds and best_dur > segment_seconds * 2:
        start_sec = 60
        for i, part in enumerate(dl_cmd):
            if part == "--format":
                dl_cmd[i + 1] = "best[height<=720][vcodec^=avc1]/best[height<=720]/best"
                break
        dl_cmd += [
            "--download-sections", f"*{start_sec}-{start_sec + segment_seconds}",
            "--force-keyframes-at-cuts",
        ]
    else:
        for i, part in enumerate(dl_cmd):
            if part == "--format":
                dl_cmd[i + 1] = (
                    "bestvideo[height<=720][vcodec^=avc1]+bestaudio/bestvideo[height<=720]+bestaudio/best[height<=720]/best"
                )
                break
    dl_cmd.append(f"https://www.youtube.com/watch?v={vid_id}")

    try:
        dl_proc = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=600)
        if dl_proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1_000_000:
            print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
            return True
        if dl_proc.stderr:
            print(f"  yt-dlp error: {dl_proc.stderr[-200:]}")
    except subprocess.TimeoutExpired:
        print("  Download timed out")
    except Exception as e:
        print(f"  Download error: {e}")
    return False


def _search_dailymotion(query: str, base_cmd: list,
                        min_dur: int = 300, max_dur: int = 14400) -> list:
    """Search Dailymotion via yt-dlp. NBA full games persist longer on DM."""
    import urllib.parse
    search_url = f"https://www.dailymotion.com/search/{urllib.parse.quote(query)}/videos"
    info_cmd = base_cmd + ["--impersonate", "chrome", "--dump-json", "--flat-playlist", search_url]
    try:
        proc = subprocess.run(info_cmd, capture_output=True, text=True, timeout=30)
    except (subprocess.TimeoutExpired, Exception):
        return []

    candidates = []
    _REJECT = ["live stream", "scoreboard", "aiscore", "simulcast",
               "animation", "animated", "2k", "nba2k", "reaction"]
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            info = json.loads(line)
            dur = info.get("duration") or 0
            vid_url = info.get("webpage_url") or info.get("url", "")
            title = info.get("title", "")
            channel = info.get("uploader", info.get("channel", ""))
            if min_dur <= dur <= max_dur:
                if not any(kw in title.lower() for kw in _REJECT):
                    candidates.append((dur, vid_url, title, channel))
        except json.JSONDecodeError:
            continue
    return sorted(candidates, key=lambda c: c[0], reverse=True)


def _download_direct_url(url: str, out_path: Path, base_cmd: list,
                         segment_seconds: int, best_dur: int) -> bool:
    """Download from a direct URL (Dailymotion, etc). Returns True on success."""
    dl_cmd = list(base_cmd) + ["--impersonate", "chrome"]
    dl_cmd += ["--output", str(out_path)]
    if segment_seconds and best_dur > segment_seconds * 2:
        start_sec = 60
        dl_cmd += [
            "--download-sections", f"*{start_sec}-{start_sec + segment_seconds}",
            "--force-keyframes-at-cuts",
        ]
    dl_cmd.append(url)

    try:
        dl_proc = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=900)
        if dl_proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1_000_000:
            print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
            return True
        if dl_proc.stderr:
            print(f"  yt-dlp error: {dl_proc.stderr[-200:]}")
    except subprocess.TimeoutExpired:
        print("  Download timed out")
    except Exception as e:
        print(f"  Download error: {e}")
    return False


def _search_and_download(game: dict, out_path: Path,
                         segment_seconds: int) -> bool:
    """Search YouTube + Dailymotion for the game and download to out_path.
    Returns True on success.
    Tries: YT full games → DM full games → YT highlights."""
    date_obj = datetime.strptime(game["date"], "%Y-%m-%d")
    date_str  = date_obj.strftime("%B %d %Y")
    month_year = date_obj.strftime("%B %Y")
    away_full = _team_full(game["away"])
    home_full = _team_full(game["home"])
    away_city = _team_city(game["away"])
    home_city = _team_city(game["home"])
    fmt_args = dict(away=away_full, home=home_full,
                    away_city=away_city, home_city=home_city,
                    date_str=date_str, month_year=month_year,
                    season=_current_nba_season())

    base_cmd = _build_base_cmd()

    # Collect ALL candidates from ALL YouTube templates first, then pick the best.
    # Previous approach tried one template at a time and downloaded the first hit,
    # missing better results from later templates.
    all_yt_candidates = []

    # ── Pass 1: YouTube full game replays (>60 min) ──────────────────────────
    for tmpl in _YT_SEARCH_TEMPLATES:
        query = tmpl.format(**fmt_args)
        print(f"  [YT] Searching: {query}")
        candidates = _search_yt(query, base_cmd, min_dur=300, max_dur=14400,
                                reject_kw=["highlights", "highlight"],
                                num_results=10)
        all_yt_candidates.extend(candidates)
        pass  # rate limit removed for pod use

    # Deduplicate by video ID
    _seen_ids = set()
    deduped = []
    for c in all_yt_candidates:
        if c[1] not in _seen_ids:
            _seen_ids.add(c[1])
            deduped.append(c)
    full_games = [c for c in deduped if c[0] >= 3600]

    if full_games:
        def _score(c):
            dur, vid_id, title, channel = c
            s = dur
            cl = channel.lower()
            tl = title.lower()
            # Boost known reliable channels
            if any(k in cl for k in ["manuelmazon", "time for basketball",
                                      "nba full", "full game", "nba replays"]):
                s += 5000
            if cl == "nba" and dur >= 3600:
                s += 4000
            # Boost titles that match team names (relevance check)
            if away_full.lower() in tl and home_full.lower() in tl:
                s += 3000
            elif game["away"].lower() in tl and game["home"].lower() in tl:
                s += 2000
            # Penalize suspiciously long (compilations, not single games)
            if dur > 10800:
                s -= 3000
            return s

        full_games.sort(key=_score, reverse=True)
        # Try top 3 candidates (first might be DMCA'd or geo-blocked)
        for best in full_games[:3]:
            print(f"  Found full game: {best[2][:70]} ({best[0]}s, ch={best[3][:30]})")
            print(f"  Downloading from {best[1]} ...")
            if _download_video_yt(best[1], out_path, base_cmd, segment_seconds, best[0]):
                return True
            print(f"  Failed — trying next candidate...")

    # ── Pass 2: Dailymotion full games ───────────────────────────────────────
    print(f"  No YouTube full game found — trying Dailymotion...")
    for tmpl in _DM_SEARCH_TEMPLATES:
        query = tmpl.format(**fmt_args)
        print(f"  [DM] Searching: {query}")
        candidates = _search_dailymotion(query, base_cmd, min_dur=1200, max_dur=14400)
        if candidates:
            # Prefer longest (most complete game)
            best = candidates[0]
            print(f"  Found on DM: {best[2][:70]} ({best[0]}s)")
            if _download_direct_url(best[1], out_path, base_cmd, segment_seconds, best[0]):
                return True
        time.sleep(1)

    # ── Pass 3: YouTube highlights fallback (>5 min) ─────────────────────────
    print(f"  No full game found — trying highlights...")
    for tmpl in _YT_HIGHLIGHTS_TEMPLATES:
        query = tmpl.format(**fmt_args)
        print(f"  Searching: {query}")
        candidates = _search_yt(query, base_cmd, min_dur=300, max_dur=1800)
        if not candidates:
            continue
        # Prefer longer highlights, NBA official channel
        def _hl_score(c):
            dur, vid_id, title, channel = c
            s = dur
            if channel.lower() == "nba":
                s += 2000
            if "extended" in title.lower():
                s += 1000
            return s
        candidates.sort(key=_hl_score, reverse=True)
        best = candidates[0]
        print(f"  Found highlights: {best[2][:60]} ({best[0]}s)")
        print(f"  Downloading from {best[1]} ...")
        if _download_video_yt(best[1], out_path, base_cmd, 0, best[0]):
            return True

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

    # Default date range: last 30 days, but cap to current season window
    # so we don't accidentally search outside the active season.
    _start_year = int(_current_nba_season().split("-")[0])
    _NBA_SEASON_START = f"{_start_year}-10-01"
    _NBA_SEASON_END   = f"{_start_year + 1}-04-30"
    _today = datetime.now().strftime("%Y-%m-%d")
    _default_to   = min(_today, _NBA_SEASON_END)
    _default_from = max(
        (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        _NBA_SEASON_START,
    )
    # If today is past the season, use the last 30 days OF the season
    if _today > _NBA_SEASON_END:
        _default_to   = _NBA_SEASON_END
        _default_from = (
            datetime.strptime(_NBA_SEASON_END, "%Y-%m-%d") - timedelta(days=30)
        ).strftime("%Y-%m-%d")
    from_date = args.from_date or _default_from
    to_date   = args.to_date   or _default_to

    print(f"Fetching {args.count} games ({from_date} → {to_date}) ...")
    games = _get_recent_games(args.count, from_date, to_date)

    if not games:
        print("No games returned from NBA API. Check your internet connection.")
        return

    segment_s = 0 if args.full else args.segment
    downloaded: list[str] = []
    downloaded_lock = Lock()

    def _fetch_one(game: dict) -> str | None:
        gid = game["game_id"]
        out = VIDEOS_DIR / f"{gid}.mp4"
        if out.exists() and out.stat().st_size > 500_000:
            with _print_lock:
                print(f"[skip] {gid} already downloaded")
            return gid
        with _print_lock:
            print(f"\n── {game['away']} @ {game['home']}  {game['date']}  ({gid})")
        ok = _search_and_download(game, out, segment_s)
        if ok:
            return gid
        with _print_lock:
            print(f"  [WARN] Could not download {gid} — skipping")
        return None

    # Parallel fetch: 4 workers — each yt-dlp search is I/O-bound
    workers = min(4, len(games))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_fetch_one, g): g for g in games if len(downloaded) < args.count * 2}
        for fut in as_completed(futs):
            result = fut.result()
            if result:
                with downloaded_lock:
                    if len(downloaded) < args.count:
                        downloaded.append(result)
            if len(downloaded) >= args.count:
                # Cancel remaining if we have enough
                for f in futs:
                    f.cancel()

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
