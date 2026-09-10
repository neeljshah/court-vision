"""Build blind G364 rating sheets from a sealed frame manifest."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np


def _strip(capture: cv2.VideoCapture, index: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for target in (max(0, index - 1), index, index + 1):
        capture.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = capture.read()
        if not ok:
            raise ValueError("unreadable frame: %d" % target)
        frames.append(frame)
    return frames


def sheet_name(stable_key: str) -> str:
    """Return a portable sheet basename; the colon in a stable key is illegal on Windows."""
    return stable_key.replace(":", "__")


def sheet(strip: list[np.ndarray], stable_key: str, target: Path) -> None:
    """Write a frame plus three-frame strip with no model information."""
    if len(strip) != 3:
        raise ValueError("sheet requires exactly three frames")
    tiles = [cv2.resize(frame, (240, 135), interpolation=cv2.INTER_AREA) for frame in strip]
    center = cv2.resize(strip[1], (360, 203), interpolation=cv2.INTER_AREA)
    canvas = np.full((370, 720, 3), 18, dtype=np.uint8)
    for index, tile in enumerate(tiles):
        canvas[24:159, index * 240:(index + 1) * 240] = tile
    canvas[167:370, 180:540] = center
    cv2.putText(canvas, "FRAME " + stable_key[-12:], (12, 18), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (245, 245, 245), 1, cv2.LINE_AA)
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (70, 55, 40):
        cv2.imwrite(str(target), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if target.stat().st_size <= 200_000:
            return
    raise ValueError("sheet exceeds 200 KB: " + str(target))


def build_sheets(manifest: Path, output: Path) -> None:
    """Decode one source at a time and emit blind sheets only for sealed rows."""
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    groups: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[row["source_path"]].append(row)
    for source, selected in groups.items():
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            raise ValueError("unreadable source: " + source)
        try:
            for row in selected:
                sheet(_strip(capture, int(row["frame_index"])), row["frame_key"],
                      output / (sheet_name(row["frame_key"]) + ".jpg"))
        finally:
            capture.release()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="G364 blind sheet builder")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    args = parser.parse_args()
    build_sheets(args.manifest, args.sheets)


if __name__ == "__main__":
    main()
