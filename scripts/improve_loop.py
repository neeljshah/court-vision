"""
improve_loop.py — Self-improving tracker loop.

Repeatedly runs the tracker, scores output quality, hill-climbs on parameters,
and logs every run to data/improvement_runs.csv.

Usage:
    python improve_loop.py                      # 20 iterations, 500 frames/run
    python improve_loop.py --iters 40 --frames 1000
    python improve_loop.py --reset              # reset params to defaults and start fresh
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_DIR)

from src.tracking.tracker_config import DEFAULTS, load_config, save_config

LOG_PATH    = Path(PROJECT_DIR) / "data" / "improvement_runs.csv"
VIDEOS_DIR  = Path(PROJECT_DIR) / "data" / "videos"
VIDEO_EXTS  = {".mp4", ".mkv", ".avi", ".mov"}

# ── Search space ──────────────────────────────────────────────────────────────
# Each key maps to an ordered list of candidates (low → high).
# Hill-climbing tries neighbours of the current value first.

SEARCH_SPACE: Dict[str, List[Any]] = {
    "conf_threshold":        [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45],
    "topcut":                [0, 50, 100, 150, 200, 250, 320, 400],
    "appearance_w":          [0.1, 0.2, 0.25, 0.35, 0.5, 0.65],
    "max_lost_frames":       [30, 60, 90, 120, 150],
    "min_gameplay_persons":  [3, 4, 5, 6],
}

# Which param to search based on diagnosis
DIAGNOSIS_PARAMS = {
    "low_detection":  ["conf_threshold", "topcut"],
    "low_coverage":   ["conf_threshold", "min_gameplay_persons"],
    "high_switches":  ["appearance_w", "max_lost_frames"],
    "duplicates":     ["conf_threshold", "appearance_w"],
    "ok":             list(SEARCH_SPACE.keys()),
}


# ── Scoring ───────────────────────────────────────────────────────────────────

def score(m: Dict) -> float:
    """Composite score in [0, 1]. Higher is better."""
    total    = max(m.get("total_frames", 1), 1)
    players  = min(m.get("avg_players_per_frame", 0) / 9.0, 1.0)
    stab     = m.get("track_stability", 0.0)
    low_cov  = m.get("low_coverage_frames", total) / total
    sw_rate  = m.get("id_switches_estimated", total) / total
    return players * 0.45 + stab * 0.30 + (1.0 - low_cov) * 0.20 - sw_rate * 0.05


def diagnose(m: Dict) -> str:
    """Map metrics to a failure mode label."""
    total   = max(m.get("total_frames", 1), 1)
    avg     = m.get("avg_players_per_frame", 0)
    low_cov = m.get("low_coverage_frames", total) / total
    sw_rate = m.get("id_switches_estimated", total) / total
    dup_rt  = m.get("duplicate_detections", 0) / total

    if avg < 2.0:
        return "low_detection"
    if low_cov > 0.4:
        return "low_coverage"
    if sw_rate > 0.03:
        return "high_switches"
    if dup_rt > 0.05:
        return "duplicates"
    return "ok"


# ── Tracker execution ─────────────────────────────────────────────────────────

def run_tracker(video: Path, frames: int, params: Dict) -> Dict:
    """
    Write params to config, patch module-level constants, run tracker in-process.
    Returns evaluate_tracking metrics dict.
    """
    save_config(params)

    # Patch module-level constants that aren't read at instance-creation time
    import src.pipeline.unified_pipeline as up_mod
    import src.tracking.video_handler    as vh_mod
    up_mod.TOPCUT               = params["topcut"]
    vh_mod.TOPCUT               = params["topcut"]
    up_mod.MIN_GAMEPLAY_PERSONS = params["min_gameplay_persons"]

    from src.tracking.evaluate import evaluate_tracking, track_video
    results = track_video(str(video), max_frames=frames, show=False)
    return evaluate_tracking(results["predictions"])


# ── Logging ───────────────────────────────────────────────────────────────────

_LOG_FIELDS = [
    "timestamp", "iteration", "video", "score", "diagnosis",
    "avg_players", "stability", "id_switches", "low_coverage",
] + list(SEARCH_SPACE.keys())


def log_run(
    iteration: int,
    video: str,
    s: float,
    diagnosis: str,
    metrics: Dict,
    params: Dict,
):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=_LOG_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow({
            "timestamp":   datetime.now().isoformat(timespec="seconds"),
            "iteration":   iteration,
            "video":       video,
            "score":       round(s, 4),
            "diagnosis":   diagnosis,
            "avg_players": metrics.get("avg_players_per_frame", 0),
            "stability":   metrics.get("track_stability", 0),
            "id_switches": metrics.get("id_switches_estimated", 0),
            "low_coverage":metrics.get("low_coverage_frames", 0),
            **{k: params.get(k) for k in SEARCH_SPACE},
        })


# ── Neighbour search ──────────────────────────────────────────────────────────

def neighbours(param: str, current_val: Any) -> List[Any]:
    """Return candidates adjacent to current_val in the search space, then the rest."""
    space = SEARCH_SPACE.get(param, [])
    if current_val not in space:
        return space
    idx = space.index(current_val)
    ordered = []
    for step in (1, -1, 2, -2, 3, -3):
        ni = idx + step
        if 0 <= ni < len(space):
            ordered.append(space[ni])
    for v in space:
        if v not in ordered and v != current_val:
            ordered.append(v)
    return ordered


# ── Main loop ─────────────────────────────────────────────────────────────────

def get_videos() -> List[Path]:
    if not VIDEOS_DIR.exists():
        return []
    return [p for p in sorted(VIDEOS_DIR.iterdir()) if p.suffix.lower() in VIDEO_EXTS]


def improve(iterations: int = 20, frames: int = 500, reset: bool = False):
    """Run the improvement loop."""
    videos = get_videos()
    if not videos:
        print(f"No videos found in {VIDEOS_DIR}")
        sys.exit(1)

    params = DEFAULTS.copy() if reset else load_config()
    save_config(params)

    print(f"Videos: {[v.name for v in videos]}")
    print(f"Starting params: {params}\n")

    # ── Baseline ──────────────────────────────────────────────────────────────
    video = videos[0]
    print(f"[Baseline] {video.name}, {frames} frames...")
    metrics    = run_tracker(video, frames, params)
    best_score = score(metrics)
    diag       = diagnose(metrics)
    log_run(0, video.name, best_score, diag, metrics, params)

    print(f"  score={best_score:.4f}  players={metrics.get('avg_players_per_frame', 0):.2f}"
          f"  stability={metrics.get('track_stability', 0):.4f}  diagnosis={diag}")

    # ── Hill-climbing iterations ───────────────────────────────────────────────
    no_improve_streak = 0

    for it in range(1, iterations + 1):
        diag        = diagnose(metrics)
        target_keys = DIAGNOSIS_PARAMS.get(diag, list(SEARCH_SPACE.keys()))
        vid         = videos[it % len(videos)]

        print(f"\n[Iter {it:02d}] diagnosis={diag}  video={vid.name}")

        improved = False
        for param in target_keys:
            for candidate in neighbours(param, params[param]):
                test_params = {**params, param: candidate}
                m           = run_tracker(vid, frames, test_params)
                s           = score(m)
                log_run(it, vid.name, s, diagnose(m), m, test_params)

                delta = s - best_score
                print(f"  {param}={candidate}: score={s:.4f}  players={m.get('avg_players_per_frame',0):.2f}"
                      f"  delta={delta:+.4f}")

                if s > best_score + 1e-4:
                    best_score = s
                    params     = test_params
                    metrics    = m
                    improved   = True
                    print(f"  ✓ Improved → {param}={candidate}  best={best_score:.4f}")
                    break  # greedy: take first improvement, move to next iteration

            if improved:
                break

        if improved:
            no_improve_streak = 0
            save_config(params)
        else:
            no_improve_streak += 1
            print(f"  No improvement (streak={no_improve_streak})")
            # On a stale streak, re-evaluate on a different video to avoid local minima
            if no_improve_streak >= 3 and len(videos) > 1:
                vid     = videos[(it + 1) % len(videos)]
                metrics = run_tracker(vid, frames, params)
                print(f"  Re-evaluated on {vid.name}: score={score(metrics):.4f}")

        if no_improve_streak >= 6:
            print("\nConverged (6 consecutive iterations without improvement). Stopping.")
            break

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print(f"Best score:   {best_score:.4f}")
    print(f"Best params:  {params}")
    print(f"Log:          {LOG_PATH}")
    save_config(params)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters",  type=int, default=20,  help="Max iterations")
    ap.add_argument("--frames", type=int, default=500, help="Frames per tracker run")
    ap.add_argument("--reset",  action="store_true",   help="Reset params to defaults")
    args = ap.parse_args()
    improve(iterations=args.iters, frames=args.frames, reset=args.reset)
