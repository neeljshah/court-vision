"""Measure football field-line evidence before invoking detector or OCR.

Run: python -m domains.football.tracking.line_probe <video> [--frames 300]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from domains.football.tracking.adapter import FootballAdapter
from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction, pencil_is_uniform


@dataclass
class Probe:
    sampled: int = 0
    field: int = 0
    hough_family: int = 0
    lsd_family: int = 0
    uniform: int = 0
    hash_rows: int = 0

    def render(self, width: int, height: int, fps: float) -> str:
        denominator = max(self.sampled, 1)
        fields = ("field", "hough_family", "lsd_family", "uniform", "hash_rows")
        lines = ["source=%dx%d fps=%.3f sampled=%d" % (width, height, fps, self.sampled)]
        for name in fields:
            value = getattr(self, name)
            lines.append("%s=%d (%.3f)" % (name, value, value / denominator))
        return "\n".join(lines)


def _hough_family(frame: np.ndarray, adapter: FootballAdapter) -> list[np.ndarray]:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
    white = cv2.inRange(hsv, np.array((0, 0, 150)), np.array((180, 100, 255)))
    mask = cv2.bitwise_and(white, cv2.dilate(green, np.ones((5, 5), np.uint8)))
    lines = cv2.HoughLinesP(mask, 1, np.pi / 180, threshold=35,
                            minLineLength=max(30, frame.shape[1] // 12), maxLineGap=18)
    return [] if lines is None else adapter.family_from_segments(
        [line.astype(float) for line in lines.reshape(-1, lines.shape[-1])])


def measure(video: Path, budget: int, stride: int) -> Probe:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    adapter, result, index = FootballAdapter(), Probe(), 0
    try:
        while result.sampled < budget:
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride:
                index += 1
                continue
            result.sampled += 1
            if field_view_fraction(frame) < MIN_FIELD_VIEW_GREEN:
                index += 1
                continue
            result.field += 1
            if len(_hough_family(frame, adapter)) >= 4:
                result.hough_family += 1
            yards = adapter.detect_yard_line_family(frame)
            if len(yards) >= 4:
                result.lsd_family += 1
            if len(yards) >= 4 and pencil_is_uniform(yards, frame.shape):
                result.uniform += 1
                if len(adapter._hash_row_lines(frame, yards)) == 2:
                    result.hash_rows += 1
            index += 1
    finally:
        capture.release()
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--frames", type=int, default=300)
    parser.add_argument("--stride", type=int, default=3)
    args = parser.parse_args(argv[1:])
    capture = cv2.VideoCapture(str(args.video))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    capture.release()
    print(measure(args.video, args.frames, args.stride).render(width, height, fps))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
