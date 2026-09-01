"""Measure LSD funnel survivors and an independent football hash/yard scale check.

Run: python -m domains.football.tracking.scale_probe <video> --frames 60
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from domains.football.tracking.adapter import FootballAdapter
from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction, pencil_is_uniform
from domains.football.tracking.geometry import NFL_HASH_ROW_SEPARATION_FT, YARD_LINE_SPACING_FT

EXPECTED_NFL_RATIO = NFL_HASH_ROW_SEPARATION_FT / YARD_LINE_SPACING_FT


@dataclass
class ScaleProbe:
    sampled: int = 0
    field_view: int = 0
    line_detection: int = 0
    yard_line_family: int = 0
    hash_mark_detection: int = 0
    ratios: list[float] = field(default_factory=list)

    def render(self, width: int, height: int, fps: float) -> str:
        stages = ("field_view", "line_detection", "yard_line_family", "hash_mark_detection")
        lines = ["source=%dx%d fps=%.3f sampled=%d" % (width, height, fps, self.sampled)]
        lines.extend("%s=%d" % (stage, getattr(self, stage)) for stage in stages)
        errors = np.abs(np.asarray(self.ratios) / EXPECTED_NFL_RATIO - 1.0)
        lines.append("scale_n=%d expected_ratio=%.6f" % (len(self.ratios), EXPECTED_NFL_RATIO))
        if len(errors):
            lines.append("ratio_median=%.6f median_error_pct=%.3f p95_error_pct=%.3f" %
                         (float(np.median(self.ratios)), 100 * float(np.median(errors)),
                          100 * float(np.percentile(errors, 95))))
        lines.append("scale_status=%s" % ("pass" if len(errors) >= 30 and
                     float(np.percentile(errors, 95)) <= 0.10 else "provisional_or_fail"))
        return "\n".join(lines)


def _canonical(line: np.ndarray) -> np.ndarray:
    line = np.asarray(line, dtype=float).copy()
    if line[0] < 0 or (abs(line[0]) < 1e-9 and line[1] < 0):
        line *= -1.0
    return line / np.hypot(line[0], line[1])


def _intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray | None:
    point = np.cross(first, second)
    return None if abs(float(point[2])) < 1e-8 else point[:2] / point[2]


def _frame_ratio(yards: list[np.ndarray], hashes: list[np.ndarray]) -> float | None:
    """Return a frame median without selecting candidates by the expected ratio."""
    ordered_yards = sorted((_canonical(line) for line in yards), key=lambda line: line[2])
    first_hash, second_hash = map(_canonical, hashes)
    values = []
    for first, second in zip(ordered_yards, ordered_yards[1:]):
        a, b = _intersection(first, first_hash), _intersection(first, second_hash)
        c, d = _intersection(first, first_hash), _intersection(second, first_hash)
        if a is None or b is None or c is None or d is None:
            continue
        hash_distance, yard_distance = np.linalg.norm(a - b), np.linalg.norm(c - d)
        if yard_distance > 1e-6:
            values.append(float(hash_distance / yard_distance))
    return float(np.median(values)) if values else None


def measure(video: Path, frames: int) -> ScaleProbe:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    indices = np.linspace(0, count - 1, num=frames, dtype=int)
    adapter, result = FootballAdapter(field_level="nfl"), ScaleProbe()
    try:
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            result.sampled += 1
            if field_view_fraction(frame) < MIN_FIELD_VIEW_GREEN:
                continue
            result.field_view += 1
            segments = adapter._segments(frame, max(30.0, frame.shape[1] / 12.0))
            if not segments:
                continue
            result.line_detection += 1
            yards = adapter.detect_yard_line_family(frame)
            if len(yards) < 4 or not pencil_is_uniform(yards, frame.shape):
                continue
            result.yard_line_family += 1
            hashes = adapter._hash_row_lines(frame, yards)
            if len(hashes) != 2:
                continue
            result.hash_mark_detection += 1
            ratio = _frame_ratio(yards, hashes)
            if ratio is not None:
                result.ratios.append(ratio)
    finally:
        capture.release()
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args(argv[1:])
    capture = cv2.VideoCapture(str(args.video))
    width, height, fps = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
                          int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)), capture.get(cv2.CAP_PROP_FPS) or 0.0)
    capture.release()
    print(measure(args.video, args.frames).render(width, height, fps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
