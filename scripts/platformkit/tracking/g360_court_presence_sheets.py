"""Build G360 blind sheets from a sealed held-out frame list."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


def _read_strip(capture: cv2.VideoCapture, frame_index: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for index in (max(0, frame_index - 1), frame_index, frame_index + 1):
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = capture.read()
        if not ok:
            raise ValueError("unreadable held-out frame: %d" % index)
        frames.append(frame)
    return frames


def _sheet(strip: list[np.ndarray], frame_key: str, target: Path) -> None:
    """Write a blind representative and strip with no cue or prediction text."""
    if len(strip) != 3:
        raise ValueError("sheet needs a three-frame strip")
    tiles = [cv2.resize(frame, (240, 135), interpolation=cv2.INTER_AREA) for frame in strip]
    representative = cv2.resize(strip[1], (360, 203), interpolation=cv2.INTER_AREA)
    canvas = np.full((370, 720, 3), 18, dtype=np.uint8)
    for index, tile in enumerate(tiles):
        canvas[24:159, index * 240:(index + 1) * 240] = tile
    canvas[167:370, 180:540] = representative
    cv2.putText(canvas, "FRAME " + frame_key[-12:], (12, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (245, 245, 245), 1, cv2.LINE_AA)
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (70, 55, 40):
        cv2.imwrite(str(target), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if target.stat().st_size <= 200_000:
            return
    raise ValueError("sheet exceeds 200 KB: %s" % target)


def build_sheets(heldout_csv: Path, sheet_dir: Path) -> None:
    """Decode sources one at a time and build sheets for sealed rows only."""
    with heldout_csv.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    by_source: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_source[row["source_path"]].append(row)
    for source, selected in by_source.items():
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise ValueError("unreadable source: %s" % source)
        try:
            for row in selected:
                strip = _read_strip(capture, int(row["frame_index"]))
                _sheet(strip, row["frame_key"],
                       sheet_dir / (row["frame_key"] + ".jpg"))
        finally:
            capture.release()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="G360 blind sheet builder")
    parser.add_argument("--heldout", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    args = parser.parse_args()
    build_sheets(args.heldout, args.sheets)


if __name__ == "__main__":
    main()
