"""Source-video metadata and resolution-independent range conversions."""
from __future__ import annotations

import csv
import os
from pathlib import Path

import cv2


def probe_source(video: Path) -> dict[str, float | int | None]:
    """Return declared source timing and dimensions without full decoding."""
    capture = cv2.VideoCapture(str(video))
    try:
        if not capture.isOpened():
            return {"source_fps": None, "source_height": None, "source_duration": None}
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frames = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return {"source_fps": fps if fps > 0 else None,
                "source_height": height if height > 0 else None,
                "source_duration": frames / fps if frames > 0 and fps > 0 else None}
    finally:
        capture.release()


def seconds_to_frames(start: float, stop: float, fps: float) -> tuple[int, int]:
    """Convert inclusive seconds bounds to nearest source-frame bounds."""
    if fps <= 0:
        raise ValueError("source fps must be positive")
    if stop < start:
        raise ValueError("range seconds needs start <= stop")
    return round(start * fps), round(stop * fps)


def frames_to_seconds(start: int, stop: int, fps: float) -> tuple[float, float]:
    """Convert inclusive source-frame bounds to seconds."""
    if fps <= 0:
        raise ValueError("source fps must be positive")
    if stop < start:
        raise ValueError("range frames needs start <= stop")
    return start / fps, stop / fps


def stamp_tracking_csv(path: Path, source: dict[str, float | int | None]) -> None:
    """Append source metadata columns without renaming existing CSV fields."""
    try:
        original = path.stat()
        with path.open("r", newline="", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            if not fields:
                return
            rows = list(reader)
        for name in ("source_fps", "source_height", "source_duration"):
            if name not in fields:
                fields.append(name)
        temp = path.with_name(path.name + ".source_meta")
        with temp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                for name in ("source_fps", "source_height", "source_duration"):
                    row[name] = source[name]
                writer.writerow(row)
        os.replace(temp, path)
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    except (OSError, csv.Error):
        return
