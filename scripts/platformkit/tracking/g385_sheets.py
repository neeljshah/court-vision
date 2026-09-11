"""G385 blind native-frame sheet preparation for section-level ratings."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import cv2


MAX_BYTES = 200_000
WIDTH = 1280
BLIND_FIELDS = ("sheet_id", "tick_key", "frame_index", "sheet_bytes", "sheet_sha256")


def blind_manifest(frames: list[dict[str, str]]) -> list[dict[str, str]]:
    """Create opaque sheet identifiers without labels, scores, or decisions."""
    ordered = sorted(frames, key=lambda row: row["tick_key"])
    return [{"sheet_id": "g385_%04d" % index, "tick_key": row["tick_key"],
             "frame_index": row["frame_index"]} for index, row in enumerate(ordered)]


def render_native(source: Path, frame_index: int, target: Path) -> int:
    """Render one native source frame as an overlay-free bounded JPEG."""
    capture = cv2.VideoCapture(str(source))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError("unreadable planned frame")
    height, width = frame.shape[:2]
    if width > WIDTH:
        frame = cv2.resize(frame, (WIDTH, max(1, round(height * WIDTH / width))),
                           interpolation=cv2.INTER_AREA)
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (85, 75, 65, 55, 45):
        cv2.imwrite(str(target), frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if target.stat().st_size <= MAX_BYTES:
            return target.stat().st_size
    target.unlink(missing_ok=True)
    raise ValueError("blind sheet exceeds byte cap")


def build(frames: list[dict[str, str]], sheets: Path) -> list[dict[str, str]]:
    """Render planned ticks only; callers retain all attempted ticks separately."""
    out = []
    for row in blind_manifest(frames):
        source_row = next(item for item in frames if item["tick_key"] == row["tick_key"])
        target = sheets / (row["sheet_id"] + ".jpg")
        size = render_native(Path(source_row["source_path"]), int(row["frame_index"]), target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        out.append({**row, "sheet_bytes": str(size), "sheet_sha256": digest})
    return out


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    """Write an LF-only blind manifest under the evidence directory supplied by the caller."""
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BLIND_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
