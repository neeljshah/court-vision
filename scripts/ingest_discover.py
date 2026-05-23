"""
ingest_discover.py -- enumerate NBA games, resolve video URLs, enqueue queue.db.

The ingest queue (ingest_fetch -> run_phase_g -> backfill_quality) consumes
`queued` rows that carry a `source_url`. Nothing ever populated them, so
ingest_fetch.py had no work. This script is that missing discovery front-end.

Modes:
  --mode channels  scrape full-game YouTube channels, match titles -> NBA game IDs
  --mode search    per-game NBA-API enumeration -> YouTube search for each
  --mode both      channels first, then search to fill toward --target (default)
  --reclaim        register orphan videos already in full_games/ into the queue

Usage:
    conda activate basketball_ai
    python scripts/ingest_discover.py --target 200            # both modes
    python scripts/ingest_discover.py --reclaim               # adopt orphans
    python scripts/ingest_discover.py --mode channels --dry-run
    python scripts/ingest_discover.py --channels @manuelmazon @other

Next step: commit data/ingest/queue.db, rsync to the pod, run ingest_fetch.py.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling-script imports

from src.ingest.db import connect, migrate
from src.ingest.manifest import add_game, get_game
from fetch_games import (  # proven team-name helpers + search templates
    _team_full, _team_city, _current_nba_season,
    _YT_SEARCH_TEMPLATES, _TEAM_NAMES, _TEAM_CITIES,
)
from batch_from_channel import parse_title  # date regex over video titles

FULL_GAMES = ROOT / "data" / "videos" / "full_games"
TRACKING   = ROOT / "data" / "tracking"
COOKIES    = ROOT / "data" / "videos" / "youtube_cookies.txt"

_SEEN: set = set()   # game_ids enqueued this run -- dedup channel re-uploads

# yt-dlp invocation base -- the standalone binary. NOT `python3.11 -m yt_dlp`,
# which fetch_games._build_base_cmd prefers but which has no yt_dlp module here.
_YT_BASE: list = ["yt-dlp", "--quiet", "--no-warnings", "--no-abort-on-error",
                  "--extractor-args", "youtube:player_client=android"]
if COOKIES.exists():
    _YT_BASE += ["--cookies", str(COOKIES)]

# nickname / city -> abbreviation, for matching channel video titles
_NAME_TO_ABBR: dict = {}
for _ab, _nk in _TEAM_NAMES.items():
    _NAME_TO_ABBR[_nk.lower()] = _ab
for _ab, _ct in _TEAM_CITIES.items():
    _NAME_TO_ABBR[_ct.lower()] = _ab


def _seasons_default() -> list:
    """Current NBA season + the two prior (e.g. 2025-26, 2024-25, 2023-24)."""
    y = int(_current_nba_season().split("-")[0])
    return [f"{y - i}-{str(y - i + 1)[-2:]}" for i in range(3)]


def _fetch_season(season: str, retries: int = 3) -> list:
    """All regular-season game-team rows for a season via the NBA stats API."""
    params = urllib.parse.urlencode({
        "LeagueID": "00", "Season": season, "SeasonType": "Regular Season",
    })
    url = f"https://stats.nba.com/stats/leaguegamefinder?{params}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Referer": "https://www.nba.com/", "Origin": "https://www.nba.com",
        "Accept": "application/json, text/plain, */*", "Host": "stats.nba.com",
    }
    for attempt in range(1, retries + 1):
        try:
            time.sleep(0.8)
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            rs = data["resultSets"][0]
            return [dict(zip(rs["headers"], row)) for row in rs["rowSet"]]
        except Exception as exc:
            print(f"  [{season} attempt {attempt}/{retries}] NBA API error: {exc}")
            time.sleep(2.0 * attempt)
    return []


def _parse_matchup(team: str, matchup: str) -> tuple:
    """Return (home, away) abbreviations from an NBA MATCHUP string."""
    if " @ " in matchup:
        away, home = matchup.split(" @ ", 1)
        return home.strip(), away.strip()
    if " vs. " in matchup:
        home, away = matchup.split(" vs. ", 1)
        return home.strip(), away.strip()
    return team, ""


def build_index(seasons: list) -> tuple:
    """Return (games_by_id, id_by_key) for all games across `seasons`.

    games_by_id[gid] = {game_id, date, home, away, season}
    id_by_key[(date, frozenset({home, away}))] = gid   # for channel-title matching
    """
    games_by_id: dict = {}
    id_by_key: dict = {}
    for season in seasons:
        rows = _fetch_season(season)
        print(f"  {season}: {len(rows)} game-team rows")
        for r in rows:
            gid = str(r.get("GAME_ID", "")).strip().zfill(10)
            if not gid or gid in games_by_id or not r.get("WL"):
                continue
            team = str(r.get("TEAM_ABBREVIATION", "")).strip()
            home, away = _parse_matchup(team, str(r.get("MATCHUP", "")))
            if not home or not away:
                continue
            date = str(r.get("GAME_DATE", ""))[:10]
            games_by_id[gid] = {"game_id": gid, "date": date,
                                "home": home, "away": away, "season": season}
            id_by_key[(date, frozenset({home, away}))] = gid
    return games_by_id, id_by_key


def _teams_in_title(title: str) -> list:
    """Detect NBA team abbreviations mentioned in a video title."""
    t = title.lower()
    found: list = []
    for token, ab in _NAME_TO_ABBR.items():
        if token in t and ab not in found:
            found.append(ab)
    return found


def _enqueue(conn, game: dict, url: str, source: str, dry: bool) -> bool:
    """Insert a new `queued` row. Returns True if newly enqueued."""
    gid = game["game_id"]
    if gid in _SEEN or get_game(conn, gid) is not None:
        return False                       # already known -- never clobber
    _SEEN.add(gid)
    if not dry:
        add_game(conn, gid, status="queued", source_url=url,
                 source=source, date=game.get("date"),
                 home=game.get("home"), away=game.get("away"))
    return True


def _interleave_by_season(games: list) -> list:
    """Round-robin games across seasons (newest first) for even coverage."""
    from collections import defaultdict
    buckets: dict = defaultdict(list)
    for g in sorted(games, key=lambda g: g["date"], reverse=True):
        buckets[g["season"]].append(g)
    out: list = []
    while any(buckets.values()):
        for s in sorted(buckets):
            if buckets[s]:
                out.append(buckets[s].pop(0))
    return out


def scrape_channels(channels: list, id_by_key: dict, games_by_id: dict,
                    conn, target: int, dry: bool) -> int:
    """Enumerate channel videos, match titles to game IDs, enqueue. Returns count."""
    enqueued = 0
    for ch in channels:
        ch_url = ch if ch.startswith("http") else f"https://www.youtube.com/{ch}"
        print(f"\n[channels] listing {ch_url}/videos ...")
        try:
            r = subprocess.run(
                _YT_BASE + ["--flat-playlist", "--print",
                            "%(id)s|||%(duration)s|||%(title)s", f"{ch_url}/videos"],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=300)
        except Exception as exc:
            print(f"  [channels] {ch}: list failed -- {exc}")
            continue
        lines = [ln for ln in r.stdout.splitlines() if ln.count("|||") == 2]
        print(f"  {len(lines)} videos listed")
        for ln in lines:
            if enqueued >= target:
                return enqueued
            yt_id, dur_s, title = ln.split("|||", 2)
            try:                                   # skip clips clearly too short
                if dur_s and float(dur_s) < 1800:
                    continue
            except ValueError:
                pass
            teams = _teams_in_title(title)
            _, game_date = parse_title(title)
            if len(teams) != 2 or not game_date:
                continue
            gid = id_by_key.get((game_date, frozenset(teams)))
            if not gid:
                continue
            url = f"https://www.youtube.com/watch?v={yt_id.strip()}"
            if _enqueue(conn, games_by_id[gid], url, "youtube", dry):
                enqueued += 1
                print(f"  + {gid}  {teams[0]}/{teams[1]}  {game_date}")
    return enqueued


def _yt_search(query: str, num: int = 5) -> list:
    """ytsearch via the yt-dlp binary. Returns [(duration, video_id, title)]."""
    cmd = _YT_BASE + ["--dump-json", "--flat-playlist", f"ytsearch{num}:{query}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=45)
    except Exception:
        return []
    out: list = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (d.get("duration") or 0) and d.get("id"):
            out.append((d["duration"], d["id"], d.get("title") or ""))
    return out


def search_games(games: list, conn, target: int, dry: bool, workers: int = 6) -> int:
    """Per-game YouTube search for a full-game URL; enqueue hits. Returns count."""
    templates = _YT_SEARCH_TEMPLATES[:3]
    enqueued = 0

    def _resolve(game: dict) -> tuple:
        try:
            d = datetime.strptime(game["date"], "%Y-%m-%d")
            fmt = dict(
                away=_team_full(game["away"]), home=_team_full(game["home"]),
                away_city=_team_city(game["away"]), home_city=_team_city(game["home"]),
                date_str=d.strftime("%B %d %Y"), month_year=d.strftime("%B %Y"),
                season=game["season"])
            cands: list = []
            for tmpl in templates:
                cands += _yt_search(tmpl.format(**fmt), num=5)
            full = sorted((c for c in cands if c[0] >= 3600),
                          key=lambda c: c[0], reverse=True)
            if full:
                return game, f"https://www.youtube.com/watch?v={full[0][1]}"
        except Exception as exc:
            print(f"  [search] {game['game_id']}: {exc}")
        return game, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_resolve, g) for g in games]
        for fut in as_completed(futs):
            game, url = fut.result()
            if url and _enqueue(conn, game, url, "youtube", dry):
                enqueued += 1
                print(f"  + {game['game_id']}  {game['away']}@{game['home']}  {game['date']}")
            if enqueued >= target:
                for f in futs:
                    f.cancel()
                break
    return enqueued


def reclaim_orphans(conn, dry: bool) -> int:
    """Register videos already in full_games/ that the queue doesn't know about."""
    if not FULL_GAMES.exists():
        return 0
    n = 0
    for mp4 in sorted(FULL_GAMES.glob("*.mp4")):
        gid = mp4.stem
        if get_game(conn, gid) is not None:
            continue
        done = (TRACKING / gid / "tracking_data.csv").exists()
        status = "processed" if done else "verified"
        print(f"  {gid}: {status}")
        if not dry:
            add_game(conn, gid, status=status, source="orphan_reclaim")
        n += 1
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description="Discover NBA game video URLs -> queue.db")
    ap.add_argument("--mode", choices=["channels", "search", "both"], default="both")
    ap.add_argument("--target", type=int, default=200, help="Max games to enqueue")
    ap.add_argument("--seasons", default=None, help="Comma list, e.g. 2023-24,2024-25")
    ap.add_argument("--channels", nargs="*", default=["@manuelmazon"],
                    help="YouTube channel handles/URLs to scrape")
    ap.add_argument("--reclaim", action="store_true",
                    help="Also adopt orphan videos already in full_games/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seasons = args.seasons.split(",") if args.seasons else _seasons_default()
    print(f"=== ingest_discover -- seasons {seasons}, target {args.target} ===")

    conn = connect()
    migrate(conn)
    queued_before = conn.execute(
        "SELECT COUNT(*) FROM games WHERE status='queued'").fetchone()[0]

    reclaimed = 0
    if args.reclaim:
        print("\n--- reclaiming orphan videos ---")
        reclaimed = reclaim_orphans(conn, args.dry_run)

    print("\n--- building NBA game index ---")
    games_by_id, id_by_key = build_index(seasons)
    print(f"  {len(games_by_id)} unique games across {len(seasons)} season(s)")

    ch_n = 0
    if args.mode in ("channels", "both"):
        ch_n = scrape_channels(args.channels, id_by_key, games_by_id,
                               conn, args.target, args.dry_run)
        print(f"\n[channels] enqueued {ch_n}")

    se_n = 0
    if args.mode in ("search", "both") and ch_n < args.target:
        remaining = args.target - ch_n
        pool = [g for g in games_by_id.values()
                if g["game_id"] not in _SEEN and get_game(conn, g["game_id"]) is None]
        pool = _interleave_by_season(pool)
        print(f"\n--- per-game search ({remaining} slots, {len(pool)} candidates) ---")
        se_n = search_games(pool[:remaining * 3], conn, remaining, args.dry_run)
        print(f"\n[search] enqueued {se_n}")

    queued_after = conn.execute(
        "SELECT COUNT(*) FROM games WHERE status='queued'").fetchone()[0]
    conn.close()

    print("\n=== summary ===")
    print(f"  reclaimed orphans : {reclaimed}")
    print(f"  channel hits      : {ch_n}")
    print(f"  search hits       : {se_n}")
    print(f"  queued: {queued_before} -> {queued_after}"
          + ("   [DRY-RUN -- nothing written]" if args.dry_run else ""))
    if not args.dry_run and queued_after > queued_before:
        print(f"\nNext: commit data/ingest/queue.db, rsync to the pod, then")
        print(f"  python scripts/ingest_fetch.py --count {queued_after}")


if __name__ == "__main__":
    main()
