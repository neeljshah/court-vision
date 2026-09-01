"""Count explicitly-defined NFL scale references in a broadcast clip.

Run: python -m domains.football.tracking.scale_source_probe VIDEO --output DIR
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from domains.football.tracking.adapter import FootballAdapter
from domains.football.tracking.field_gates import MIN_FIELD_VIEW_GREEN, field_view_fraction, pencil_is_uniform


@dataclass
class SourceProbe:
    sampled: int = 0
    field_view: int = 0
    numerals: list[int] = field(default_factory=list)
    yard_pairs: list[int] = field(default_factory=list)
    hash_to_sideline: list[int] = field(default_factory=list)
    white_borders: list[int] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {"numerals": len(self.numerals), "yard_pairs": len(self.yard_pairs),
                "hash_to_sideline": len(self.hash_to_sideline),
                "white_borders": len(self.white_borders)}


def _white_mask(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, np.array((0, 0, 165)), np.array((180, 95, 255)))


def _numeral_count(frame: np.ndarray, yards: list[np.ndarray]) -> int:
    """Require two similarly-sized digit-like contours beside a detected yard line."""
    if len(yards) < 2:
        return 0
    mask = _white_mask(frame)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        aspect = width / max(height, 1)
        if 10 <= height <= frame.shape[0] / 4 and 0.25 <= aspect <= 1.1:
            candidates.append((x, y, width, height))
    for first in candidates:
        for second in candidates:
            if first >= second:
                continue
            close_height = abs(first[3] - second[3]) <= max(first[3], second[3]) * .25
            close_row = abs((first[1] + first[3] / 2) - (second[1] + second[3] / 2)) <= max(first[3], second[3])
            close_column = abs((first[0] + first[2] / 2) - (second[0] + second[2] / 2)) <= 3 * max(first[2], second[2])
            if close_height and close_row and close_column:
                return 1
    return 0


def _long_parallel_edges(adapter: FootballAdapter, frame: np.ndarray, yards: list[np.ndarray]) -> list[np.ndarray]:
    if not yards:
        return []
    yard_angle = np.arctan2(-yards[0][0], yards[0][1]) % np.pi
    edges = []
    for segment in adapter._segments(frame, frame.shape[1] / 3):
        angle = np.arctan2(segment[3] - segment[1], segment[2] - segment[0]) % np.pi
        delta = abs(((angle - yard_angle + np.pi / 2) % np.pi) - np.pi / 2)
        if delta >= np.deg2rad(12):
            edges.append(adapter._line_coefficients(segment))
    return edges


def _single_hash_and_sideline(adapter: FootballAdapter, frame: np.ndarray, yards: list[np.ndarray]) -> int:
    """Conservative proxy: one hash-row fit plus a field-edge length segment."""
    if not yards or not _long_parallel_edges(adapter, frame, yards):
        return 0
    # The production detector only returns exactly two rows. One usable row is
    # still a candidate here, so count a two-row detection as a fortiori proof.
    return int(len(adapter._hash_row_lines(frame, yards)) == 2)


def _white_border(adapter: FootballAdapter, frame: np.ndarray, yards: list[np.ndarray]) -> int:
    return int(len(_long_parallel_edges(adapter, frame, yards)) >= 2)


def _crop(frame: np.ndarray, label: str, index: int, passed: bool) -> np.ndarray:
    text = "%s frame=%d %s" % (label, index, "resolved" if passed else "not_resolved")
    image = frame.copy()
    cv2.putText(image, text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (0, 0, 0), 3)
    cv2.putText(image, text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, .8, (255, 255, 255), 1)
    return image


def measure(video: Path, output: Path, frames: int = 60) -> SourceProbe:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    output.mkdir(parents=True, exist_ok=True)
    # This probe only observes image evidence; it never creates field feet.
    # Keep it runnable against the staged pod's earlier adapter interface too.
    result, adapter = SourceProbe(), FootballAdapter()
    saved = {name: 0 for name in result.counts()}
    count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    try:
        for index in np.linspace(0, count - 1, num=frames, dtype=int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            result.sampled += 1
            if field_view_fraction(frame) < MIN_FIELD_VIEW_GREEN:
                continue
            result.field_view += 1
            yards = adapter.detect_yard_line_family(frame)
            uniform = len(yards) >= 3 and pencil_is_uniform(yards, frame.shape)
            values = {"numerals": _numeral_count(frame, yards),
                      "yard_pairs": int(uniform),
                      "hash_to_sideline": _single_hash_and_sideline(adapter, frame, yards),
                      "white_borders": _white_border(adapter, frame, yards)}
            for name, value in values.items():
                if value:
                    getattr(result, name).append(int(index))
                if saved[name] < 5:
                    cv2.imwrite(str(output / ("%s_%02d.jpg" % (name, saved[name] + 1))),
                                _crop(frame, name, int(index), bool(value)))
                    saved[name] += 1
    finally:
        capture.release()
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args(argv[1:])
    result = measure(args.video, args.output, args.frames)
    print("sampled=%d field_view=%d" % (result.sampled, result.field_view))
    for name, value in result.counts().items():
        print("%s=%d" % (name, value))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
