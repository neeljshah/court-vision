"""
run_data_collection.py — Batch CV data collection across all game clips.

Runs the full tracking pipeline on every clip in data/videos/, saving each
game's output to its own directory so nothing ever overwrites.

Usage
-----
    # Run all clips (skip already-completed)
    conda run -n basketball_ai python scripts/run_data_collection.py

    # Run a single clip by name
    conda run -n basketball_ai python scripts/run_data_collection.py --clip cavs_vs_celtics_2025

    # Run all clips, re-process already-done ones
    conda run -n basketball_ai python scripts/run_data_collection.py --force

    # Cap frames per clip (faster, less data — good for testing)
    conda run -n basketball_ai python scripts/run_data_collection.py --max-frames 9000

    # Merge all completed game CSVs into one master dataset
    conda run -n basketball_ai python scripts/run_data_collection.py --merge-only

Output layout
-------------
    data/
      game_results/
        cavs_vs_celtics_2025/
          tracking_data.csv       # player positions every frame
          ball_tracking.csv       # ball x/y every frame
          possessions.csv         # per-possession summary
          shot_log.csv            # every shot with CV features
          player_clip_stats.csv   # per-player aggregated metrics
          summary.json            # run metadata
        bos_mia_2025/
          ...
      master/
        tracking_data.csv         # all games merged (created by --merge-only)
        shot_log.csv
        possessions.csv

Frame math (RTX 4060, 15fps throughput)
----------------------------------------
    Full game  (~162,000 frames at 30fps)  → stride-2 → 81,000 frames → ~90 min
    Highlights (~18,000 frames at 30fps)   → stride-2 → 9,000 frames  → ~10 min
    --max-frames 9000                      → ~10 min any clip
    --max-frames 18000                     → ~20 min any clip  (recommended first run)

Game ID Map
-----------
Fill in the NBA Stats game IDs for each clip.
Find IDs at: https://stats.nba.com/scores/ or use nba_api:
    from nba_api.stats.endpoints import ScoreboardV2
    from nba_api.stats.static import teams

Known IDs are filled in. Clips without IDs run without NBA enrichment
(CV data still collected — enrichment can be added later).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_DIR = Path(__file__).resolve().parent.parent
VIDEOS_DIR  = PROJECT_DIR / "data" / "videos"
RESULTS_DIR = PROJECT_DIR / "data" / "game_results"
MASTER_DIR  = PROJECT_DIR / "data" / "master"
PIPELINE    = PROJECT_DIR / "src" / "pipeline" / "unified_pipeline.py"
COLLECTION_LOG = PROJECT_DIR / "data" / "collection_log.json"

# ── Game ID map ────────────────────────────────────────────────────────────────
# Map clip filename (no extension) → NBA Stats game ID
# Leave as None if unknown — clip will still be processed, just without enrichment.
# Format: "XXXXXXXXXX" (10 digits, starts with 002 for regular season, 004 for playoffs)

GAME_ID_MAP: dict[str, Optional[str]] = {
    # ── 2024-25 Regular Season ────────────────────────────────────────
    "cavs_vs_celtics_2025":  "0022400710",   # Cavs @ Celtics
    "bos_mia_2025":          None,           # TODO: fill in
    "gsw_lakers_2025":       None,           # TODO: fill in
    "mil_chi_2025":          None,           # TODO: fill in
    "den_phx_2025":          None,           # TODO: fill in
    "lal_sas_2025":          None,           # TODO: fill in
    "mem_nop_2025":          None,           # TODO: fill in
    "atl_ind_2025":          None,           # TODO: fill in
    "phi_tor_2025":          None,           # TODO: fill in
    "okc_dal_2025":          None,           # TODO: fill in
    "mia_bkn_2025":          None,           # TODO: fill in
    "sac_por_2025":          None,           # TODO: fill in
    "cavs_broadcast_2025":   None,           # TODO: fill in
    # ── 2023-24 Playoffs ──────────────────────────────────────────────
    "bos_mia_playoffs":      None,           # TODO: fill in (004 prefix)
    "den_gsw_playoffs":      None,           # TODO: fill in (004 prefix)
    # ── Highlights / misc ─────────────────────────────────────────────
    "nba_highlights_gsw":    None,           # highlights reel — no single game ID
    # ── 2016 Finals ───────────────────────────────────────────────────
    "[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors ｜ 2016 NBA Finals Game 7 ｜ NBA on ESPN":
                             "0041500407",   # 2016 Finals Game 7
}

# Processing order — most data-valuable clips first
PRIORITY_ORDER = [
    "cavs_vs_celtics_2025",
    "bos_mia_2025",
    "gsw_lakers_2025",
    "den_phx_2025",
    "okc_dal_2025",
    "mil_chi_2025",
    "lal_sas_2025",
    "bos_mia_playoffs",
    "den_gsw_playoffs",
    "mem_nop_2025",
    "atl_ind_2025",
    "phi_tor_2025",
    "mia_bkn_2025",
    "sac_por_2025",
    "cavs_broadcast_2025",
    "nba_highlights_gsw",
    "[FULL GAME] Cleveland Cavaliers vs. Golden State Warriors ｜ 2016 NBA Finals Game 7 ｜ NBA on ESPN",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clip_stem(video_path: Path) -> str:
    return video_path.stem


def _output_dir(clip_stem: str) -> Path:
    return RESULTS_DIR / clip_stem


def _is_complete(clip_stem: str) -> bool:
    """Return True if this clip already has a completed tracking_data.csv."""
    summary = _output_dir(clip_stem) / "summary.json"
    if not summary.exists():
        return False
    try:
        with open(summary) as f:
            s = json.load(f)
        return s.get("status") == "ok" and s.get("tracking_rows", 0) > 0
    except Exception:
        return False


def _load_log() -> list:
    if COLLECTION_LOG.exists():
        try:
            with open(COLLECTION_LOG) as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _append_log(entry: dict) -> None:
    entries = _load_log()
    entries.append(entry)
    COLLECTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(COLLECTION_LOG, "w") as f:
        json.dump(entries, f, indent=2)


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, newline="") as f:
            return sum(1 for _ in csv.reader(f)) - 1  # subtract header
    except Exception:
        return 0


def _run_clip(
    video_path: Path,
    game_id: Optional[str],
    out_dir: Path,
    max_frames: Optional[int],
) -> dict:
    """Run unified_pipeline on one clip, saving all outputs to out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tracking_csv = out_dir / "tracking_data.csv"

    cmd = [
        sys.executable, str(PIPELINE),
        "--video",   str(video_path),
        "--no-show",
    ]
    if game_id:
        cmd += ["--game-id", game_id]
    if max_frames:
        cmd += ["--frames", str(max_frames)]

    # unified_pipeline writes to data/tracking_data.csv by default.
    # We redirect stdout/stderr and then move the output files after.
    # Cleaner: set CWD so relative paths resolve inside out_dir... but
    # unified_pipeline uses hard-coded DATA=project/data. So we set
    # an env var to override the output path.
    env = os.environ.copy()
    env["TRACKING_OUTPUT_DIR"] = str(out_dir)
    env["TRACKING_DEBUG"] = "1"   # stream output to terminal

    # Clear shared output files before this run so checkpoint appends
    # don't mix this game's data with a prior run's rows.
    data_dir = PROJECT_DIR / "data"
    for fname in [
        "tracking_data.csv", "ball_tracking.csv",
        "possessions.csv", "shot_log.csv", "player_clip_stats.csv",
    ]:
        stale = data_dir / fname
        if stale.exists():
            stale.unlink()

    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"  Clip  : {video_path.name}")
    print(f"  GameID: {game_id or 'None (no enrichment)'}")
    print(f"  Output: {out_dir}")
    print(f"  Frames: {max_frames or 'all'}")
    print(f"{'='*60}")

    result = {
        "clip":        video_path.stem,
        "game_id":     game_id,
        "video_path":  str(video_path),
        "out_dir":     str(out_dir),
        "status":      "error",
        "error":       None,
        "tracking_rows":  0,
        "shot_rows":      0,
        "possession_rows": 0,
        "elapsed_sec":    0,
        "timestamp":   datetime.now(timezone.utc).isoformat(),
    }

    try:
        proc = subprocess.run(
            cmd,
            env=env,
            timeout=7200,   # 2-hour hard cap
        )
        elapsed = round(time.time() - t0, 1)
        result["elapsed_sec"] = elapsed

        if proc.returncode != 0:
            result["error"] = f"Pipeline exit code {proc.returncode}"
        else:
            # Move output files from data/ to out_dir
            for fname in [
                "tracking_data.csv", "ball_tracking.csv",
                "possessions.csv", "shot_log.csv", "player_clip_stats.csv",
            ]:
                src = data_dir / fname
                dst = out_dir / fname
                if src.exists():
                    import shutil
                    shutil.copy2(str(src), str(dst))

            # Count rows
            result["tracking_rows"]   = _count_csv_rows(out_dir / "tracking_data.csv")
            result["shot_rows"]       = _count_csv_rows(out_dir / "shot_log.csv")
            result["possession_rows"] = _count_csv_rows(out_dir / "possessions.csv")
            result["status"] = "ok"

            print(f"\n  Done in {elapsed}s")
            print(f"  Tracking rows : {result['tracking_rows']:,}")
            print(f"  Shots logged  : {result['shot_rows']}")
            print(f"  Possessions   : {result['possession_rows']}")

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout after 7200s"
    except Exception as e:
        result["error"] = str(e)

    # Save per-clip summary
    with open(out_dir / "summary.json", "w") as f:
        json.dump(result, f, indent=2)

    _append_log(result)
    return result


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_all() -> None:
    """Merge all completed game CSVs into master datasets."""
    import csv as _csv

    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    targets = ["tracking_data.csv", "shot_log.csv", "possessions.csv"]

    for fname in targets:
        out_path = MASTER_DIR / fname
        header_written = False
        total_rows = 0

        with open(out_path, "w", newline="") as out_f:
            writer = None
            for clip_dir in sorted(RESULTS_DIR.iterdir()):
                src = clip_dir / fname
                if not src.exists():
                    continue
                with open(src, newline="") as in_f:
                    reader = _csv.DictReader(in_f)
                    rows = list(reader)
                    if not rows:
                        continue
                    if not header_written:
                        writer = _csv.DictWriter(out_f, fieldnames=reader.fieldnames,
                                                  extrasaction="ignore")
                        writer.writeheader()
                        header_written = True

                    # Prefix clip name to possession_id / shot_id to avoid collisions
                    clip_name = clip_dir.name
                    for row in rows:
                        if "possession_id" in row and row["possession_id"]:
                            row["possession_id"] = f"{clip_name}_{row['possession_id']}"
                        if "shot_id" in row and row["shot_id"]:
                            row["shot_id"] = f"{clip_name}_{row['shot_id']}"
                        row["source_clip"] = clip_name
                        writer.writerow(row)
                        total_rows += 1

        print(f"Merged {fname} → {out_path}  ({total_rows:,} rows)")

    print(f"\nMaster dataset ready: {MASTER_DIR}")


