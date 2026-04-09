"""
batch_from_channel.py — Download full game replays from a YouTube channel
and run the tracking pipeline on each.

Usage:
    python scripts/batch_from_channel.py --channel https://www.youtube.com/@manuelmazon --limit 10
    python scripts/batch_from_channel.py --dry-run
"""
import argparse, csv, json, os, re, subprocess, sys, time, gc
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))
DATA = PROJECT / "data"
TRACK = DATA / "tracking"
VIDEOS = DATA / "videos" / "full_games"
LOG = DATA / "season_batch_log.csv"
PYTHON = sys.executable

TEAM_MAP = {
    "atlanta hawks": "ATL", "boston celtics": "BOS", "brooklyn nets": "BKN",
    "charlotte hornets": "CHA", "chicago bulls": "CHI", "cleveland cavaliers": "CLE",
    "dallas mavericks": "DAL", "denver nuggets": "DEN", "detroit pistons": "DET",
    "golden state warriors": "GSW", "houston rockets": "HOU", "indiana pacers": "IND",
    "los angeles clippers": "LAC", "los angeles lakers": "LAL", "memphis grizzlies": "MEM",
    "miami heat": "MIA", "milwaukee bucks": "MIL", "minnesota timberwolves": "MIN",
    "new orleans pelicans": "NOP", "new york knicks": "NYK", "oklahoma city thunder": "OKC",
    "orlando magic": "ORL", "philadelphia 76ers": "PHI", "phoenix suns": "PHX",
    "portland trail blazers": "POR", "sacramento kings": "SAC", "san antonio spurs": "SAS",
    "toronto raptors": "TOR", "utah jazz": "UTA", "washington wizards": "WAS",
}


def parse_title(title):
    """Extract team names and date from video title."""
    title_lower = title.lower()
    teams = []
    for name, abbr in TEAM_MAP.items():
        if name in title_lower:
            teams.append(abbr)
    date_match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)"
        r"\s+(\d{1,2}),?\s*(\d{4})",
        title_lower,
    )
    game_date = None
    if date_match:
        try:
            game_date = datetime.strptime(
                f"{date_match.group(1)} {date_match.group(2)} {date_match.group(3)}",
                "%B %d %Y",
            ).strftime("%Y-%m-%d")
        except Exception:
            pass
    return teams, game_date


def find_game_id(teams, game_date):
    """Look up NBA game ID via nba_api."""
    if not game_date or len(teams) < 2:
        return None
    try:
        from nba_api.stats.endpoints import ScoreboardV2
        from nba_api.stats.static import teams as nba_teams

        sb = ScoreboardV2(game_date=game_date)
        games = sb.game_header.get_data_frame()
        all_teams = nba_teams.get_teams()
        for _, row in games.iterrows():
            home = row.get("HOME_TEAM_ID", "")
            away = row.get("VISITOR_TEAM_ID", "")
            home_abbr = next((t["abbreviation"] for t in all_teams if t["id"] == home), "")
            away_abbr = next((t["abbreviation"] for t in all_teams if t["id"] == away), "")
            if set([home_abbr, away_abbr]) == set(teams):
                return row["GAME_ID"]
        time.sleep(0.6)
    except Exception as e:
        print(f"  NBA API error: {e}", flush=True)
    return None


def already_done(game_id):
    td = TRACK / game_id / "tracking_data.csv"
    if not td.exists():
        return False
    try:
        rows = sum(1 for _ in open(td, encoding="utf-8", errors="replace"))
        return rows > 10000
    except Exception:
        return False


def download_video(yt_id, game_id):
    out = VIDEOS / f"{game_id}.mp4"
    if out.exists() and out.stat().st_size > 10_000_000:
        return out
    VIDEOS.mkdir(parents=True, exist_ok=True)
    cmd = [
        # Force H.264 — cv2 can't decode AV1; see scripts/fetch_games.py comment.
        "yt-dlp", "-f", "bestvideo[height<=720][vcodec^=avc1]+bestaudio[ext=m4a]/best[height<=720][vcodec!*=av01][vcodec!*=vp9]",
        "--merge-output-format", "mp4",
        "-o", str(out),
        f"https://www.youtube.com/watch?v={yt_id}",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f"  yt-dlp error: {r.stderr[:200]}", flush=True)
        return None
    return out if out.exists() else None


def run_pipeline(game_id, video_path):
    cmd = [
        PYTHON, str(PROJECT / "scripts" / "run_phase_g.py"),
        "--game-id", game_id,
        "--video", str(video_path),
        "--frames", "18000",
        "--no-show",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    return r.returncode == 0, r.stderr[:500] if r.returncode != 0 else ""


def log_result(game_id, matchup, status, error=""):
    rows = 0
    td = TRACK / game_id / "tracking_data.csv"
    if td.exists():
        rows = sum(1 for _ in open(td, encoding="utf-8", errors="replace"))
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            game_id, matchup, status, rows, 0, 0, 0, error,
        ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default="https://www.youtube.com/@manuelmazon")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"Fetching video list from {args.channel}...", flush=True)
    r = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--print", "%(id)s|||%(title)s",
         f"{args.channel}/videos"],
        capture_output=True, text=True, timeout=120,
    )
    videos = []
    for line in r.stdout.strip().split("\n"):
        if "|||" not in line:
            continue
        yt_id, title = line.split("|||", 1)
        if "full game" not in title.lower() and "nba" not in title.lower():
            continue
        videos.append((yt_id.strip(), title.strip()))

    print(f"Found {len(videos)} full game videos", flush=True)

    processed = 0
    for i, (yt_id, title) in enumerate(videos):
        if processed >= args.limit:
            break
        teams, game_date = parse_title(title)
        if len(teams) < 2 or not game_date:
            print(f"  [{i+1}] SKIP (can't parse): {title[:60]}", flush=True)
            continue

        matchup = f"{teams[0]} vs {teams[1]}"
        print(f"\n[{processed+1}/{args.limit}] {title[:70]}", flush=True)
        print(f"  Teams: {teams}  Date: {game_date}", flush=True)

        game_id = find_game_id(teams, game_date)
        if not game_id:
            print("  No NBA game ID found -- skipping", flush=True)
            continue

        print(f"  Game ID: {game_id}", flush=True)

        if already_done(game_id):
            print("  Already processed -- skipping", flush=True)
            continue

        if args.dry_run:
            print("  [dry-run] Would download + process", flush=True)
            processed += 1
            continue

        # Download
        print(f"  Downloading {yt_id}...", flush=True)
        video_path = download_video(yt_id, game_id)
        if not video_path:
            log_result(game_id, matchup, "download_failed", "yt-dlp failed")
            continue

        print(f"  Downloaded: {video_path.stat().st_size // 1_000_000} MB", flush=True)

        # Pipeline
        print("  Running pipeline...", flush=True)
        ok, err = run_pipeline(game_id, video_path)

        if ok:
            print("  SUCCESS", flush=True)
            log_result(game_id, matchup, "success")
        else:
            print(f"  PIPELINE FAILED: {err[:100]}", flush=True)
            log_result(game_id, matchup, "pipeline_failed", err[:200])

        # Cleanup video
        try:
            video_path.unlink()
            print("  Deleted video (disk space)", flush=True)
        except Exception:
            pass

        processed += 1
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass

    print(f"\n=== Done: {processed} games attempted ===", flush=True)


if __name__ == "__main__":
    main()
