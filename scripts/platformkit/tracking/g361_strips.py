"""G361 eye check: one strip per section -- the archived tick's boxes drawn on the
re-fetched frame at the same index, beside the plain frame, the error printed.
Rendered before the scratch section is deleted; nothing here scores a verdict.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import cv2

CAP = 200 * 1024
PANEL_W = 640
QUALITIES = (80, 60, 45, 30, 20, 12)
BOX = ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


def landmarks(alignment, game_id: str) -> list:
    with Path(alignment).open(encoding="utf-8", errors="replace") as handle:
        return [row for row in csv.DictReader(handle) if row["game_id"] == game_id]


def archived_boxes(table, frame_index: int) -> list:
    """Boxes recorded at one archived frame; rows are frame-ordered, so stop past it."""
    boxes = []
    with Path(table).open(encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            try:
                frame = int(row["frame"])
            except (KeyError, TypeError, ValueError):
                continue
            if frame > frame_index:
                break
            if frame < frame_index:
                continue
            try:
                boxes.append(tuple(int(float(row[key])) for key in BOX))
            except (KeyError, TypeError, ValueError):
                continue
    return boxes


def frame_at(video, index: int):
    capture = cv2.VideoCapture(str(video))
    capture.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, image = capture.read()
    capture.release()
    return image if ok else None


def compose(image, boxes: list, caption: str):
    marked = image.copy()
    for x1, y1, x2, y2 in boxes:
        cv2.rectangle(marked, (x1, y1), (x2, y2), (0, 255, 0), 3)
    size = (PANEL_W, max(1, int(image.shape[0] * PANEL_W / image.shape[1])))
    pair = cv2.hconcat([cv2.resize(marked, size), cv2.resize(image, size)])
    strip = cv2.copyMakeBorder(pair, 24, 0, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
    cv2.putText(strip, caption, (5, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1)
    return strip


def encode(strip, cap: int = CAP) -> bytes:
    """Step the quality down until the strip fits; the last attempt is returned as is."""
    data = b""
    for quality in QUALITIES:
        ok, buffer = cv2.imencode(".jpg", strip, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if not ok:
            continue
        data = buffer.tobytes()
        if len(data) <= cap:
            break
    return data


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="G361 alignment strip (eye check)")
    for flag in ("game-id", "refetched", "tracking", "alignment", "out"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    rows = landmarks(args.alignment, args.game_id)
    if not rows:
        print("no_landmarks game_id=%s" % args.game_id)
        return 0
    errors = [abs(float(r["error_frames"])) for r in rows if r["error_frames"] != "UNKNOWN"]
    row = rows[len(rows) // 2]
    index = int(row["archived_frame"])
    image = frame_at(args.refetched, index)
    if image is None:
        print("no_frame game_id=%s index=%d" % (args.game_id, index))
        return 0
    caption = "%s f%d arch %ss refetch %ss err %s fr (section max %s)" % (
        args.game_id, index, row["archived_timestamp"], row["refetched_pts"],
        row["error_frames"], "%.4f" % max(errors) if errors else "UNKNOWN")
    boxes = archived_boxes(Path(args.tracking) / args.game_id / "tracking_data.csv", index)
    data = encode(compose(image, boxes, caption))
    out = Path(args.out) / ("%s.jpg" % args.game_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print("strip=%s bytes=%d boxes=%d" % (out, len(data), len(boxes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
