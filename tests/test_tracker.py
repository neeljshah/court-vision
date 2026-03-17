"""
tests/test_tracker.py — Automated tracking reliability test

Usage:
    conda activate basketball_ai
    cd C:/Users/neelj/nba-ai-system
    python tests/test_tracker.py
    python tests/test_tracker.py --video path/to/clip.mp4 --frames 200
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_env = os.environ.get("CONDA_DEFAULT_ENV", "")
if _env != "basketball_ai":
    print(
        f"ERROR: wrong environment ('{_env}').\n"
        "Run with:\n"
        "  conda activate basketball_ai && python tests/test_tracker.py\n"
        "or:\n"
        "  conda run -n basketball_ai python tests/test_tracker.py"
    )
    sys.exit(1)

try:
    from src.tracking.evaluate import track_video, evaluate_tracking
except ModuleNotFoundError as e:
    print(f"ERROR: import failed — {e}\nCheck that detectron2 is installed in basketball_ai.")
    sys.exit(1)

DEFAULT_VIDEO = os.path.join(
    os.path.dirname(__file__), "..", "resources", "Short4Mosaicing.mp4"
)

MIN_AVG_PLAYERS    = 3.0
MIN_STABILITY      = 0.70
MAX_ZERO_FRAME_PCT = 0.30
MIN_FRAME_PCT      = 0.80
REQUIRED_FIELDS    = {"player_id", "team", "x2d", "y2d"}


def run_test(video_path: str, max_frames: int = 150) -> bool:
    assert os.path.exists(video_path), f"Video not found: {video_path}"

    print(f"\n{'='*58}")
    print(f"  Tracking Test — {os.path.basename(video_path)}")
    print(f"  Frames requested: {max_frames}")
    print(f"{'='*58}\n")

    results     = track_video(video_path, max_frames=max_frames, show=False)
    predictions = results["predictions"]
    total       = results["total_frames"]

    players_per_frame = [len(f["tracks"]) for f in predictions]
    avg_players       = sum(players_per_frame) / max(1, len(players_per_frame))
    zero_frames       = sum(1 for n in players_per_frame if n == 0)
    dropped_tracks    = sum(1 for n in players_per_frame if 0 < n < MIN_AVG_PLAYERS)

    metrics = evaluate_tracking(predictions)

    print(f"  Frames processed      : {total}")
    print(f"  Avg players / frame   : {avg_players:.1f}")
    print(f"  Frames with 0 players : {zero_frames}  ({100*zero_frames/max(1,total):.1f}%)")
    print(f"  Low-coverage frames   : {dropped_tracks}")
    print(f"  ID stability score    : {metrics['track_stability']:.3f}  (1.0 = perfect)")
    print(f"  ID switches (est.)    : {metrics['id_switches_estimated']}")
    print(f"  Mean confidence       : {metrics['mean_confidence']:.3f}")
    print(f"  Out-of-bounds dets    : {metrics['oob_detections']}")
    print(f"  Duplicate dets        : {metrics['duplicate_detections']}")

    missing_fields = set()
    for fd in predictions[:20]:
        for t in fd["tracks"]:
            missing_fields |= REQUIRED_FIELDS - set(t.keys())

    failures = []
    if total < max_frames * MIN_FRAME_PCT:
        failures.append(f"FAIL frames_processed: {total}/{max_frames} (expected >={int(max_frames*MIN_FRAME_PCT)})")
    if avg_players < MIN_AVG_PLAYERS:
        failures.append(f"FAIL avg_players: {avg_players:.1f} (expected >={MIN_AVG_PLAYERS})")
    if metrics["track_stability"] < MIN_STABILITY:
        failures.append(f"FAIL track_stability: {metrics['track_stability']:.3f} (expected >={MIN_STABILITY})")
    if zero_frames > total * MAX_ZERO_FRAME_PCT:
        failures.append(f"FAIL zero_frames: {zero_frames}/{total} ({100*zero_frames/total:.0f}%, expected <{int(MAX_ZERO_FRAME_PCT*100)}%)")
    if missing_fields:
        failures.append(f"FAIL missing_fields: {sorted(missing_fields)}")

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  {f}")
        return False

    print("PASSED — all checks passed.")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="NBA AI Tracker self-test")
    ap.add_argument("--video",  default=os.path.normpath(DEFAULT_VIDEO))
    ap.add_argument("--frames", type=int, default=150)
    args = ap.parse_args()
    sys.exit(0 if run_test(args.video, args.frames) else 1)
