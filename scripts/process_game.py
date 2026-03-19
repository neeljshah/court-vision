"""
process_game.py — Automate full-game processing across multiple clips/quarters.

Runs the full pipeline (tracking → features → NBA enrichment) for each clip,
saves outputs to data/games/<game_id>/q<N>/, then merges all quarters into a
single game-level dataset.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    # One clip per quarter (most common)
    python process_game.py --game-id 0022301234 \\
      --clips "q1.mp4:1:0" "q2.mp4:2:0" "q3.mp4:3:0" "q4.mp4:4:0"

    # With custom start offsets (e.g. clip starts 3 min into Q2)
    python process_game.py --game-id 0022301234 \\
      --clips "q1_full.mp4:1:0" "q2_clip.mp4:2:180"

    # From a JSON manifest (easier for batch scheduling)
    python process_game.py --game-id 0022301234 --manifest clips.json

    # Headless + re-use cached court calibration
    python process_game.py --game-id 0022301234 \\
      --clips "q1.mp4:1:0" "q2.mp4:2:0" --no-show

Manifest JSON format (--manifest)
----------------------------------
    [
      {"path": "q1.mp4", "period": 1, "start": 0},
      {"path": "q2.mp4", "period": 2, "start": 0}
    ]

Outputs
-------
    data/games/<game_id>/
        q<N>/                 Per-quarter CSVs (tracking, ball, possessions, etc.)
        game_tracking.csv     All quarters merged (tracking_data)
        game_features.csv     All quarters merged (features)
        game_shots.csv        All quarters merged (shot_log_enriched or shot_log)
        game_possessions.csv  All quarters merged (possessions_enriched or possessions)
        manifest.json         Processing log (what ran, when, outcomes)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from typing import List, Optional

import pandas as pd

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.features.feature_engineering import run as run_features

# ── Constants ──────────────────────────────────────────────────────────────────

_DATA_DIR  = os.path.join(PROJECT_DIR, "data")          # shared pipeline output dir
_GAMES_DIR = os.path.join(_DATA_DIR, "games")           # per-game output root

# CSVs written by UnifiedPipeline / run_features into _DATA_DIR
_CLIP_OUTPUTS = [
    "tracking_data.csv",
    "ball_tracking.csv",
    "possessions.csv",
    "shot_log.csv",
    "player_clip_stats.csv",
    "features.csv",
    "stats.json",
    # enriched variants (written only when --game-id given to nba_enricher)
    "shot_log_enriched.csv",
    "possessions_enriched.csv",
]

# Which CSVs to merge across quarters for the game-level dataset
_MERGE_MAP = {
    "game_tracking.csv":    ["tracking_data.csv"],
    "game_features.csv":    ["features.csv"],
    "game_shots.csv":       ["shot_log_enriched.csv", "shot_log.csv"],      # prefer enriched
    "game_possessions.csv": ["possessions_enriched.csv", "possessions.csv"],
}


# ── Clip spec parsing ──────────────────────────────────────────────────────────

def parse_clip_spec(spec: str) -> dict:
    """
    Parse a clip spec string: "path/to/video.mp4:period:start_sec"

    Args:
        spec: Colon-separated string — path, period, optional start_sec.

    Returns:
        {"path": str, "period": int, "start": float}

    Raises:
        ValueError: if format is invalid.
    """
    parts = spec.rsplit(":", 2)
    if len(parts) == 3:
        path_part, period_part, start_part = parts
    elif len(parts) == 2:
        path_part, period_part = parts
        start_part = "0"
    else:
        raise ValueError(
            f"Invalid clip spec '{spec}'. "
            "Expected format: video.mp4:period:start_sec  (e.g. q1.mp4:1:0)"
        )
    return {
        "path":   path_part,
        "period": int(period_part),
        "start":  float(start_part),
    }


def load_manifest(manifest_path: str) -> List[dict]:
    """Load clip list from a JSON manifest file."""
    with open(manifest_path) as f:
        clips = json.load(f)
    required = {"path", "period"}
    for i, c in enumerate(clips):
        missing = required - c.keys()
        if missing:
            raise ValueError(f"Manifest entry {i} missing fields: {missing}")
        c.setdefault("start", 0.0)
    return clips


# ── Per-clip processing ────────────────────────────────────────────────────────

def process_clip(
    clip: dict,
    game_id: str,
    show: bool = True,
    max_frames: Optional[int] = None,
) -> dict:
    """
    Run the full pipeline for a single clip and snapshot outputs to the game dir.

    Args:
        clip:       {"path": str, "period": int, "start": float}
        game_id:    NBA Stats game ID string.
        show:       Whether to show the live preview window.
        max_frames: Cap on frames to process (None = full clip).

    Returns:
        Result dict with keys: period, success, error, out_dir, n_frames, stability.
    """
    period = clip["period"]
    video_path = clip["path"]
    start_sec  = clip.get("start", 0.0)

    out_dir = os.path.join(_GAMES_DIR, game_id, f"q{period}")
    result = {
        "period":    period,
        "video":     video_path,
        "start_sec": start_sec,
        "out_dir":   out_dir,
        "success":   False,
        "error":     None,
        "n_frames":  0,
        "stability": 0.0,
    }

    if not os.path.exists(video_path):
        result["error"] = f"Video not found: {video_path}"
        return result

    # Skip if already processed (all core CSVs present)
    core_files = ["tracking_data.csv", "features.csv"]
    if all(os.path.exists(os.path.join(out_dir, f)) for f in core_files):
        print(f"\n  Q{period} already processed — skipping. Delete {out_dir} to rerun.")
        result["success"] = True
        result["skipped"] = True
        return result

    os.makedirs(out_dir, exist_ok=True)

    # ── Stage 1: Tracking ──────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f" Q{period} — Stage 1 / 3 — Tracking")
    print(f"{'='*60}")
    print(f" Video : {video_path}")

    try:
        pipeline = UnifiedPipeline(
            video_path=video_path,
            yolo_weight_path=None,
            max_frames=max_frames,
            show=show,
        )
        tracking_results = pipeline.run()
    except Exception as e:
        result["error"] = f"Tracking failed: {e}"
        return result

    fps = pipeline.stats_tracker.fps if hasattr(pipeline, "stats_tracker") else 30.0
    result["n_frames"]  = tracking_results["total_frames"]
    result["stability"] = tracking_results["stability"]

    print(f"\n Frames     : {result['n_frames']}")
    print(f" Stability  : {result['stability']:.3f}")
    print(f" ID switches: {tracking_results['id_switches']}")

    # ── Stage 2: Feature engineering ──────────────────────────────────────────
    print(f"\n Q{period} — Stage 2 / 3 — Feature Engineering")
    try:
        run_features(
            input_path=os.path.join(_DATA_DIR, "tracking_data.csv"),
            output_path=os.path.join(_DATA_DIR, "features.csv"),
        )
    except Exception as e:
        print(f"  ⚠  Feature engineering failed: {e}")

    # ── Stage 3: NBA enrichment ────────────────────────────────────────────────
    print(f"\n Q{period} — Stage 3 / 3 — NBA Enrichment")
    try:
        from src.data.nba_enricher import enrich
        enrich(
            game_id=game_id,
            period=period,
            clip_start_sec=start_sec,
            fps=fps,
            data_dir=_DATA_DIR,
        )
    except Exception as e:
        print(f"  ⚠  NBA enrichment failed: {e}")
        print("  (Tracking data is still complete — enrichment is optional)")

    # ── Snapshot outputs to game dir ───────────────────────────────────────────
    for fname in _CLIP_OUTPUTS:
        src = os.path.join(_DATA_DIR, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, fname))

    result["success"] = True
    return result


# ── Quarter merging ────────────────────────────────────────────────────────────

def merge_quarters(game_id: str) -> dict:
    """
    Concatenate per-quarter CSVs into game-level files.

    Args:
        game_id: NBA Stats game ID.

    Returns:
        Dict of {output_filename: row_count} for files that were written.
    """
    game_dir = os.path.join(_GAMES_DIR, game_id)
    written  = {}

    # Find all quarter output dirs, sorted
    q_dirs = sorted(
        d for d in os.listdir(game_dir)
        if d.startswith("q") and os.path.isdir(os.path.join(game_dir, d))
    )

    for out_name, candidates in _MERGE_MAP.items():
        frames = []
        for q_dir in q_dirs:
            period_num = int(q_dir[1:])  # "q2" -> 2
            for fname in candidates:
                path = os.path.join(game_dir, q_dir, fname)
                if os.path.exists(path):
                    try:
                        df = pd.read_csv(path)
                        df.insert(0, "period", period_num)  # tag each row with quarter
                        frames.append(df)
                    except Exception:
                        pass
                    break  # found the preferred file for this quarter

        if not frames:
            continue

        merged = pd.concat(frames, ignore_index=True)
        out_path = os.path.join(game_dir, out_name)
        merged.to_csv(out_path, index=False)
        written[out_name] = len(merged)

    return written


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="NBA AI — automate full-game processing across quarters"
    )
    ap.add_argument("--game-id",  required=True,
                    help="NBA Stats game ID (e.g. 0022301234)")
    ap.add_argument("--clips",    nargs="+", default=[],
                    help="Clip specs: 'video.mp4:period:start_sec' (e.g. q1.mp4:1:0)")
    ap.add_argument("--manifest", default=None,
                    help="JSON file with clip list (alternative to --clips)")
    ap.add_argument("--no-show",  action="store_true",
                    help="Disable live preview windows (faster, for headless runs)")
    ap.add_argument("--frames",   type=int, default=None,
                    help="Max frames per clip (default: full clip; useful for testing)")
    args = ap.parse_args()

    # ── Resolve clip list ──────────────────────────────────────────────────────
    clips: List[dict] = []
    if args.manifest:
        clips = load_manifest(args.manifest)
    elif args.clips:
        for spec in args.clips:
            clips.append(parse_clip_spec(spec))
    else:
        ap.error("Provide --clips or --manifest")

    if not clips:
        ap.error("No clips to process.")

    print(f"\n{'='*60}")
    print(f" Game: {args.game_id}   Clips: {len(clips)}")
    print(f"{'='*60}")
    for c in clips:
        print(f"  Q{c['period']}  {c['path']}  (start {c['start']}s)")

    game_dir = os.path.join(_GAMES_DIR, args.game_id)
    os.makedirs(game_dir, exist_ok=True)

    t_game_start = time.time()
    run_log = []

    # ── Process each clip ──────────────────────────────────────────────────────
    for clip in clips:
        t0 = time.time()
        result = process_clip(
            clip=clip,
            game_id=args.game_id,
            show=not args.no_show,
            max_frames=args.frames,
        )
        result["elapsed_s"] = round(time.time() - t0, 1)
        run_log.append(result)

        status = "✓" if result["success"] else "✗"
        skip   = " (skipped)" if result.get("skipped") else ""
        print(f"\n {status} Q{result['period']}{skip}  "
              f"{result['n_frames']} frames  "
              f"stability={result['stability']:.3f}  "
              f"{result['elapsed_s']}s")
        if result["error"]:
            print(f"   Error: {result['error']}")

    # ── Merge quarters ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(" Merging quarters into game-level dataset...")
    print(f"{'='*60}")
    merged = merge_quarters(args.game_id)
    for fname, n_rows in merged.items():
        print(f"  ✓  {fname:<30}  ({n_rows} rows)")

    # ── Save run manifest ──────────────────────────────────────────────────────
    manifest_out = os.path.join(game_dir, "manifest.json")
    with open(manifest_out, "w") as f:
        json.dump({
            "game_id":      args.game_id,
            "processed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "clips":        run_log,
            "merged_files": merged,
        }, f, indent=2)

    # ── Summary ────────────────────────────────────────────────────────────────
    total_elapsed = time.time() - t_game_start
    n_ok    = sum(1 for r in run_log if r["success"])
    n_fail  = len(run_log) - n_ok
    n_frames_total = sum(r["n_frames"] for r in run_log)

    print(f"\n{'='*60}")
    print(f" Game {args.game_id} — Done")
    print(f"{'='*60}")
    print(f"  Clips processed : {n_ok}/{len(run_log)}"
          + (f"  ({n_fail} failed)" if n_fail else ""))
    print(f"  Total frames    : {n_frames_total:,}")
    print(f"  Output dir      : {game_dir}")
    print(f"  Total time      : {total_elapsed:.0f}s")
    if n_fail:
        print("\n Failed clips:")
        for r in run_log:
            if not r["success"]:
                print(f"    Q{r['period']}: {r['error']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
