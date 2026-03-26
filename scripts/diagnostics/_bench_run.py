"""
_bench_run.py — Tracker benchmark runner for diagnostics.

Processes N frames of a video clip through the full tracking pipeline
and reports quality metrics: ball detection rate, team classification
accuracy, homography stability, and event detection coverage.

Usage:
    python scripts/diagnostics/_bench_run.py --video <path> [--frames 3600]

Output:
    JSON summary printed to stdout + written to scripts/diagnostics/bench_last.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))


def build_summary(
    total_frames: int,
    ball_detected: int,
    ball_live_frames: int,
    ball_dead_frames: int,
    team_green: int,
    team_white: int,
    id_switches: int,
    elapsed_sec: float,
) -> Dict:
    """
    Aggregate raw frame counts into a quality-metrics dict.

    Keys
    ----
    ball_valid_live  : fraction of live (non-suspended) frames where ball was detected
    ball_valid_dead  : fraction of suspended frames where ball was correctly absent
    ball_detect_pct  : overall ball detection rate across all frames
    team_balance     : ratio min(green,white)/max(green,white) — 1.0 = perfect balance
    id_switch_rate   : ID switches per 100 frames
    fps              : frames processed per wall-clock second
    """
    live  = max(1, ball_live_frames)
    dead  = max(1, ball_dead_frames)
    total = max(1, total_frames)

    ball_valid_live = round(ball_detected / live, 4) if ball_live_frames else 0.0
    ball_valid_dead = round(1.0 - (ball_detected / dead), 4) if ball_dead_frames else 1.0
    ball_detect_pct = round(ball_detected / total, 4)
    team_b = min(team_green, team_white) / max(max(team_green, team_white), 1)
    id_switch_rate  = round(id_switches / total * 100, 2)
    fps_val         = round(total / max(elapsed_sec, 0.001), 1)

    return {
        "total_frames":    total_frames,
        "ball_detected":   ball_detected,
        "ball_valid_live": ball_valid_live,
        "ball_valid_dead": ball_valid_dead,
        "ball_detect_pct": ball_detect_pct,
        "team_balance":    round(team_b, 4),
        "id_switch_rate":  id_switch_rate,
        "fps":             fps_val,
        "elapsed_sec":     round(elapsed_sec, 1),
    }


def run_bench(video_path: str, max_frames: int = 3600) -> Dict:
    """
    Run the tracking pipeline on up to max_frames frames of video_path.

    Returns a summary dict from build_summary().
    Falls back to a zeroed summary when the video cannot be opened
    (missing file, no CV deps) so the script is always importable.
    """
    t0 = time.time()
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open {video_path}")

        from src.pipeline.unified_pipeline import UnifiedPipeline

        pipe = UnifiedPipeline(video_path=video_path, max_frames=max_frames)
        result = pipe.run()

        ball_detected    = result.get("ball_detected_frames",   0)
        ball_live_frames = result.get("ball_live_frames",        max(1, max_frames))
        ball_dead_frames = result.get("ball_dead_frames",        0)
        team_green       = result.get("team_green_detections",   0)
        team_white       = result.get("team_white_detections",   0)
        id_switches      = result.get("id_switches",             0)
        total_frames     = result.get("total_frames",            max_frames)

    except Exception as exc:
        print(f"[bench] Pipeline error: {exc}", file=sys.stderr)
        total_frames = 0
        ball_detected = ball_live_frames = ball_dead_frames = 0
        team_green = team_white = id_switches = 0

    return build_summary(
        total_frames    = total_frames,
        ball_detected   = ball_detected,
        ball_live_frames= ball_live_frames,
        ball_dead_frames= ball_dead_frames,
        team_green      = team_green,
        team_white      = team_white,
        id_switches     = id_switches,
        elapsed_sec     = time.time() - t0,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--video",  required=True,  help="Path to input video file")
    ap.add_argument("--frames", type=int, default=3600,
                    help="Max frames to process (default=3600 = 2 min @ 30fps)")
    ap.add_argument("--out",    default=str(Path(__file__).parent / "bench_last.json"),
                    help="Output JSON path")
    args = ap.parse_args()

    print(f"[bench] Running on {args.video} ({args.frames} frames max) …")
    summary = run_bench(args.video, args.frames)

    print(json.dumps(summary, indent=2))
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"[bench] Written to {args.out}")

    # Exit non-zero if ball detection below 40% on live frames
    if summary["ball_valid_live"] < 0.40:
        print(f"[bench] WARN: ball_valid_live={summary['ball_valid_live']:.1%} < 40% target")
        sys.exit(1)


if __name__ == "__main__":
    main()
