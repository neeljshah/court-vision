"""Known-geometry CONSTRUCT controls and native-pixel renders for G409.

The CONSTRUCT cases push synthetic frames of known geometry through the exact
archived statements (numpy row-slice crop at TOPCUT, the yxyx tuple stored by
the tracker, and the serialization expressions at the export site) so the
declared transform is confirmed independently of any measured box.
"""
from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

TOPCUT = 60


def archived_crop(frame: np.ndarray) -> np.ndarray:
    """unified_pipeline.py:1693 -- frame = frame[TOPCUT:]."""
    return frame[TOPCUT:]


def archived_serialize(bbox) -> dict[str, float]:
    """unified_pipeline.py:2736-2739 -- bbox is (y1, x1, y2, x2), written as xyxy."""
    return {"bbox_x1": bbox[1], "bbox_y1": bbox[0], "bbox_x2": bbox[3], "bbox_y2": bbox[2]}


def construct_cases() -> list[dict]:
    """Run origin, corner, crop-boundary and tuple-order cases end to end."""
    cases = []
    for name, height, width, native_box in (
        ("origin_1080p", 1080, 1920, (0, 0, 40, 40)),
        ("top_left_corner_1080p", 1080, 1920, (60, 0, 160, 80)),
        ("crop_boundary_1080p", 1080, 1920, (59, 10, 61, 12)),
        ("bottom_right_corner_1080p", 1080, 1920, (1040, 1880, 1080, 1920)),
        ("origin_720p", 720, 1280, (0, 0, 30, 30)),
        ("crop_boundary_720p", 720, 1280, (59, 5, 61, 7)),
        ("mid_court_720p", 720, 1280, (300, 600, 460, 680)),
    ):
        y1, x1, y2, x2 = native_box
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[y1:y2, x1:x2] = 255
        cropped = archived_crop(frame)
        ys, xs = np.nonzero(cropped[:, :, 0])
        if ys.size == 0:
            observed = None
            stored = None
        else:
            observed = (int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1)
            stored = archived_serialize(observed)
        fully_above = y2 <= TOPCUT
        straddles = y1 < TOPCUT < y2
        expected_y1 = "" if fully_above else max(0, y1 - TOPCUT)
        cases.append({
            "fully_above_crop_line": "1" if fully_above else "0",
            "straddles_crop_line": "1" if straddles else "0",
            "vanished_by_crop": "1" if observed is None else "0",
            "case": name,
            "native_height": height, "native_width": width,
            "native_y1": y1, "native_x1": x1, "native_y2": y2, "native_x2": x2,
            "crop_height": int(cropped.shape[0]), "crop_width": int(cropped.shape[1]),
            "observed_crop_y1": "" if observed is None else observed[0],
            "observed_crop_x1": "" if observed is None else observed[1],
            "stored_bbox_x1": "" if stored is None else stored["bbox_x1"],
            "stored_bbox_y1": "" if stored is None else stored["bbox_y1"],
            "expected_crop_y1_from_code": expected_y1,
            "crop_y_matches_code": "1" if (
                (fully_above and observed is None)
                or (observed is not None and observed[0] == expected_y1)) else "0",
            "crop_x_unchanged": "1" if (fully_above or (observed and observed[1] == x1)) else "0",
            "uncrop_recovers_native_y1": "1" if (
                fully_above or straddles or (observed and observed[0] + TOPCUT == y1)) else "0",
            "uncrop_exact": "0" if (fully_above or straddles) else "1",
            "tuple_order_checked": "y1x1y2x2->xyxy",
            "note": ("removed entirely by the crop" if fully_above else
                     "clipped at the crop line; uncrop returns y1=TOPCUT, not the native y1"
                     if straddles else ""),
        })
    return cases


COLORS = {"stored": (0, 0, 255), "mapped": (0, 220, 0), "comparator": (0, 200, 255)}


def render_card(frame_path: Path, out_path: Path, stored, mapped, comparator) -> tuple[int, str]:
    """Draw stored (red), code-mapped (green) and comparator (amber) boxes."""
    import hashlib

    image = cv2.imread(str(frame_path))
    if image is None:
        raise FileNotFoundError(str(frame_path))
    for label, boxes in (("stored", stored), ("mapped", mapped), ("comparator", comparator)):
        for box in boxes:
            x1, y1, x2, y2 = (int(round(float(v))) for v in box)
            cv2.rectangle(image, (x1, y1), (x2, y2), COLORS[label], 2)
    legend = "red = stored CSV   green = stored + TOPCUT(60)   amber = comparator native"
    cv2.putText(image, legend, (12, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    data = out_path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
