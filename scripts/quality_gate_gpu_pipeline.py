#!/usr/bin/env python3
"""Quality gate: compare GPU pipeline tracking output vs CPU baseline.

Runs on one game and diffs tracking_data.csv:
  - Row count (must not regress >5%)
  - Detection count per frame (must not regress >5%)
  - Track continuity: avg track length (must not regress >5%)

Usage:
    # 1. Run baseline (on master branch):
    python -m src.pipeline.unified_pipeline --video data/videos/full_games/GAME.mp4 \
        --max-frames 300 --output data/tracking/baseline_test/

    # 2. Switch to feat/gpu-pipeline branch and run:
    python -m src.pipeline.unified_pipeline --video data/videos/full_games/GAME.mp4 \
        --max-frames 300 --output data/tracking/gpu_test/

    # 3. Compare:
    python scripts/quality_gate_gpu_pipeline.py \
        data/tracking/baseline_test/tracking_data.csv \
        data/tracking/gpu_test/tracking_data.csv
"""

import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, Tuple

import csv


def load_tracking_csv(path: str) -> Tuple[int, Dict[str, int], Dict[int, int]]:
    """Parse tracking_data.csv → (row_count, detections_per_frame, track_lengths)."""
    rows = 0
    dets_per_frame: Dict[str, int] = defaultdict(int)
    track_frames: Dict[int, int] = defaultdict(int)

    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows += 1
            frame_key = row.get("frame_idx", row.get("frame", ""))
            dets_per_frame[frame_key] += 1
            tid = row.get("track_id", row.get("slot", ""))
            if tid:
                track_frames[int(tid)] += 1

    return rows, dict(dets_per_frame), dict(track_frames)


def compare(baseline_path: str, gpu_path: str, threshold: float = 0.05) -> bool:
    """Compare two tracking CSVs. Returns True if GPU pipeline passes quality gate."""
    b_rows, b_dets, b_tracks = load_tracking_csv(baseline_path)
    g_rows, g_dets, g_tracks = load_tracking_csv(gpu_path)

    b_avg_dets = sum(b_dets.values()) / max(len(b_dets), 1)
    g_avg_dets = sum(g_dets.values()) / max(len(g_dets), 1)

    b_avg_track = sum(b_tracks.values()) / max(len(b_tracks), 1)
    g_avg_track = sum(g_tracks.values()) / max(len(g_tracks), 1)

    def pct_change(baseline: float, gpu: float) -> float:
        if baseline == 0:
            return 0.0
        return (gpu - baseline) / baseline

    metrics = [
        ("Row count", b_rows, g_rows),
        ("Avg detections/frame", b_avg_dets, g_avg_dets),
        ("Avg track length", b_avg_track, g_avg_track),
        ("Unique tracks", len(b_tracks), len(g_tracks)),
        ("Total frames", len(b_dets), len(g_dets)),
    ]

    print(f"\n{'Metric':<25} {'Baseline':>12} {'GPU':>12} {'Change':>10} {'Status':>8}")
    print("-" * 72)

    all_pass = True
    for name, bval, gval in metrics:
        change = pct_change(float(bval), float(gval))
        status = "PASS" if change >= -threshold else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"{name:<25} {bval:>12.1f} {gval:>12.1f} {change:>+9.1%} {status:>8}")

    print("-" * 72)
    print(f"Quality gate: {'PASS' if all_pass else 'FAIL'} (threshold: {threshold:.0%} max regression)")
    return all_pass


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    baseline = sys.argv[1]
    gpu = sys.argv[2]

    for p in (baseline, gpu):
        if not Path(p).exists():
            print(f"ERROR: {p} not found")
            sys.exit(1)

    passed = compare(baseline, gpu)
    sys.exit(0 if passed else 1)
