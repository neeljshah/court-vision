"""G382 eye-check cards: native pixels, reference polygons and every emitted stroke."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.g382_masks import LABELS, read
from scripts.platformkit.tracking.g382_score import ResizeTransform

CARD_WIDTH = 1280
JPEG_QUALITY = 70
PAINTED_BGR = (0, 235, 0)
REGION_BGR = {"STANDS": (160, 160, 160), "LED": (0, 200, 235), "SCORE_BUG": (235, 120, 0),
              "OTHER": (120, 120, 235), "UNREADABLE": (60, 60, 60)}
STROKE_ON_BGR = (0, 0, 255)
STROKE_OFF_BGR = (235, 0, 235)


def even_indices(size: int, count: int) -> list[int]:
    """Even positions over the WHOLE planned set; a head slice is a contract B7 reject."""
    if size <= count:
        return list(range(size))
    return sorted({int(round(index * (size - 1) / (count - 1))) for index in range(count)})


def _poly(points) -> np.ndarray:
    return np.rint(np.asarray(points, dtype=np.float32)).astype(np.int32)


def draw(image: np.ndarray, annotation: Path | None, strokes: list[dict[str, str]]) -> np.ndarray:
    """Overlay reference geometry in native pixels; strokes are mapped back from 720p."""
    canvas = image.copy()
    height, width = canvas.shape[:2]
    transform = ResizeTransform.from_native(width, height)
    if annotation is not None and annotation.is_file():
        doc = read(annotation)
        for label, polygon in doc.regions:
            cv2.polylines(canvas, [_poly(polygon)], True, REGION_BGR.get(label, (90, 90, 90)), 2)
        for marking in doc.markings:
            cv2.polylines(canvas, [_poly(marking.polygon)], True, PAINTED_BGR, 3)
    for row in strokes:
        points = json.loads(row["support_xy"])
        native = [transform.work_to_native(float(x), float(y)) for x, y in points]
        colour = STROKE_ON_BGR if row["on_marking"] == "1" else STROKE_OFF_BGR
        for x, y in native:
            cv2.circle(canvas, (int(round(x)), int(round(y))), 3, colour, -1)
        if len(native) > 1:
            cv2.line(canvas, tuple(int(round(v)) for v in native[0]),
                     tuple(int(round(v)) for v in native[-1]), colour, 1)
    scale = CARD_WIDTH / width
    return cv2.resize(canvas, (CARD_WIDTH, int(round(height * scale))), interpolation=cv2.INTER_AREA)


def card_missing(frame_key: str, reason: str) -> np.ndarray:
    """An explicit card, so a missing frame is never silently absent from the eye check."""
    canvas = np.zeros((360, CARD_WIDTH, 3), dtype=np.uint8)
    cv2.putText(canvas, frame_key[:64], (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.putText(canvas, reason[:64], (20, 210), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--masks", type=Path, required=True)
    parser.add_argument("--supports", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with args.frames.open(encoding="utf-8", newline="") as handle:
        planned = list(csv.DictReader(handle))
    grouped: dict[str, dict[str, list]] = {}
    with args.supports.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            frame = grouped.setdefault(row["frame_key"], {})
            frame.setdefault(row["stroke_id"], []).append((float(row["x"]), float(row["y"])))
    on_marking = {}
    with (args.supports.parent / "strokes.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            on_marking[(row["frame_key"], row["stroke_id"])] = row["on_marking"]
    written = 0
    for index in even_indices(len(planned), args.count):
        row = planned[index]
        key = row["frame_key"]
        safe = key.replace(":", "_").replace("/", "_")
        image = cv2.imread(row.get("frame_path", ""), cv2.IMREAD_COLOR) if row.get("frame_path") else None
        if image is None:
            card = card_missing(key, row.get("retained", "MISSING"))
        else:
            strokes = [{"support_xy": json.dumps(points),
                        "on_marking": on_marking.get((key, stroke_id), "0")}
                       for stroke_id, points in sorted(grouped.get(key, {}).items())]
            card = draw(image, args.masks / (safe + ".json"), strokes)
        cv2.imwrite(str(args.out / ("%02d_%s.jpg" % (index, safe))), card,
                    [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        written += 1
    print("G382_RENDER cards=%d of planned=%d labels=%d" % (written, len(planned), len(LABELS)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
