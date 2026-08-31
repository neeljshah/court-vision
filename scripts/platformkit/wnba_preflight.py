"""Pre-tracking video checks for WNBA court appearance and visible lines."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball_wnba.tracking.court_config import (
    line_mask,
    sample_court_palette,
    scorebug_exclude,
)
from scripts.platformkit.io_atomic import write_json_atomic

REPORT_DIR = Path("data/tracking_reports/preflight")
_MAX_FRAMES = 200
_STRIDE = 10
_LOW_LINES_PCT = 0.20


def _sample_frames(video_path: Path) -> list[np.ndarray]:
    """Read every tenth frame among the first 200 decoded video frames."""
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError("Unable to open video: %s" % video_path)
    frames: list[np.ndarray] = []
    try:
        for index in range(_MAX_FRAMES):
            ok, frame = capture.read()
            if not ok:
                break
            if index % _STRIDE == 0:
                frames.append(frame)
    finally:
        capture.release()
    if not frames:
        raise ValueError("Video contains no readable frames: %s" % video_path)
    return frames


def _line_coverage(frames: list[np.ndarray], palette: dict[str, Any]) -> float:
    """Return mean line-mask coverage excluding the standard scorebug region."""
    coverage: list[float] = []
    for frame in frames:
        allowed = scorebug_exclude(frame.shape, "auto") > 0
        coverage.append(float(np.count_nonzero(line_mask(frame, palette)[allowed])) / allowed.sum())
    return 100.0 * float(np.mean(coverage))


def preflight(video_path: str | Path) -> dict[str, Any]:
    """Inspect a WNBA broadcast and write its court-readiness report."""
    path = Path(video_path)
    frames = _sample_frames(path)
    palette = sample_court_palette(frames)
    coverage_pct = _line_coverage(frames, palette)
    if palette["is_dark_court"]:
        verdict = "DARK_COURT_FALLBACK"
    elif coverage_pct < _LOW_LINES_PCT:
        verdict = "LOW_LINES"
    else:
        verdict = "OK"
    report = {
        "is_dark_court": bool(palette["is_dark_court"]),
        "line_coverage_pct": round(coverage_pct, 4),
        "scorebug_region": "auto",
        "verdict": verdict,
    }
    write_json_atomic(REPORT_DIR / (path.stem + ".json"), report, indent=2, trailing_newline=True)
    return report
