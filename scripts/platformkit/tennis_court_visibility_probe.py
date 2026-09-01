"""Measure direct tennis-court visibility without using player detections.

This probe deliberately calls only the adapter's court-line solver.  A failed
solve is evidence that court coordinates cannot be produced for that frame;
it is not inferred from the number of detected players.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.tennis.tracking.adapter import TennisAdapter


def measure(video: Path, max_frames: int) -> dict[str, object]:
    """Return direct court-solve counts for a bounded video prefix."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    adapter = TennisAdapter(detector=lambda frame: ())
    sampled = solved = 0
    try:
        while sampled < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            sampled += 1
            solved += int(adapter.detect_court_corners(frame) is not None)
    finally:
        capture.release()
    return {
        "video": video.name,
        "frames_sampled": sampled,
        "court_solved_frames": solved,
        "court_solved_fraction": round(solved / sampled, 4) if sampled else 0.0,
    }


def main() -> int:
    """Print a JSON court-visibility measurement for one video."""
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-frames", type=int, default=600)
    parser.add_argument("--tracking-csv", type=Path)
    args = parser.parse_args()
    if args.max_frames < 1:
        parser.error("--max-frames must be positive")
    report = measure(args.video, args.max_frames)
    if args.tracking_csv is not None:
        adapter = TennisAdapter()
        rows = adapter.process_video(args.video, max_frames=args.max_frames)
        adapter.write_csv(args.tracking_csv, rows)
        report["tracking_rows"] = int(len(rows))
        report["tracking_frames"] = int(rows["frame"].nunique()) if len(rows) else 0
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
