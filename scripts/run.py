"""
run.py — NBA AI System entry point

Usage:
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system

    python run.py                                        # track with Hough fallback
    python run.py --yolo src/detection/model_weights/x.pth  # use YOLO-NAS for ball
    python run.py --frames 100 --debug                   # 100 frames + trail debug
    python run.py --eval                                 # print tracking metrics
    python run.py --no-show                              # headless (faster)

Outputs:
    data/tracking_data.csv   — per-frame player positions + possession + confidence
    data/stats.json          — per-player shot attempts + made baskets (YOLO mode)
    data/debug_tracking.mp4  — annotated video (--debug)
"""

import argparse
import os
import sys

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from src.pipeline.unified_pipeline import UnifiedPipeline
from src.tracking import (
    evaluate_tracking, visualize_tracking,
    auto_correct_tracking, run_self_test,
)

RESOURCES     = os.path.join(PROJECT_DIR, "resources")
DEFAULT_VIDEO = os.path.join(PROJECT_DIR, "data", "videos", "bos_mia_2025.mp4")


def main():
    ap = argparse.ArgumentParser(description="NBA AI Basketball Tracker")
    ap.add_argument("--video",   default=DEFAULT_VIDEO,
                    help="Path to input video (.mp4)")
    ap.add_argument("--yolo",    default=None,
                    help="Path to YOLO-NAS weights (.pth). Enables ball/rim/shot detection.")
    ap.add_argument("--frames",  type=int, default=None,
                    help="Max frames to process (default: full video)")
    ap.add_argument("--start-frame", type=int, default=0,
                    help="Frame index to seek to before processing (default: 0)")
    ap.add_argument("--debug",   action="store_true",
                    help="Save annotated debug video with player trails")
    ap.add_argument("--eval",    action="store_true",
                    help="Print tracking quality metrics after run")
    ap.add_argument("--no-show",   action="store_true",
                    help="Disable live window (faster)")
    ap.add_argument("--self-test", action="store_true",
                    help="Run full self-test: track → evaluate → auto-correct → re-evaluate")
    ap.add_argument("--correct",   action="store_true",
                    help="Apply auto-correction to tracking output before saving")
    args = ap.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: video not found at {args.video}")
        sys.exit(1)

    # Quick path: self-test mode
    if args.self_test:
        run_self_test(
            video_path=args.video,
            max_frames=args.frames or 200,
            yolo_weight_path=args.yolo,
        )
        return

    mode = "YOLO-NAS + AdvancedFeetDetector" if args.yolo else "Hough+CSRT + AdvancedFeetDetector"
    print(f"\n=== NBA AI Tracking System ===")
    print(f"Video:   {args.video}")
    print(f"Mode:    {mode}")
    print(f"Output:  data/tracking_data.csv  +  data/stats.json")
    print()

    debug_out = os.path.join(PROJECT_DIR, "data", "debug_tracking.mp4") if args.debug else None

    pipeline = UnifiedPipeline(
        video_path=args.video,
        yolo_weight_path=args.yolo,
        max_frames=args.frames,
        start_frame=args.start_frame,
        show=not args.no_show,
        output_video_path=debug_out,
    )

    results = pipeline.run()

    print(f"\n=== Results ===")
    print(f"Frames processed:      {results['total_frames']}")
    print(f"Estimated ID switches: {results['id_switches']}")
    print(f"Track stability:       {results['stability']}")

    if results["stats"]:
        print(f"\nPlayer stats (shots attempted / made):")
        for player_key, s in results["stats"].items():
            print(f"  {player_key}: {s.get('attempts', 0)} attempts, {s.get('made', 0)} made")

    if args.correct:
        print("\nAuto-correcting tracking output...")
        correction = auto_correct_tracking(results["predictions"])
        results["predictions"] = correction["predictions"]
        print(f"  Jumps fixed:       {correction['jumps_fixed']}")
        print(f"  Tracks smoothed:   {correction['smoothed']}")
        print(f"  Duplicates removed:{correction['duplicates_removed']}")

    if args.eval:
        print("\nTracking quality (self-consistency):")
        metrics = evaluate_tracking(results["predictions"])
        for k, v in metrics.items():
            if k not in ("self_evaluation", "note"):
                print(f"  {k}: {v}")

    if args.debug:
        print(f"\nDebug video → {debug_out}")

    print("\nDone.")


if __name__ == "__main__":
    main()

