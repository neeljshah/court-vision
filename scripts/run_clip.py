"""
run_clip.py — Full data-extraction pipeline for a 5-minute basketball clip.

Runs every stage end-to-end and prints a summary of all output files.

Usage
-----
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    # Basic — just tracking data
    python run_clip.py --video path/to/clip.mp4

    # With NBA enrichment (adds made/missed labels + possession outcomes)
    python run_clip.py --video clip.mp4 --game-id 0022301234 --period 2 --start 420

    # Headless (no preview window, faster)
    python run_clip.py --video clip.mp4 --no-show

    # Limit frames (useful for quick tests)
    python run_clip.py --video clip.mp4 --frames 500

Outputs (written to data/)
--------------------------
    tracking_data.csv       Per-frame rows for every tracked player (36 cols)
    ball_tracking.csv       Per-frame ball position + detection flag
    possessions.csv         One row per possession with aggregate stats
    shot_log.csv            One row per detected shot attempt
    player_clip_stats.csv   Per-player aggregate stats across the clip
    features.csv            ML-ready features (rolling windows, momentum, etc.)
    stats.json              Shot attempts + made baskets (YOLO mode only)

    If --game-id is provided, also writes:
    shot_log_enriched.csv       shot_log with made/missed from NBA API
    possessions_enriched.csv    possessions with result + score_diff from NBA API
"""

import argparse
import json
import os
import sys
import time
import uuid

import cv2

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.features.feature_engineering import run as run_features

try:
    from src.tracking.player_identity import (
        JerseyVotingBuffer,
        run_ocr_annotation_pass,
        SAMPLE_EVERY_N,
    )
    from src.data.player_identity import persist_identity_map, update_tracking_frames
    _HAS_IDENTITY = True
except ImportError:
    _HAS_IDENTITY = False


MIN_CLIP_SECONDS = 60  # clips under this are too short for meaningful analytics


def _fmt_rows(path: str) -> str:
    """Return '(N rows)' or '(not found)' for a CSV path."""
    if not os.path.exists(path):
        return "(not found)"
    with open(path) as f:
        n = sum(1 for _ in f) - 1  # subtract header
    return f"({max(0, n)} rows)"


def _fmt_size(path: str) -> str:
    if not os.path.exists(path):
        return "(not found)"
    kb = os.path.getsize(path) / 1024
    return f"({kb:.1f} KB)"


