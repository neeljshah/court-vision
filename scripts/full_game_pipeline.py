"""
full_game_pipeline.py — Automated full-game download + process loop.

Picks high-profile 2024-25 NBA games, searches YouTube for full-game
replays (≥ 90 min), downloads them with yt-dlp, then runs the complete
4-stage pipeline (track → features → enrich → retrain check).

Runs until the time budget is exhausted, skipping games already on disk.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    python scripts/full_game_pipeline.py                  # 3-hour default
    python scripts/full_game_pipeline.py --hours 6        # longer run
    python scripts/full_game_pipeline.py --max-frames 3000 # cap frames (faster)
    python scripts/full_game_pipeline.py --no-enrich      # skip NBA enrichment
    python scripts/full_game_pipeline.py --dry-run        # plan only

Output
------
    data/videos/full_games/<game_id>.mp4   downloaded videos
    data/games/<game_id>/                  pipeline outputs per game
    data/full_game_results.json            running metrics log
    vault/Sessions/full_game_<date>.md     final quality report
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

# ── Paths ──────────────────────────────────────────────────────────────────────

_DATA_DIR      = os.path.join(PROJECT_DIR, "data")
_SCHEDULE_DIR  = os.path.join(_DATA_DIR, "nba", "schedule")
_VIDEOS_DIR    = os.path.join(_DATA_DIR, "videos", "full_games")
_GAMES_DIR     = os.path.join(_DATA_DIR, "games")
_COOKIES_FILE  = os.path.join(_DATA_DIR, "videos", "youtube_cookies.txt")
_RESULTS_PATH  = os.path.join(_DATA_DIR, "full_game_results.json")
_VAULT_DIR     = os.path.join(PROJECT_DIR, "vault", "Sessions")

os.makedirs(_VIDEOS_DIR, exist_ok=True)
os.makedirs(_GAMES_DIR, exist_ok=True)
os.makedirs(_VAULT_DIR, exist_ok=True)

# ── Full team name map (abbr → display name for search queries) ────────────────

_TEAM_NAMES: Dict[str, str] = {
    "ATL": "Hawks",   "BKN": "Nets",    "BOS": "Celtics", "CHA": "Hornets",
    "CHI": "Bulls",   "CLE": "Cavaliers","DAL": "Mavericks","DEN": "Nuggets",
    "DET": "Pistons", "GSW": "Warriors","HOU": "Rockets", "IND": "Pacers",
    "LAC": "Clippers","LAL": "Lakers",  "MEM": "Grizzlies","MIA": "Heat",
    "MIL": "Bucks",   "MIN": "Timberwolves","NOP": "Pelicans","NYK": "Knicks",
    "OKC": "Thunder", "ORL": "Magic",   "PHI": "76ers",   "PHX": "Suns",
    "POR": "Blazers", "SAC": "Kings",   "SAS": "Spurs",   "TOR": "Raptors",
    "UTA": "Jazz",    "WAS": "Wizards",
}

# ── High-value target matchups — prioritise these for download ─────────────────
# Format: (home_abbr, away_abbr) — best games of 2024-25 season

_PRIORITY_MATCHUPS: List[Tuple[str, str]] = [
    ("BOS", "NYK"),   # East rivalry
    ("OKC", "DAL"),   # SGA vs Doncic
    ("GSW", "LAL"),   # Classic rivalry
    ("MIL", "IND"),   # Giannis vs Haliburton
    ("DEN", "MIN"),   # Jokic vs Edwards
    ("CLE", "BOS"),   # Top East seeds
    ("PHX", "DAL"),   # KD vs Luka
    ("MIA", "BOS"),   # Playoff rematch
    ("LAL", "GSW"),   # LeBron vs Steph
    ("OKC", "HOU"),   # Young guns
    ("MEM", "NOP"),   # Deep South
    ("SAC", "LAL"),   # Fox vs LeBron
    ("CHI", "MIL"),   # Division game
    ("ATL", "IND"),   # Trae vs Hali
    ("PHI", "TOR"),   # Process vs North
    ("DEN", "PHX"),   # Rocky Mountain
    ("BKN", "NYK"),   # NYC derby
    ("SAS", "LAL"),   # Wemby vs LeBron
    ("NOP", "MEM"),   # Zion vs Morant
    ("HOU", "SAC"),   # West up-and-comers
]

# ── Schedule loader ────────────────────────────────────────────────────────────

_SCHED_CACHE: Dict[str, dict] = {}   # game_id → {game_id, date, home, away}

def _build_schedule_index() -> Dict[str, dict]:
    """Build a full game_id → matchup index from all 2024-25 schedule files."""
    if _SCHED_CACHE:
        return _SCHED_CACHE

    import glob
    files = glob.glob(os.path.join(_SCHEDULE_DIR, "schedule_*_2024-25*.json"))
    for fpath in files:
        team = os.path.basename(fpath).split("schedule_")[1].split("_2024")[0]
        try:
            data = json.load(open(fpath))
        except Exception:
            continue
        games = data if isinstance(data, list) else []
        for g in games:
            gid = g.get("game_id", "")
            if not gid or gid in _SCHED_CACHE:
                continue
            opp  = g.get("opponent", "")
            home = g.get("home", False)
            _SCHED_CACHE[gid] = {
                "game_id": gid,
                "date":    g.get("date", ""),
                "home":    team if home else opp,
                "away":    opp  if home else team,
            }
    return _SCHED_CACHE


def find_game_for_matchup(home: str, away: str) -> Optional[dict]:
    """
    Return the most recent 2024-25 game_id for a home/away matchup.
    Tries both home/away orderings.
    """
    idx = _build_schedule_index()
    matches = []
    for g in idx.values():
        if (g["home"] == home and g["away"] == away) or \
           (g["home"] == away and g["away"] == home):
            matches.append(g)
    if not matches:
        return None
    # Most recent game first
    return sorted(matches, key=lambda x: x["date"], reverse=True)[0]


def build_target_list() -> List[dict]:
    """
    Build ordered download target list.

    1. Priority matchups (curated list above)
    2. Remaining 2024-25 games not yet processed, sorted by date descending
    """
    idx   = _build_schedule_index()
    seen  = set()
    targets = []

    # First: priority matchups
    for home, away in _PRIORITY_MATCHUPS:
        g = find_game_for_matchup(home, away)
        if g and g["game_id"] not in seen:
            seen.add(g["game_id"])
            targets.append(g)

    # Then: everything else sorted by recency
    remaining = sorted(
        [g for g in idx.values() if g["game_id"] not in seen],
        key=lambda x: x["date"],
        reverse=True,
    )
    targets.extend(remaining)
    return targets


# ── YouTube search + download ──────────────────────────────────────────────────

def _search_query(game: dict) -> str:
    """Build a YouTube search query optimised for full-game replay videos."""
    home_name = _TEAM_NAMES.get(game["home"], game["home"])
    away_name = _TEAM_NAMES.get(game["away"], game["away"])
    # Parse date for month/day in query
    try:
        from datetime import datetime as _dt
        d = _dt.strptime(game["date"], "%Y-%m-%d")
        date_str = d.strftime("%B %d").replace(" 0", " ")   # "March 5"
    except Exception:
        date_str = game["date"]

    return (
        f"{home_name} vs {away_name} {date_str} 2025 "
        f"NBA full game replay"
    )


def _video_path(game_id: str) -> str:
    return os.path.join(_VIDEOS_DIR, f"{game_id}.mp4")


def download_full_game(game: dict, timeout_min: int = 30) -> Optional[str]:
    """
    Search YouTube and download the best full-game replay (≥ 90 min).

    Uses yt-dlp with:
      - ytsearch5 — checks top 5 results
      - match-filter duration >= 5400 (90 min)
      - 720p max resolution (balance quality / disk space)
      - cookies from data/videos/youtube_cookies.txt

    Returns local video path on success, None on failure.
    """
    out_path = _video_path(game["game_id"])
    if os.path.exists(out_path) and os.path.getsize(out_path) > 50_000_000:
        print(f"    Already downloaded: {out_path}")
        return out_path

    query   = _search_query(game)
    tmp_out = os.path.join(_VIDEOS_DIR, f"{game['game_id']}.%(ext)s")

    print(f"    Searching: {query}")

    cmd = [
        "yt-dlp",
        f"ytsearch5:{query}",
        "--match-filter", "duration >= 5400",   # ≥ 90 min = full game
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", tmp_out,
        "--no-playlist",
        "--max-downloads", "1",
        "--no-warnings",
        "--quiet",
        "--progress",
    ]
    if os.path.exists(_COOKIES_FILE):
        cmd += ["--cookies", _COOKIES_FILE]

    print(f"    Downloading (≥ 90 min filter, 720p max)...")
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            timeout=timeout_min * 60,
            capture_output=False,
        )
        elapsed = time.time() - t0

        if os.path.exists(out_path):
            size_mb = os.path.getsize(out_path) / (1024 * 1024)
            print(f"    ✓ Downloaded {size_mb:.0f} MB in {elapsed/60:.1f} min → {out_path}")
            return out_path

        # yt-dlp may have written to a slightly different path
        for f in os.listdir(_VIDEOS_DIR):
            if f.startswith(game["game_id"]) and f.endswith(".mp4"):
                actual = os.path.join(_VIDEOS_DIR, f)
                os.rename(actual, out_path)
                size_mb = os.path.getsize(out_path) / (1024 * 1024)
                print(f"    ✓ Downloaded {size_mb:.0f} MB → {out_path}")
                return out_path

        print(f"    ✗ No full-game video found (all results < 90 min or search failed)")
        return None

    except subprocess.TimeoutExpired:
        print(f"    ✗ Download timeout ({timeout_min} min)")
        return None
    except Exception as e:
        print(f"    ✗ Download error: {e}")
        return None


# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_pipeline(game: dict, video_path: str, max_frames: Optional[int],
                 no_enrich: bool) -> dict:
    """Run the 4-stage pipeline on a downloaded full game."""
    import inspect
    from src.pipeline.unified_pipeline import UnifiedPipeline
    from src.features.feature_engineering import run as run_features

    t0 = time.time()
    result = {
        "game_id":       game["game_id"],
        "date":          game["date"],
        "home":          game["home"],
        "away":          game["away"],
        "video_path":    video_path,
        "started_at":    datetime.now().isoformat(),
        "success":       False,
        "error":         None,
        "traceback":     None,
        "total_frames":      0,
        "tracking_rows":     0,
        "stability":         0.0,
        "id_switches":       0,
        "fps_estimate":      0.0,
        "ball_detected_pct": 0.0,
        "shots_detected":        0,
        "possessions_labeled":   0,
        "shots_enriched":        0,
        "possessions_enriched":  0,
        "stages_completed": [],
    }

    try:
        # Stage 1: Tracking
        print(f"\n  [TRACKING] {game['home']} vs {game['away']}  {game['date']}")
        t_track = time.time()
        up_kwargs = dict(
            video_path=video_path,
            yolo_weight_path=None,
            max_frames=max_frames,
            show=False,
            game_id=game["game_id"],
        )
        sig = inspect.signature(UnifiedPipeline.__init__).parameters
        if "frame_skip" in sig:
            up_kwargs["frame_skip"] = 1
        pipeline = UnifiedPipeline(**up_kwargs)
        tr = pipeline.run()

        result["total_frames"] = tr.get("total_frames", 0)
        result["stability"]    = round(float(tr.get("stability", 0)), 3)
        result["id_switches"]  = tr.get("id_switches", 0)
        elapsed_track = time.time() - t_track
        result["fps_estimate"] = round(result["total_frames"] / max(elapsed_track, 1), 1)
        result["stages_completed"].append("tracking")

        # Ball detection rate
        bt_path = os.path.join(_DATA_DIR, "ball_tracking.csv")
        if os.path.exists(bt_path):
            try:
                import csv
                total_bt = detected_bt = 0
                with open(bt_path, newline="") as f:
                    for row in csv.DictReader(f):
                        total_bt += 1
                        if row.get("detected", "0") == "1":
                            detected_bt += 1
                if total_bt > 0:
                    result["ball_detected_pct"] = round(100.0 * detected_bt / total_bt, 1)
            except Exception:
                pass

        result["tracking_rows"]       = _count_rows(os.path.join(_DATA_DIR, "tracking_data.csv"))
        result["shots_detected"]      = _count_rows(os.path.join(_DATA_DIR, "shot_log.csv"))
        result["possessions_labeled"] = _count_rows(os.path.join(_DATA_DIR, "possessions.csv"))

        print(f"  ✓ Tracked {result['total_frames']} frames @ {result['fps_estimate']} fps  "
              f"stability={result['stability']}  ball={result['ball_detected_pct']}%")

        # Stage 2: Features
        print(f"  [FEATURES]")
        try:
            run_features(
                input_path=os.path.join(_DATA_DIR, "tracking_data.csv"),
                output_path=os.path.join(_DATA_DIR, "features.csv"),
            )
            result["stages_completed"].append("features")
            print(f"  ✓ Features — {_count_rows(os.path.join(_DATA_DIR, 'features.csv'))} rows")
        except Exception as e:
            print(f"  ⚠ Features failed: {e}")

        # Stage 3: NBA enrichment
        if not no_enrich:
            print(f"  [ENRICH]")
            try:
                import csv
                from src.data.nba_enricher import enrich
                enrich_result = enrich(
                    game_id=game["game_id"],
                    period=1,
                    clip_start_sec=0.0,
                    fps=result["fps_estimate"] or 30.0,
                    data_dir=_DATA_DIR,
                )
                result["stages_completed"].append("enrichment")
                for key, pkey in [("shots_enriched", "shot_log_enriched"),
                                   ("possessions_enriched", "possessions_enriched")]:
                    p = enrich_result.get(pkey, "")
                    if p and os.path.exists(p):
                        with open(p, newline="") as fh:
                            rows_e = list(csv.DictReader(fh))
                        if pkey == "shot_log_enriched":
                            result[key] = sum(1 for r in rows_e if r.get("made", "") != "")
                        else:
                            result[key] = sum(1 for r in rows_e if r.get("result", "") not in ("", "unknown"))
                print(f"  ✓ Enriched — {result['shots_enriched']} shots / "
                      f"{result['possessions_enriched']} possessions")
            except Exception as e:
                print(f"  ⚠ Enrich failed: {e}")
        else:
            print(f"  [ENRICH] skipped")

        # Stage 4: Snapshot
        _snapshot(game["game_id"], result)
        result["stages_completed"].append("snapshot")
        result["success"] = True

    except KeyboardInterrupt:
        raise
    except Exception as e:
        result["error"]     = str(e)
        result["traceback"] = traceback.format_exc()
        print(f"\n  ✗ Pipeline failed: {e}")
        print(result["traceback"])

    result["duration_sec"] = round(time.time() - t0, 1)
    return result


def _count_rows(path: str) -> int:
    if not os.path.exists(path):
        return 0
    try:
        import csv
        with open(path, newline="") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def _snapshot(game_id: str, result: dict) -> None:
    import shutil
    out = os.path.join(_GAMES_DIR, game_id)
    os.makedirs(out, exist_ok=True)
    for fname in [
        "tracking_data.csv", "ball_tracking.csv", "possessions.csv",
        "shot_log.csv", "features.csv", "stats.json",
        "shot_log_enriched.csv", "possessions_enriched.csv",
    ]:
        src = os.path.join(_DATA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out, fname))
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(result, f, indent=2)


# ── Quality grade ──────────────────────────────────────────────────────────────

def grade(r: dict) -> str:
    if not r["success"]:
        return "F"
    s, bd, sh, pos = r["stability"], r["ball_detected_pct"], r["shots_detected"], r["possessions_labeled"]
    if s >= 0.9 and bd >= 80 and sh >= 10 and pos >= 50: return "A"
    if s >= 0.8 and bd >= 60 and sh >= 5  and pos >= 20: return "B"
    if s >= 0.7 and bd >= 40 and sh >= 2  and pos >= 5:  return "C"
    if s > 0: return "D"
    return "F"


# ── Vault report ───────────────────────────────────────────────────────────────

def write_report(results: List[dict], path: str, hours: float) -> None:
    from collections import Counter
    ok    = sum(1 for r in results if r["success"])
    total = len(results)
    grades = [grade(r) for r in results]
    avg_s  = sum(r["stability"] for r in results if r["success"]) / max(ok, 1)
    avg_b  = sum(r["ball_detected_pct"] for r in results if r["success"]) / max(ok, 1)
    avg_f  = sum(r["fps_estimate"] for r in results if r["success"]) / max(ok, 1)
    t_rows = sum(r["tracking_rows"] for r in results)
    t_sh   = sum(r["shots_detected"] for r in results)
    t_pos  = sum(r["possessions_labeled"] for r in results)
    t_enr  = sum(r["shots_enriched"] for r in results)

    lines = [
        f"# Full Game Pipeline — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"",
        f"**Runtime:** {hours:.1f}h   **Games processed:** {ok}/{total}",
        f"**Avg FPS:** {avg_f:.1f}   **Avg stability:** {avg_s:.3f}   **Avg ball det.:** {avg_b:.1f}%",
        f"**Total tracking rows:** {t_rows:,}   **Shots detected:** {t_sh}   "
        f"**Possessions:** {t_pos}   **Shots enriched:** {t_enr}",
        f"",
        f"## Results",
        f"",
        f"| Date | Matchup | Grade | Frames | FPS | Stab | Ball% | Shots | Poss | Enriched |",
        f"|------|---------|-------|--------|-----|------|-------|-------|------|----------|",
    ]
    for r, g in zip(results, grades):
        matchup = f"{r['home']} vs {r['away']}"
        lines.append(
            f"| {r['date']} | {matchup} | {g} | {r['total_frames']} | {r['fps_estimate']} "
            f"| {r['stability']:.3f} | {r['ball_detected_pct']}% "
            f"| {r['shots_detected']} | {r['possessions_labeled']} | {r['shots_enriched']} |"
        )

    grade_dist = Counter(grades)
    lines += ["", "## Grade Distribution", ""]
    for g in "ABCDF":
        if grade_dist[g]:
            lines.append(f"- **{g}**: {grade_dist[g]}")

    failures = [r for r in results if not r["success"]]
    lines += ["", "## Failures", ""]
    if failures:
        for r in failures:
            lines.append(f"### {r['home']} vs {r['away']}  {r['date']}")
            lines.append(f"```\n{r.get('error', '')}\n```")
    else:
        lines.append("None.")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Report → {path}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Full-game download + pipeline loop")
    parser.add_argument("--hours",        type=float, default=3.0)
    parser.add_argument("--max-frames",   type=int,   default=None)
    parser.add_argument("--no-enrich",    action="store_true")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--download-only",action="store_true",
                        help="Only download, don't process")
    parser.add_argument("--process-only", action="store_true",
                        help="Only process already-downloaded videos, skip yt-dlp")
    parser.add_argument("--download-timeout", type=int, default=30,
                        help="Max minutes to wait per download (default 30)")
    args = parser.parse_args()

    deadline = datetime.now() + timedelta(hours=args.hours)
    vault_log = os.path.join(
        _VAULT_DIR,
        f"full_game_{datetime.now().strftime('%Y-%m-%d_%H%M')}.md",
    )

    targets   = build_target_list()
    results: List[dict] = []

    # Load existing results to skip already-done games
    done_ids: set = set()
    if os.path.exists(_RESULTS_PATH):
        try:
            existing = json.load(open(_RESULTS_PATH))
            for r in existing:
                if r.get("success"):
                    done_ids.add(r["game_id"])
            results = existing
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"  NBA AI — Full Game Pipeline")
    print(f"  Runtime  : {args.hours}h  (deadline {deadline.strftime('%H:%M')})")
    print(f"  Targets  : {len(targets)} games  ({len(done_ids)} already done)")
    print(f"  Mode     : {'download only' if args.download_only else 'process only' if args.process_only else 'download + process'}")
    print(f"  Enrich   : {'OFF' if args.no_enrich else 'ON'}")
    print(f"  Frames   : {'all' if not args.max_frames else args.max_frames}")
    print(f"{'='*60}")

    if args.dry_run:
        print("\nFirst 10 targets:")
        for t in targets[:10]:
            vid = _video_path(t["game_id"])
            on_disk = " [on disk]" if os.path.exists(vid) else ""
            done    = " [DONE]"   if t["game_id"] in done_ids else ""
            print(f"  {t['date']}  {t['home']:3s} vs {t['away']:3s}  {t['game_id']}{on_disk}{done}")
        print("\nDry-run — exiting.")
        return

    # ── Main loop ──────────────────────────────────────────────────────────────
    for game in targets:
        if datetime.now() >= deadline:
            print("\n  Time limit reached.")
            break

        if game["game_id"] in done_ids:
            continue

        mins_left = int((deadline - datetime.now()).total_seconds() // 60)
        print(f"\n{'─'*60}")
        print(f"  {game['date']}  {game['home']} vs {game['away']}  "
              f"[{game['game_id']}]  {mins_left} min left")
        print(f"{'─'*60}")

        # Step 1: Download (skip if --process-only or already on disk)
        video_path = _video_path(game["game_id"])
        if not args.process_only:
            if os.path.exists(video_path) and os.path.getsize(video_path) > 50_000_000:
                print(f"  Video already on disk ({os.path.getsize(video_path)//1_000_000} MB) — skip download")
            else:
                video_path = download_full_game(game, timeout_min=args.download_timeout)
                if video_path is None:
                    print(f"  No full-game video found — skipping this game")
                    continue

        if args.download_only:
            continue

        # Step 2: Verify we have a video
        if not os.path.exists(video_path):
            print(f"  No video at {video_path} — skipping")
            continue

        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        if size_mb < 50:
            print(f"  Video too small ({size_mb:.0f} MB) — likely not a full game, skipping")
            continue

        # Step 3: Check time budget — skip if < 10 min left
        if (deadline - datetime.now()).total_seconds() < 600:
            print(f"  < 10 min left — stopping before processing more games.")
            break

        # Step 4: Process
        result = run_pipeline(
            game=game,
            video_path=video_path,
            max_frames=args.max_frames,
            no_enrich=args.no_enrich,
        )
        results.append(result)
        if result["success"]:
            done_ids.add(game["game_id"])

        # Print grade summary
        g = grade(result)
        status = "✓" if result["success"] else "✗"
        print(f"\n  {status} Grade: {g}  |  "
              f"frames={result['total_frames']}  fps={result['fps_estimate']}  "
              f"stab={result['stability']}  ball={result['ball_detected_pct']}%  "
              f"shots={result['shots_detected']}  poss={result['possessions_labeled']}  "
              f"enriched={result['shots_enriched']}  time={result['duration_sec']:.0f}s")

        # Save running log
        try:
            with open(_RESULTS_PATH, "w") as f:
                json.dump(results, f, indent=2)
        except Exception:
            pass

    # ── Final report ───────────────────────────────────────────────────────────
    elapsed = args.hours - (deadline - datetime.now()).total_seconds() / 3600
    processed = [r for r in results if r.get("started_at")]

    print(f"\n{'='*60}")
    print(f"  DONE — {len(processed)} games processed")
    print(f"{'='*60}")

    if processed:
        write_report(processed, vault_log, elapsed)
        print(f"  Results → {_RESULTS_PATH}")

    print()


if __name__ == "__main__":
    main()
