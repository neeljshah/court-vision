"""Produce a bounded FootballAdapter tracking smoke report.

Run: python scripts/platformkit/football_smoke.py VIDEO_PATH --game-id GAME_ID
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Optional, Sequence

import numpy as np

from domains.football.tracking.adapter import Detector, FootballAdapter

REPORT_DIR = Path("data/tracking_reports/football")
QUEUE_PATH = Path("data/footage_queue_football.json")


def run_smoke(
    video_path: Path,
    game_id: str,
    detector: Optional[Detector] = None,
    max_frames: int = 3000,
    report_dir: Path = REPORT_DIR,
) -> dict[str, object]:
    """Run FootballAdapter and write a concise tracking readiness report."""
    adapter = FootballAdapter(detector=detector)
    original: Callable[[np.ndarray], object] = adapter.homography_from_yard_lines
    attempts = accepted = 0

    def monitored(frame: np.ndarray) -> object:
        nonlocal attempts, accepted
        attempts += 1
        homography = original(frame)
        accepted += homography is not None
        return homography

    adapter.homography_from_yard_lines = monitored  # type: ignore[method-assign]
    rows = adapter.process_video(video_path, max_frames=max_frames)
    report = {
        "game_id": game_id,
        "n_presnap_frames": int(rows["frame"].nunique()),
        "n_player_rows": int(len(rows)),
        "homography_acceptance_rate": accepted / attempts if attempts else 0.0,
    }
    output = report_dir / (game_id + "_smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a FootballAdapter smoke report")
    parser.add_argument("video_path", type=Path)
    parser.add_argument("--game-id", help="Report game ID; defaults to the video filename stem")
    args = parser.parse_args()
    if QUEUE_PATH.is_file() and "REPLACE_ME" in QUEUE_PATH.read_text(encoding="utf-8"):
        print("WARNING: FILL REAL COLLEGE-FOOTBALL FULL-GAME URLS IN data/footage_queue_football.json")
    try:
        report = run_smoke(args.video_path, args.game_id or args.video_path.stem)
    except ImportError as exc:
        print("ERROR: ultralytics is required for a production football smoke run: %s" % exc)
        raise SystemExit(2)
    print("football_smoke game_id=%s presnap_frames=%d player_rows=%d homography_rate=%.3f" % (
        report["game_id"], report["n_presnap_frames"], report["n_player_rows"],
        report["homography_acceptance_rate"],
    ))


if __name__ == "__main__":
    main()