def main():
    ap = argparse.ArgumentParser(
        description="NBA AI — full data extraction pipeline for a single clip"
    )
    ap.add_argument("--video",    required=True,
                    help="Path to input video (.mp4)")
    ap.add_argument("--yolo",     default=None,
                    help="Path to YOLO-NAS weights (.pth). Optional.")
    ap.add_argument("--frames",      type=int, default=None,
                    help="Max frames to process (default: full video)")
    ap.add_argument("--start-frame", type=int, default=0,
                    help="Frame index to seek to before processing (default: 0)")
    ap.add_argument("--no-show",  action="store_true",
                    help="Disable live preview window")
    # NBA enrichment (optional)
    ap.add_argument("--game-id",  default=None,
                    help="NBA Stats game ID (e.g. 0022301234) for play-by-play enrichment")
    ap.add_argument("--period",   type=int, default=1,
                    help="Quarter the clip covers (1-4). Used with --game-id.")
    ap.add_argument("--start",    type=float, default=0.0,
                    help="Seconds elapsed in the period when the clip starts. "
                         "e.g. clip starts at 8:30 left in Q1 → --start 210")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: video not found at {args.video}")
        sys.exit(1)

    cap_check = cv2.VideoCapture(args.video)
    total_frames_check = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_check = cap_check.get(cv2.CAP_PROP_FPS) or 30.0
    cap_check.release()
    clip_duration_sec = total_frames_check / fps_check
    if clip_duration_sec < MIN_CLIP_SECONDS:
        print(
            f"\nWARNING: Clip is only {clip_duration_sec:.1f}s "
            f"(minimum recommended: {MIN_CLIP_SECONDS}s).\n"
            "Short clips produce unreliable shot/possession analytics.\n"
            "Pass --frames to process a subset, or use a longer broadcast clip.\n"
        )
        # Exit with non-zero so automated pipelines can detect short clips.
        sys.exit(2)

    data_dir = os.path.join(PROJECT_DIR, "data")
    t0 = time.time()

    # ── Stage 1: Tracking ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" Stage 1 / 3 — Tracking")
    print("=" * 60)
    print(f" Video : {args.video}")

    pipeline = UnifiedPipeline(
        video_path=args.video,
        yolo_weight_path=args.yolo,
        max_frames=args.frames,
        start_frame=args.start_frame,
        show=not args.no_show,
    )
    results = pipeline.run()

    fps = pipeline.stats_tracker.fps if hasattr(pipeline, "stats_tracker") else 30.0

    print(f"\n Frames processed : {results['total_frames']}")
    print(f" Track stability  : {results['stability']:.3f}")
    print(f" Est. ID switches : {results['id_switches']}")

    # ── Stage 2: Feature engineering ─────────────────────────────────────────
    print("\n" + "=" * 60)
    print(" Stage 2 / 3 — Feature Engineering")
    print("=" * 60)
    features_df = run_features(
        input_path=os.path.join(data_dir, "tracking_data.csv"),
        output_path=os.path.join(data_dir, "features.csv"),
    )

    # ── Stage 3: NBA enrichment (optional) ───────────────────────────────────
    enriched = {}
    if args.game_id:
        print("\n" + "=" * 60)
        print(" Stage 3 / 3 — NBA API Enrichment")
        print("=" * 60)
        try:
            from src.data.nba_enricher import enrich
            enriched = enrich(
                game_id=args.game_id,
                period=args.period,
                clip_start_sec=args.start,
                fps=fps,
                data_dir=data_dir,
            )
        except Exception as e:
            print(f"  NBA enrichment failed: {e}")
            print("  (Tracking data is still complete — enrichment is optional)")
    else:
        print("\n Stage 3 / 3 — NBA Enrichment skipped (no --game-id)")
        print("  Run later: python -m src.data.nba_enricher "
              "--game-id <ID> --period <P> --start <secs>")

    # ── OCR identity annotation pass ──────────────────────────────────────────
    if _HAS_IDENTITY and args.game_id:
        db_url = os.environ.get("DATABASE_URL")
        clip_id = str(uuid.uuid4())

        print("\n" + "=" * 60)
        print(" Stage 4 / 4 — OCR Identity Annotation")
        print("=" * 60)
        print("[run_clip] Running OCR annotation pass...")
        buf = JerseyVotingBuffer()

        # player_crops is a dict {slot: crop_bgr} saved during the tracking loop.
        # If the pipeline exposes crops, use them; otherwise pass an empty dict
        # and let run_ocr_annotation_pass skip gracefully (no crops = no OCR reads).
        player_crops: dict = getattr(results, "player_crops", {})

        # run_ocr_annotation_pass expects a frame and frame_index.
        # Since we are in post-processing mode (no live frame), pass a dummy frame
        # at frame_index=0 so SAMPLE_EVERY_N triggers (0 % N == 0).
        import numpy as np
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        confirmed = run_ocr_annotation_pass(
            frame=dummy_frame,
            player_crops=player_crops,
            frame_index=0,
            buffer=buf,
        )

        if db_url and confirmed:
            print(f"[run_clip] Persisting {len(confirmed)} confirmed identities...")
            for slot, jersey_number in confirmed.items():
                persist_identity_map(
                    db_url=db_url,
                    game_id=args.game_id,
                    clip_id=clip_id,
                    slot=slot,
                    jersey_number=jersey_number,
                    player_id=None,   # player_id resolved from roster lookup downstream
                    confirmed_frame=0,
                    confidence=1.0,
                )
            rows_updated = update_tracking_frames(
                db_url=db_url,
                game_id=args.game_id,
                clip_id=clip_id,
            )
            print(f"[run_clip] Updated {rows_updated} tracking_frames rows with player_id")
        elif not db_url:
            print("[run_clip] DATABASE_URL not set — skipping identity persistence")
        else:
            print("[run_clip] No confirmed jersey identities in this clip")
    # ── end OCR annotation pass ───────────────────────────────────────────────

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(" Output Summary")
    print("=" * 60)

    outputs = [
        ("tracking_data.csv",     "Per-frame player data (36 cols)"),
        ("ball_tracking.csv",     "Per-frame ball position"),
        ("possessions.csv",       "Per-possession aggregate stats"),
        ("shot_log.csv",          "Per-shot attempt log"),
        ("player_clip_stats.csv", "Per-player clip aggregates"),
        ("features.csv",          "ML-ready engineered features"),
    ]
    if results.get("stats"):
        outputs.append(("stats.json", "Shot attempts + made (YOLO mode)"))
    if enriched.get("shot_log_enriched"):
        outputs.append(("shot_log_enriched.csv",     "Shot log + made/missed (NBA API)"))
    if enriched.get("possessions_enriched"):
        outputs.append(("possessions_enriched.csv",  "Possessions + result + score_diff"))

    for fname, desc in outputs:
        path = os.path.join(data_dir, fname)
        if fname.endswith(".csv"):
            tag = _fmt_rows(path)
        else:
            tag = _fmt_size(path)
        exists = "✓" if os.path.exists(path) else "✗"
        print(f"  {exists}  {fname:<30}  {tag:<12}  {desc}")

    # ML readiness
    td_path = os.path.join(data_dir, "tracking_data.csv")
    fe_path = os.path.join(data_dir, "features.csv")
    n_frames = results["total_frames"]
    n_cols   = len(features_df.columns) if features_df is not None else "?"

    print(f"\n ML Dataset")
    print(f"  features.csv : {_fmt_rows(fe_path)}  {n_cols} columns")
    print(f"  Frames        : {n_frames}  "
          f"({n_frames / max(1, fps):.0f}s @ {fps:.0f}fps)")
    if args.game_id:
        poss_path = os.path.join(data_dir, "possessions_enriched.csv")
        print(f"  possessions   : {_fmt_rows(poss_path)} labeled rows "
              f"(team / result / score_diff) — train your model here")
        shot_path = os.path.join(data_dir, "shot_log_enriched.csv")
        print(f"  shot_log      : {_fmt_rows(shot_path)} labeled rows "
              f"(zone / quality / made) — shot-quality model target")
    else:
        print("  Run with --game-id to add outcome labels for ML training.")

    print(f"\n Total time: {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
