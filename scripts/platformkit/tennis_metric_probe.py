"""Measure whether the tennis adapter's court coordinates are metric feet.

TennisAdapter.detect_court_corners takes ``horizontal_clusters[0]`` -- the topmost
bright horizontal line ANYWHERE in the frame -- as the far doubles baseline.  In a
stadium broadcast the topmost bright horizontal lines are railings and ad-board
edges above the court, so the 78-foot length axis gets fitted against the wrong
line and comes out compressed.  The 36-foot width axis is unaffected, because both
sidelines are real lines.

This probe quantifies the damage without touching the adapter: every person box the
adapter sees is projected through BOTH the adapter's own homography and a
hand-measured reference quad for the same fixed camera, and the probe reports the
linear fit ``x_adapter = a * x_reference + b``.  a == 1 is metric; a < 1 means the
length axis is compressed by 1 / a.

The reference quad is validated on the frame before it is trusted: the adapter's own
detected singles sidelines must project to y = 4.5 and y = 31.5 feet, and those two
lines are not among the four the quad was fitted from.

Diagnostic only -- writes nothing, moves no threshold.

Run: python -m scripts.platformkit.tennis_metric_probe data/videos/reference/tennis.mp4
"""
from __future__ import annotations

import sys
from typing import Optional, Sequence

import cv2
import numpy as np
import pandas as pd

from domains.tennis.tracking.adapter import COURT_FEET, TennisAdapter
from domains.tennis.tracking.segmenter import detect_cut, small_gray

# Near-left, near-right, far-left, far-right doubles corners of the fixed rally
# camera in data/videos/reference/tennis.mp4, measured by least-squares fitting the
# bright pixels of the near baseline (image row 282.4) and the far baseline (row
# 87.4) between the adapter's own detected sidelines.  The adapter instead pins its
# far baseline to a stand railing at row 15.7.
REFERENCE_QUAD = np.float32(
    ((106.589, 283.389), (517.898, 281.441), (215.486, 87.694), (412.428, 87.103))
)
SINGLES_FEET = (4.5, 31.5)


def reference_homography(quad: np.ndarray = REFERENCE_QUAD) -> np.ndarray:
    """Map the reference image quad onto the 78-by-36-foot doubles court."""
    homography, _ = cv2.findHomography(np.asarray(quad, dtype=np.float32), COURT_FEET)
    if homography is None:
        raise ValueError("Could not calculate reference homography")
    return homography


def validate_reference(frame: np.ndarray,
                       quad: np.ndarray = REFERENCE_QUAD) -> Optional[tuple[float, float]]:
    """Return the court y of the two singles sidelines, or None if undetectable.

    A trustworthy quad puts them at SINGLES_FEET.  Independent check: those lines
    are not among the four the quad was fitted from.
    """
    height, width = frame.shape[:2]
    bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
    lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                            minLineLength=max(40, width // 12), maxLineGap=20)
    if lines is None:
        return None
    vertical = [line.astype(float) for line in lines.reshape(-1, lines.shape[-1])
                if abs(line[3] - line[1]) > abs(line[2] - line[0])]
    if len(vertical) < 2:
        return None
    clusters = TennisAdapter._cluster_lines(vertical, False, (height, width))
    if len(clusters) < 4:
        return None
    homography = reference_homography(quad)
    found = []
    for index in (1, len(clusters) - 2):
        x1, y1, x2, y2 = TennisAdapter._fit_line(clusters[index])
        u = x1 + (height / 2.0 - y1) * (x2 - x1) / (y2 - y1)
        found.append(float(cv2.perspectiveTransform(
            np.float32([[[u, height / 2.0]]]), homography)[0, 0][1]))
    return found[0], found[1]


def _boxes(adapter: TennisAdapter, frame: np.ndarray, homography: np.ndarray,
           href: np.ndarray, frame_index: int) -> list[dict[str, object]]:
    rows = []
    for box in adapter.detector(frame):
        x1, y1, x2, y2 = map(float, box[:4])
        if len(box) >= 5 and float(box[4]) < adapter.tracker_conf:
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        foot = ((x1 + x2) / 2.0, y2)
        own, ref = adapter._project(foot, homography), adapter._project(foot, href)
        rows.append({"frame": frame_index,
                     "x_adapter": float(own[0]), "y_adapter": float(own[1]),
                     "x_reference": float(ref[0]), "y_reference": float(ref[1]),
                     "accepted": True})
    return rows


def collect(video: str, offsets: Sequence[int] = (14454, 21681), per_window: int = 150,
            stride: int = 3, quad: np.ndarray = REFERENCE_QUAD,
            adapter_factory=TennisAdapter) -> pd.DataFrame:
    """Project every person box the adapter sees through both planes."""
    href = reference_homography(quad)
    rows: list[dict[str, object]] = []
    for offset in offsets:
        adapter = adapter_factory()
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise FileNotFoundError(video)
        capture.set(cv2.CAP_PROP_POS_FRAMES, offset)
        previous = None
        source = processed = 0
        try:
            while processed < per_window:
                ok, frame = capture.read()
                if not ok:
                    break
                current = small_gray(frame)
                if previous is not None and detect_cut(previous, current):
                    adapter._reset_temporal_calibration()
                previous = current
                if source % stride == 0:
                    homography = adapter._stable_homography(frame)
                    if homography is not None:
                        rows.extend(_boxes(adapter, frame, homography, href, offset + source))
                    processed += 1
                source += 1
        finally:
            capture.release()
    return pd.DataFrame(rows, columns=("frame", "x_adapter", "y_adapter",
                                       "x_reference", "y_reference", "accepted"))


def summarize(rows: pd.DataFrame) -> dict[str, float]:
    """Report the length-axis scale error and far players placed in the near half."""
    on_court = rows[rows.x_reference.between(-11.0, 89.0)
                    & rows.y_reference.between(-3.0, 39.0)]
    if len(on_court) < 2:
        return {"n_boxes": float(len(on_court))}
    scale, offset = np.polyfit(on_court.x_reference, on_court.x_adapter, 1)
    far = on_court[on_court.x_reference > 60.0]
    summary = {
        "n_boxes": float(len(on_court)),
        "length_scale": round(float(scale), 4),
        "length_offset_ft": round(float(offset), 2),
        "length_median_error_ft": round(
            float((on_court.x_adapter - on_court.x_reference).median()), 2),
        "width_median_error_ft": round(
            float((on_court.y_adapter - on_court.y_reference).median()), 2),
        "far_players": float(len(far)),
    }
    if len(far):
        summary["far_median_x_reference"] = round(float(far.x_reference.median()), 1)
        summary["far_median_x_adapter"] = round(float(far.x_adapter.median()), 1)
        summary["far_placed_in_near_half"] = float((far.x_adapter < 39.0).sum())
    return summary


def main(argv: list) -> int:
    if len(argv) < 2:
        print("usage: tennis_metric_probe.py <video> [per_window]")
        return 2
    video = argv[1]
    per_window = int(argv[2]) if len(argv) > 2 else 150
    capture = cv2.VideoCapture(video)
    capture.set(cv2.CAP_PROP_POS_FRAMES, 14454)
    ok, frame = capture.read()
    capture.release()
    if ok:
        checked = validate_reference(frame)
        print("reference singles sidelines -> %s ft (true %s)" % (
            None if checked is None else tuple(round(v, 2) for v in checked), SINGLES_FEET))
    for key, value in summarize(collect(video, per_window=per_window)).items():
        print("%-26s %s" % (key, value))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
