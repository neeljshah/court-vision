"""Grid blind views and adjudication overlays for the G406 pixel diagnostic."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import cv2
import numpy as np

from scripts.platformkit.tracking.g406_measure import FRAMES, OUT, read_csv, sha256, write_csv

VIEWS = Path("C:/Users/neelj/g406_views")
STEP = 100
FONT = cv2.FONT_HERSHEY_SIMPLEX
COLORS = {"PRODUCER": (60, 220, 255), "COMPARATOR": (80, 255, 80), "BLIND": (255, 120, 255)}


def grid_view(image: np.ndarray, step: int = STEP) -> np.ndarray:
    """Draw a native-coordinate reference grid without revealing any prediction."""
    canvas = image.copy()
    overlay_layer = canvas.copy()
    height, width = canvas.shape[:2]
    for x in range(0, width, step):
        cv2.line(overlay_layer, (x, 0), (x, height), (0, 255, 255), 2 if x % (2 * step) == 0 else 1)
    for y in range(0, height, step):
        cv2.line(overlay_layer, (0, y), (width, y), (0, 255, 255), 2 if y % (2 * step) == 0 else 1)
    canvas = cv2.addWeighted(overlay_layer, 0.30, canvas, 0.70, 0.0)
    for x in range(0, width, 2 * step):
        for y_text in (30, height - 12):
            cv2.putText(canvas, str(x), (x + 4, y_text), FONT, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(canvas, str(x), (x + 4, y_text), FONT, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    for y in range(0, height, 2 * step):
        for x_text in (4, width - 78):
            cv2.putText(canvas, str(y), (x_text, y - 6), FONT, 0.8, (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(canvas, str(y), (x_text, y - 6), FONT, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    return canvas


def draw_boxes(canvas: np.ndarray, boxes: Iterable[Mapping[str, Any]], role: str) -> np.ndarray:
    """Draw one labelled anonymized box set in its role colour."""
    colour = COLORS[role]
    for box in boxes:
        x1, y1, x2, y2 = (int(round(float(box[field]))) for field in
                          ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
        cv2.rectangle(canvas, (x1, y1), (x2, y2), colour, 2)
        label = str(box["label"])
        anchor = (max(2, x1), max(16, y1 - 6))
        cv2.putText(canvas, label, anchor, FONT, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(canvas, label, anchor, FONT, 0.6, colour, 2, cv2.LINE_AA)
    return canvas


def _save(path: Path, image: np.ndarray, quality: int) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return {"path": str(path).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256(path)}


def stage_views() -> dict[str, Any]:
    rows = []
    for receipt in read_csv(OUT / "frame_receipts.csv"):
        image = cv2.imread(str(FRAMES / (receipt["card_id"] + ".png")))
        saved = _save(VIEWS / (receipt["card_id"] + ".jpg"), grid_view(image), 88)
        rows.append({"card_id": receipt["card_id"], "grid_step": STEP,
                     "native_width": image.shape[1], "native_height": image.shape[0],
                     "view_path": saved["path"], "view_bytes": saved["bytes"],
                     "view_sha256": saved["sha256"]})
    write_csv(OUT / "blind_view_receipts.csv", rows, list(rows[0]))
    return {"views": len(rows)}


def stage_cards() -> dict[str, Any]:
    """Render the 60 adjudication cards from producer rows and comparator detections."""
    producer: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "all_masked_rows.csv"):
        producer.setdefault(row["card_id"], []).append(
            dict(row, label=row["box_id"].split("_r")[-1] + ":" + row["position_source"][:4]))
    comparator: dict[str, list[dict[str, Any]]] = {}
    for row in read_csv(OUT / "comparator_detections.csv"):
        comparator.setdefault(row["card_id"], []).append(
            dict(row, label=row["det_id"].split("_d")[-1] + ":" + row["confidence"][:4]))
    rows = []
    for receipt in read_csv(OUT / "frame_receipts.csv"):
        card = receipt["card_id"]
        canvas = grid_view(cv2.imread(str(FRAMES / (card + ".png"))))
        draw_boxes(canvas, producer.get(card, []), "PRODUCER")
        draw_boxes(canvas, comparator.get(card, []), "COMPARATOR")
        saved = _save(OUT / "renders" / (card + ".jpg"), canvas, 72)
        rows.append({"card_id": card, "producer_boxes": len(producer.get(card, [])),
                     "comparator_boxes": len(comparator.get(card, [])),
                     "silence": int(not producer.get(card)),
                     "render_path": "renders/" + card + ".jpg",
                     "render_bytes": saved["bytes"], "render_sha256": saved["sha256"]})
    write_csv(OUT / "render_receipts.csv", rows, list(rows[0]))
    return {"cards": len(rows), "silence_cards": sum(row["silence"] for row in rows),
            "total_bytes": sum(row["render_bytes"] for row in rows)}


if __name__ == "__main__":
    name = sys.argv[1]
    print({"views": stage_views, "cards": stage_cards}[name]())