# ── Progress report ────────────────────────────────────────────────────────────

def print_status() -> None:
    """Print current collection status."""
    log = _load_log()
    done  = [e for e in log if e["status"] == "ok"]
    failed = [e for e in log if e["status"] != "ok"]

    total_tracking = sum(e.get("tracking_rows", 0) for e in done)
    total_shots    = sum(e.get("shot_rows", 0) for e in done)
    total_poss     = sum(e.get("possession_rows", 0) for e in done)

    print(f"\n{'='*60}")
    print(f"  Collection Status")
    print(f"{'='*60}")
    print(f"  Completed : {len(done)} clips")
    print(f"  Failed    : {len(failed)} clips")
    print(f"  Tracking rows : {total_tracking:,}")
    print(f"  Shots logged  : {total_shots:,}")
    print(f"  Possessions   : {total_poss:,}")
    print(f"{'='*60}")

    if done:
        print("\nCompleted clips:")
        for e in done:
            print(f"  ✓ {e['clip']:<40} {e['tracking_rows']:>8} rows  "
                  f"{e['shot_rows']:>4} shots  {round(e['elapsed_sec']/60, 1):>5}min")
    if failed:
        print("\nFailed clips:")
        for e in failed:
            print(f"  ✗ {e['clip']:<40} {e.get('error', 'unknown')[:50]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Project CourtVision — Batch CV data collection"
    )
    ap.add_argument("--clip",       default=None,
                    help="Process one clip by stem name (e.g. cavs_vs_celtics_2025)")
    ap.add_argument("--max-frames", type=int, default=None,
                    help="Frame cap per clip. Recommended: 18000 (~20min equivalent)")
    ap.add_argument("--force",      action="store_true",
                    help="Re-process clips that are already complete")
    ap.add_argument("--merge-only", action="store_true",
                    help="Skip processing; just merge completed CSVs into master/")
    ap.add_argument("--status",     action="store_true",
                    help="Print collection status and exit")
    args = ap.parse_args()

    if args.status:
        print_status()
        return

    if args.merge_only:
        merge_all()
        return

    # Collect clips to process
    all_clips = {v.stem: v for v in VIDEOS_DIR.glob("*.mp4")}

    if args.clip:
        if args.clip not in all_clips:
            print(f"ERROR: clip '{args.clip}' not found in {VIDEOS_DIR}")
            sys.exit(1)
        clips_to_run = {args.clip: all_clips[args.clip]}
    else:
        # Run in priority order, unknown clips last
        ordered = []
        for stem in PRIORITY_ORDER:
            if stem in all_clips:
                ordered.append((stem, all_clips[stem]))
        for stem, path in sorted(all_clips.items()):
            if stem not in PRIORITY_ORDER:
                ordered.append((stem, path))
        clips_to_run = dict(ordered)

    print(f"\nProject CourtVision — Data Collection")
    print(f"Clips to process: {len(clips_to_run)}")
    print(f"Max frames/clip : {args.max_frames or 'all (full game)'}")
    print(f"Force re-run    : {args.force}")

    results = []
    for stem, video_path in clips_to_run.items():
        if not args.force and _is_complete(stem):
            print(f"\n  SKIP (already complete): {stem}")
            continue

        game_id = GAME_ID_MAP.get(stem)
        out_dir = _output_dir(stem)
        result  = _run_clip(video_path, game_id, out_dir, args.max_frames)
        results.append(result)

        status = "✓" if result["status"] == "ok" else "✗"
        print(f"\n  {status} {stem}  →  "
              f"{result['tracking_rows']:,} rows, "
              f"{result['shot_rows']} shots")

    print("\n" + "="*60)
    print_status()

    # Auto-merge after batch completes
    if not args.clip and any(r["status"] == "ok" for r in results):
        print("\nAuto-merging completed games into master dataset...")
        merge_all()


if __name__ == "__main__":
    main()
