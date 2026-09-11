"""G382 frozen whole-stroke scorer at the G362 720p working scale."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking import g362_strokes
from scripts.platformkit.tracking.g382_masks import LABEL_CODES, UNKNOWN, label_name, rasterize, read

BASE_HEIGHT = 720
DILATION_RADIUS = 2
ON_MARKING_FRACTION = 0.80
FRAME_FIELDS = ("frame_key", "status", "native_width", "native_height", "work_width", "work_height", "n_strokes")
STROKE_FIELDS = ("frame_key", "stroke_id", "family", "length_px", "n_supports", "on_supports",
                 "on_fraction", "on_marking", "physical_marking_ids")
SUPPORT_FIELDS = ("frame_key", "stroke_id", "support_index", "x", "y", "base_label", "on_dilated_painted")


@dataclass(frozen=True)
class ResizeTransform:
    """Pixel-center coordinate transform used by OpenCV resize for the recorded target shape."""
    native_width: int
    native_height: int
    work_width: int
    work_height: int

    @classmethod
    def from_native(cls, width: int, height: int) -> "ResizeTransform":
        return cls(width, height, int(round(width * BASE_HEIGHT / height)), BASE_HEIGHT)

    def native_to_work(self, x: float, y: float) -> tuple[float, float]:
        return ((x + 0.5) * self.work_width / self.native_width - 0.5,
                (y + 0.5) * self.work_height / self.native_height - 0.5)

    def work_to_native(self, x: float, y: float) -> tuple[float, float]:
        return ((x + 0.5) * self.native_width / self.work_width - 0.5,
                (y + 0.5) * self.native_height / self.work_height - 0.5)

    def resize_image(self, image: np.ndarray) -> np.ndarray:
        return cv2.resize(image, (self.work_width, self.work_height), interpolation=cv2.INTER_AREA)

    def resize_mask(self, mask: np.ndarray) -> np.ndarray:
        return cv2.resize(mask, (self.work_width, self.work_height), interpolation=cv2.INTER_NEAREST)


def dilate(mask: np.ndarray) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * DILATION_RADIUS + 1,) * 2)
    return cv2.dilate(mask, kernel)


def _sample(mask: np.ndarray, x: float, y: float) -> int:
    col, row = int(round(x)), int(round(y))
    if row < 0 or col < 0 or row >= mask.shape[0] or col >= mask.shape[1]:
        return 0
    return int(mask[row, col])


def score_frame(frame_key: str, image: np.ndarray, annotation: Path) -> tuple[dict[str, str], list[dict[str, str]], list[dict[str, str]]]:
    """Score every G362 whole stroke; no emitted support is removed from the denominator."""
    doc = read(annotation)
    height, width = image.shape[:2]
    if doc.frame_key != frame_key or (doc.width, doc.height) != (width, height):
        raise ValueError("annotation identity or native dimensions disagree with pixels")
    transform = ResizeTransform.from_native(width, height)
    labels, physical = rasterize(doc)
    work_labels = transform.resize_mask(labels)
    work_physical = {key: dilate(transform.resize_mask(mask)) for key, mask in physical.items()}
    painted = dilate((work_labels == LABEL_CODES["PAINTED"]).astype(np.uint8))
    strokes = g362_strokes.extract_strokes(transform.resize_image(image))
    frame = {"frame_key": frame_key, "status": "SCORED", "native_width": str(width), "native_height": str(height),
             "work_width": str(transform.work_width), "work_height": str(transform.work_height), "n_strokes": str(len(strokes))}
    stroke_rows, support_rows = [], []
    for stroke in strokes:
        on_supports, marking_ids = 0, set()
        for index, (x, y) in enumerate(stroke.supports):
            label = label_name(_sample(work_labels, float(x), float(y)))
            on = int(label != UNKNOWN and _sample(painted, float(x), float(y)) != 0)
            on_supports += on
            marking_ids.update(key for key, mask in work_physical.items() if _sample(mask, float(x), float(y)) != 0)
            support_rows.append({"frame_key": frame_key, "stroke_id": stroke.stroke_id, "support_index": str(index),
                                 "x": "%.4f" % x, "y": "%.4f" % y, "base_label": label,
                                 "on_dilated_painted": str(on)})
        fraction = on_supports / len(stroke.supports)
        stroke_rows.append({"frame_key": frame_key, "stroke_id": stroke.stroke_id, "family": str(stroke.family),
                            "length_px": "%.4f" % stroke.length, "n_supports": str(len(stroke.supports)),
                            "on_supports": str(on_supports), "on_fraction": "%.8f" % fraction,
                            "on_marking": str(int(fraction >= ON_MARKING_FRACTION)),
                            "physical_marking_ids": ",".join(sorted(marking_ids))})
    return frame, stroke_rows, support_rows


def _write(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def receipt(frame_rows: list[dict[str, str]], strokes: list[dict[str, str]], supports: list[dict[str, str]]) -> dict[str, object]:
    """Canonical process receipt; finisher compares these from two fresh processes."""
    parts = {"frames": sorted(frame_rows, key=lambda row: row["frame_key"]),
             "strokes": sorted(strokes, key=lambda row: (row["frame_key"], row["stroke_id"])),
             "supports": sorted(supports, key=lambda row: (row["frame_key"], row["stroke_id"], row["support_index"]))}
    payload = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"sha256": hashlib.sha256(payload).hexdigest(), "frames": len(frame_rows), "strokes": len(strokes), "supports": len(supports)}


def verify_repeat(first: dict[str, object], second: dict[str, object]) -> dict[str, object]:
    """Record a hard identity result instead of treating one extraction as reproducible."""
    same = first == second
    return {"identical": same, "first": first, "second": second}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, required=True); parser.add_argument("--masks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    with args.frames.open(encoding="utf-8", newline="") as handle: planned = list(csv.DictReader(handle))
    frames, strokes, supports = [], [], []
    for row in planned:
        image = cv2.imread(row["native_path"], cv2.IMREAD_COLOR)
        if image is None:
            frames.append({"frame_key": row["frame_key"], "status": "DECODE_FAILED", "native_width": "", "native_height": "", "work_width": "", "work_height": "", "n_strokes": "0"}); continue
        result = score_frame(row["frame_key"], image, args.masks / (row["frame_key"] + ".json"))
        frames.append(result[0]); strokes.extend(result[1]); supports.extend(result[2])
    _write(args.out / "frames_scored.csv", FRAME_FIELDS, frames); _write(args.out / "strokes.csv", STROKE_FIELDS, strokes); _write(args.out / "support_labels.csv", SUPPORT_FIELDS, supports)
    value = receipt(frames, strokes, supports); (args.out / "receipt.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("G382_SCORE frames=%d strokes=%d supports=%d" % (len(frames), len(strokes), len(supports)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
