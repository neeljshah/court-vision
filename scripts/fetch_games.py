"""
fetch_games.py — Auto-download NBA game footage via yt-dlp, no OBS needed.

Pulls recent games from the NBA schedule API, searches YouTube for each
game's full broadcast, downloads a segment (default: first 15 min of Q1),
and saves to data/videos/full_games/{game_id}.mp4.

Usage:
    conda activate basketball_ai

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
    # Bug 47 fix 2026-05-29: query both Regular Season AND Playoffs.
    # Regular Season 2025-26 ended 2026-04-12; April-June dates need Playoffs.
    try:
        import pandas as _pd
        rs = LeagueGameLog(season=season, season_type_all_star="Regular Season").get_data_frames()[0]
        try:
            po = LeagueGameLog(season=season, season_type_all_star="Playoffs").get_data_frames()[0]
        except Exception:
            po = _pd.DataFrame()
        df = _pd.concat([rs, po], ignore_index=True) if not po.empty else rs
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
        # NOTE: was "player_client=android" — but in yt-dlp 2026+ the android
        # client SKIPS cookies ("Skipping client 'android' since it does not
        # support cookies"), leaving requests unauthenticated → bot-detected on
        # NBA content. With logged-in cookies + Deno + yt-dlp-ejs the default
        # client chain (tv/web with signature solving) works.
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
        if dl_proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 30_000_000:
            print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
            return True
        if dl_proc.stderr:
            print(f"  yt-dlp error: {dl_proc.stderr[-200:]}")
        # Delete tiny/failed downloads so the orchestrator doesn't pick them up.
        if out_path.exists() and out_path.stat().st_size <= 30_000_000:
            try: out_path.unlink()
            except Exception: pass
    except subprocess.TimeoutExpired:
        print("  Download timed out")
    except Exception as e:
        print(f"  Download error: {e}")
    return False


def _search_archive_org(away: str, home: str, away_city: str, home_city: str,
                        min_dur: int = 1800) -> list:
    """Search archive.org for NBA footage. No bot detection or rate limits."""
    import urllib.request, urllib.parse
    seen: set = set()
    candidates = []
    for q in [f'"{away}" "{home}" NBA', f'"{away_city}" "{home_city}" NBA basketball']:
        params = urllib.parse.urlencode([
            ("q", f"({q}) AND mediatype:movies"),
            ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "runtime"),
            ("rows", "5"), ("output", "json"),
        ])
        try:
            req = urllib.request.Request(
                f"https://archive.org/advancedsearch.php?{params}",
                headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                docs = json.loads(r.read()).get("response", {}).get("docs", [])
            for doc in docs:
                ident = doc.get("identifier", "")
                if not ident or ident in seen:
                    continue
                seen.add(ident)
                title = doc.get("title", "")
                parts = (doc.get("runtime") or "").split(":")
                dur = 0
                try:
                    if len(parts) == 3:
                        dur = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                    elif len(parts) == 2:
                        dur = int(parts[0]) * 60 + int(parts[1])
                except ValueError:
                    pass
                if dur >= min_dur or dur == 0:
                    candidates.append((dur or 7200, f"https://archive.org/details/{ident}", title))
        except Exception:
            pass
    return sorted(candidates, key=lambda c: c[0], reverse=True)


def _download_archive_item(url: str, out_path: Path, base_cmd: list,
                           segment_seconds: int) -> bool:
    """Download from archive.org via yt-dlp (no impersonation needed)."""
    dl_cmd = list(base_cmd) + ["--output", str(out_path)]
    if segment_seconds:
        dl_cmd += [
            "--download-sections", f"*60-{60 + segment_seconds}",
            "--force-keyframes-at-cuts",
        ]
    dl_cmd.append(url)
    try:
        proc = subprocess.run(dl_cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 30_000_000:
            print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
            return True
        if proc.stderr:
            print(f"  yt-dlp error: {proc.stderr[-200:]}")
        if out_path.exists() and out_path.stat().st_size <= 30_000_000:
            try: out_path.unlink()
            except Exception: pass
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
        if dl_proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 30_000_000:
            print(f"  Saved: {out_path} ({out_path.stat().st_size // 1024 // 1024} MB)")
            return True
        if dl_proc.stderr:
            print(f"  yt-dlp error: {dl_proc.stderr[-200:]}")
        if out_path.exists() and out_path.stat().st_size <= 30_000_000:
            try: out_path.unlink()
            except Exception: pass
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
    # Require BOTH team names (full, city, or abbrev) appear in title to prevent
    # channel-boost from accepting unrelated games (e.g., "Time for Basketball"
    # uploads from prior seasons labeled as current-season game_ids).
    def _matches_teams(title):
        tl = title.lower()
        away_match = (away_full.lower() in tl) or (away_city.lower() in tl) or \
                     (game["away"].lower() in tl)
        home_match = (home_full.lower() in tl) or (home_city.lower() in tl) or \
                     (game["home"].lower() in tl)
        if not (away_match and home_match):
            return False
        import re as _re
        years = set(_re.findall(r"\b(19[5-9]\d|20[0-2]\d)\b", tl))
        current_era = {y for y in years if y in ("2024", "2025", "2026")}
        stale = years - current_era
        if stale and not current_era:
            return False
        # Reject explicit prior-season indicators like "2024-25", "2024 2025",
        # "23-24". A title like "2024 2025 NBA Game 4" is the 2024-25 season,
        # not the queried 2025-26 — even though both years are "current era".
        season_pairs = set()
        for y1, y2 in _re.findall(r"\b(20\d{2})[-/\s\.](20\d{2}|\d{2})\b", tl):
            y2_int = int(y2) if len(y2) == 4 else 2000 + int(y2)
            if y2_int == int(y1) + 1:
                season_pairs.add((int(y1), y2_int))
        if season_pairs:
            current_seasons = {(2025, 2026), (2026, 2027)}
            if not (season_pairs & current_seasons):
                return False
        # Date relevance: if the title names a specific month+day that does not
        # match the queried game's date (±1 day for late-night broadcasts), it's
        # a different game between the same teams — reject. Titles with no
        # specific date are accepted (assumed channel-style uploads).
        _MONTHS = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "october": 10,
            "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
        }
        found_dates = []
        for mname, mnum in _MONTHS.items():
            for m in _re.finditer(rf"\b{mname}\.?\s+(\d{{1,2}})(?:[a-z]{{0,2}})?(?:[,\s]+(\d{{4}}))?", tl):
                day = int(m.group(1))
                year = int(m.group(2)) if m.group(2) else None
                if 1 <= day <= 31:
                    found_dates.append((mnum, day, year))
        for m in _re.finditer(r"\b(\d{1,2})[/\-\.](\d{1,2})(?:[/\-\.](\d{2,4}))?\b", tl):
            month, day = int(m.group(1)), int(m.group(2))
            yraw = m.group(3)
            year = int("20" + yraw) if yraw and len(yraw) == 2 else (int(yraw) if yraw else None)
            if 1 <= month <= 12 and 1 <= day <= 31:
                found_dates.append((month, day, year))
        if found_dates:
            from datetime import timedelta as _td
            ok = False
            for delta in (-1, 0, 1):
                target = date_obj + _td(days=delta)
                for fmonth, fday, fyear in found_dates:
                    if fmonth == target.month and fday == target.day:
                        if fyear is None or fyear == target.year:
                            ok = True
                            break
                if ok:
                    break
            if not ok:
                return False
        return True

    full_games = [c for c in deduped if c[0] >= 3600 and _matches_teams(c[2])]

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
        candidates = [c for c in candidates if _matches_teams(c[2])]
        if candidates:
            # Prefer longest (most complete game)
            best = candidates[0]
            print(f"  Found on DM: {best[2][:70]} ({best[0]}s)")
            if _download_direct_url(best[1], out_path, base_cmd, segment_seconds, best[0]):
                return True
        time.sleep(1)

    # ── Pass 2.5: Internet Archive ─ re-enabled with team+year+date validation ──
    # Use the same _matches_teams() guard (covers team names, current-era years,
    # and date-in-title checks) so IA can't return 1990s NBA All-Star Game.
    print(f"  Trying Internet Archive...")
    ia_hits = _search_archive_org(away_full, home_full, away_city, home_city)
    ia_hits = [(d, u, t) for (d, u, t) in ia_hits if _matches_teams(t)]
    for ia_dur, ia_url, ia_title in ia_hits[:3]:
        print(f"  [IA] {ia_title[:60]} ({ia_dur}s)")
        if _download_archive_item(ia_url, out_path, base_cmd, segment_seconds):
            return True

    # ── Pass 3: extended highlights (≥30 min) — short clips cause RC3_ZERO_ROWS ──
    # Only accept ≥1800s so the tracker sees enough stable broadcast court footage.
    print(f"  No full game found — trying extended highlights (≥30 min)...")
    for tmpl in _YT_HIGHLIGHTS_TEMPLATES:
        query = tmpl.format(**fmt_args)
        print(f"  Searching: {query}")
        candidates = _search_yt(query, base_cmd, min_dur=1800, max_dur=5400)
        candidates = [c for c in candidates if _matches_teams(c[2])]
        if not candidates:
            continue
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
        print(f"  Found extended highlights: {best[2][:60]} ({best[0]}s)")
        print(f"  Downloading from {best[1]} ...")
        if _download_video_yt(best[1], out_path, base_cmd, segment_seconds, best[0]):
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
    ap.add_argument("--game-id",  dest="game_id", default=None,
                    help="Download exactly this NBA game ID (e.g. 0022500279). "
                         "When set, --count is ignored and only this game is "
                         "fetched. Matchup is looked up via NBA API.")
    ap.add_argument("--out-dir",  dest="out_dir", default=None,
                    help="Override download directory "
                         "(default: data/videos/full_games). Pod orchestrator "
                         "uses /root/nba_videos.")
    args = ap.parse_args()

    # Allow per-call override of the videos directory (for orchestrators).
    global VIDEOS_DIR
    if args.out_dir:
        VIDEOS_DIR = Path(args.out_dir)
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

    # Load already-processed game IDs so we never re-download PREFLIGHT_FAIL or
    # done games.  Without this, the orchestrator loop re-downloads the same
    # failed game every iteration (video deleted post-PREFLIGHT → not on disk →
    # fetch_games thinks it's new → downloads again → PREFLIGHT_FAIL → repeat).
    _done_log = PROJECT_DIR / "data" / "phase_g_processed.txt"
    _processed_ids: set[str] = set()
    if _done_log.exists():
        for _ln in _done_log.read_text().splitlines():
            _ln = _ln.strip()
            if _ln and not _ln.startswith("hash:"):
                _processed_ids.add(_ln)

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

    # --game-id mode: download exactly one game; look up matchup via NBA API.
    if args.game_id:
        print(f"Single-game mode: fetching matchup for {args.game_id}")
        # Search a wide window — the game could be anywhere in the season.
        wide_games = _get_recent_games(
            count=10000,
            from_date=_NBA_SEASON_START,
            to_date=_NBA_SEASON_END,
        )
        match = next((g for g in wide_games if g["game_id"] == args.game_id),
                     None)
        if not match:
            # Maybe a prior season — try one season back.
            prev_start_year = _start_year - 1
            prev_start = f"{prev_start_year}-10-01"
            prev_end   = f"{prev_start_year + 1}-04-30"
            print(f"  not found in current season — trying {prev_start_year}-"
                  f"{prev_start_year + 1}")
            wide_games = _get_recent_games(
                count=10000, from_date=prev_start, to_date=prev_end,
            )
            match = next((g for g in wide_games if g["game_id"] == args.game_id),
                         None)
        if not match:
            print(f"[ERR] game_id {args.game_id} not in NBA API for current or "
                  f"previous season. Aborting.")
            return
        games = [match]
        args.count = 1
    else:
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
        if gid in _processed_ids:
            with _print_lock:
                print(f"[skip] {gid} already processed (in done log)")
            return None  # don't count as downloaded — already handled
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
