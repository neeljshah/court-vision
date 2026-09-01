"""The funnel's one load-bearing property: every frame lands in exactly one bucket.

Run: python -m pytest scripts/platformkit/test_tennis_gate_funnel.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def _clip(path: Path, frames: int = 9) -> None:
    """A synthetic clip with court-like bright lines on a dark surface."""
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (640, 360))
    for _ in range(frames):
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[120:340, 60:580] = (40, 110, 40)
        for x in (90, 150, 320, 490, 550):          # five length-running lines
            cv2.line(frame, (x, 130), (x, 335), (255, 255, 255), 2)
        cv2.line(frame, (60, 330), (580, 330), (255, 255, 255), 2)
        writer.write(frame)
    writer.release()


def test_every_processed_frame_is_accounted_for_exactly_once(tmp_path):
    """A funnel that loses frames tells you the wrong thing about where they die.

    The counts across all buckets must equal the frames processed -- otherwise a
    stage silently swallows frames and its drop looks smaller than it is.
    """
    video = tmp_path / "synthetic.mp4"
    _clip(video)
    assert video.is_file() and video.stat().st_size > 0

    result = subprocess.run(
        [sys.executable, "-m", "scripts.platformkit.tennis_gate_funnel", str(video), "3"],
        capture_output=True, text=True, timeout=300, cwd=str(Path(__file__).resolve().parents[2]))
    assert result.returncode == 0, result.stderr[-800:]

    processed = 0
    bucket_total = 0
    in_buckets = False
    for line in result.stdout.splitlines():
        if line.startswith("processed"):
            processed = int(line.split()[1])
        elif line.startswith("WHERE FRAMES DIE"):
            in_buckets = True
        elif in_buckets and line.startswith("  "):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                bucket_total += int(parts[1])
        elif in_buckets and not line.strip():
            break

    assert processed > 0, result.stdout
    assert bucket_total == processed, "%d bucketed vs %d processed" % (bucket_total, processed)
