"""G412 native demonstration cards: raw cropped, native padded and native unpadded boxes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2

from scripts.platformkit.tracking.g412_contract import (
    CROP_ORIGIN_Y_PX, Box, native_boxes, write_csv_lf,
)
from scripts.platformkit.tracking.g412_premise import FRAMES, G406, OUT, read_csv
from scripts.platformkit.tracking.g412_tables import _route_of

RENDERS = OUT / "renders"
RAW_BGR = (60, 60, 235)
PADDED_BGR = (60, 220, 60)
DETECTOR_BGR = (235, 200, 60)
TEXT_BGR = (245, 245, 245)
FONT = cv2.FONT_HERSHEY_SIMPLEX


def _rect(image, box, colour, thickness: int = 2) -> None:
    cv2.rectangle(image, (int(round(box[0])), int(round(box[1]))),
                  (int(round(box[2])), int(round(box[3]))), colour, thickness)


def _caption(image, lines: list[str]) -> None:
    for index, line in enumerate(lines):
        y = 26 + index * 24
        cv2.putText(image, line, (12, y), FONT, 0.6, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(image, line, (12, y), FONT, 0.6, TEXT_BGR, 1, cv2.LINE_AA)


def render_card(tick: dict[str, str], boxes: list[dict[str, str]]) -> dict[str, Any]:
    """Render one sealed tick; a silent tick becomes an explicit UNKNOWN card."""
    card = tick["card_id"]
    png = FRAMES / (card + ".png")
    image = cv2.imread(str(png))
    if image is None:
        return {"card_id": card, "status": "DECODE_ABSENT", "render_path": "",
                "render_sha256": "", "render_bytes": 0, "crop_sha256": "",
                "crop_width": "", "crop_height": "", "boxes_drawn": 0}
    native_h, native_w = image.shape[:2]
    crop = image[CROP_ORIGIN_Y_PX:]
    crop_h, crop_w = crop.shape[:2]
    crop_sha = hashlib.sha256(crop.tobytes()).hexdigest()
    silent = tick["producer_silence"] == "1"
    drawn = 0
    for row in boxes:
        stored = tuple(float(row["bbox_" + k]) for k in ("x1", "y1", "x2", "y2"))
        padded, detector = native_boxes(Box(*stored), crop_w, crop_h)
        _rect(image, stored, RAW_BGR)
        _rect(image, padded.as_tuple(), PADDED_BGR)
        _rect(image, detector.as_tuple(), DETECTOR_BGR, 1)
        cv2.line(image, (int(round((stored[0] + stored[2]) / 2)),
                         int(round((stored[1] + stored[3]) / 2))),
                 (int(round((stored[0] + stored[2]) / 2)),
                  int(round((stored[1] + stored[3]) / 2 + CROP_ORIGIN_Y_PX))),
                 PADDED_BGR, 2)
        drawn += 1
    lines = [
        "G412 " + card + "  " + tick["section_id"] + "  frame " + tick["frame"]
        + "  pts " + tick["actual_pts_s"] + "s",
        "native " + str(native_w) + "x" + str(native_h) + "  cropped "
        + str(crop_w) + "x" + str(crop_h) + "  crop sha256 " + crop_sha[:16],
        "RED raw stored cropped xyxy   GREEN native padded (y+60)   CYAN native unpadded"
        + " (x+-15, y+75/+45)",
        ("UNKNOWN CARD: producer silent at this tick, 0 stored boxes"
         if silent else "stored boxes " + str(drawn)
         + "   centre translation +" + str(CROP_ORIGIN_Y_PX) + " before clipping"),
        "fresh_box " + str(sum(1 for b in boxes if _route_of(b) == "fresh_box"))
        + "   prediction " + str(sum(1 for b in boxes if _route_of(b) == "prediction"))
        + "   retained_point "
        + str(sum(1 for b in boxes if _route_of(b) == "retained_point")),
    ]
    _caption(image, lines)
    RENDERS.mkdir(parents=True, exist_ok=True)
    out_path = RENDERS / (card + ".jpg")
    cv2.imwrite(str(out_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    payload = out_path.read_bytes()
    return {"card_id": card, "status": "UNKNOWN_SILENT" if silent else "OK",
            "render_path": "renders/" + card + ".jpg",
            "render_sha256": hashlib.sha256(payload).hexdigest(),
            "render_bytes": len(payload), "crop_sha256": crop_sha,
            "crop_width": crop_w, "crop_height": crop_h, "boxes_drawn": drawn}


def run() -> dict[str, Any]:
    """Render all 60 sealed cards and write eye_index.csv."""
    per_tick = read_csv(G406 / "per_tick.csv")
    masked = read_csv(G406 / "all_masked_rows.csv")
    by_card: dict[str, list[dict[str, str]]] = {}
    for row in masked:
        by_card.setdefault(row["card_id"], []).append(row)
    rows = []
    for tick in per_tick:
        result = render_card(tick, by_card.get(tick["card_id"], []))
        rows.append({
            "card_id": tick["card_id"], "draw_kind": tick["draw_kind"],
            "section_id": tick["section_id"], "frame": tick["frame"],
            "sealed_ordinal": "", "native_width": tick["native_width"],
            "native_height": tick["native_height"],
            "producer_silence": tick["producer_silence"], **result,
        })
    write_csv_lf(OUT / "eye_index.csv", list(rows[0]), rows)
    return {"cards": len(rows),
            "ok": sum(1 for r in rows if r["status"] == "OK"),
            "unknown_silent": sum(1 for r in rows if r["status"] == "UNKNOWN_SILENT"),
            "decode_absent": sum(1 for r in rows if r["status"] == "DECODE_ABSENT"),
            "boxes_drawn": sum(r["boxes_drawn"] for r in rows),
            "distinct_crop_shapes": sorted({str(r["crop_width"]) + "x" + str(r["crop_height"])
                                            for r in rows})}


if __name__ == "__main__":
    print(json.dumps(run(), indent=1, sort_keys=True))
