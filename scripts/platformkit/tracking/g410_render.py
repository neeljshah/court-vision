"""G410 native-pixel eye cards for the drawn ticks.

Each card decodes the retained source at the selected frame at its own native
resolution and draws, in that one image: the stored box exactly as serialized,
the same box translated by the archived TOPCUT origin, the archived projected
foot, and the same track's predecessor box.  Nothing is resized.
"""
from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g410_measure import PAD, TOPCUT, write_csv

RAW = (0, 0, 255)          # stored box, as serialized
SHIFTED = (0, 200, 0)      # stored box translated by the archived crop origin
PRIOR = (255, 128, 0)      # same-track predecessor box, translated
FOOT = (255, 0, 255)       # archived projected foot, translated


def decode(path: Path, frame_index: int):
    """Decode one native frame by index; return (image, reported_index)."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return None, -1
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
    ok, image = cap.read()
    reported = int(cap.get(cv2.CAP_PROP_POS_FRAMES)) - 1
    cap.release()
    return (image if ok else None), reported


def box_of(row: dict, prefix: str = ""):
    """Return the serialized xyxy box under an optional column prefix."""
    try:
        return tuple(float(row[prefix + name]) for name in
                     ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"))
    except (KeyError, ValueError, TypeError):
        return None


def draw_card(image, row: dict, prior_box, out_path: Path) -> dict:
    """Draw one native-pixel card and return its render receipt."""
    box = box_of(row)
    height, width = image.shape[:2]
    def rect(target, colour, dy):
        cv2.rectangle(image,
                      (int(round(target[0])), int(round(target[1] + dy))),
                      (int(round(target[2])), int(round(target[3] + dy))),
                      colour, 2)
    rect(box, RAW, 0)
    rect(box, SHIFTED, TOPCUT)
    if prior_box is not None:
        rect(prior_box, PRIOR, TOPCUT)
    foot = (int(row["archived_head_x"]), int(row["archived_foot_y"]) + TOPCUT)
    cv2.circle(image, foot, 5, FOOT, -1)
    caption = ("%s f=%s pid=%s %s ret_age=%s box_l2=%s px topcut=%d pad=%d"
               % (row["section_id"], row["frame"], row["player_id"],
                  row["position_source"], row["retained_position_age"],
                  row["box_l2_px"] or "NA", TOPCUT, PAD))
    cv2.putText(image, caption, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(image, caption, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 1, cv2.LINE_AA)
    cv2.imwrite(str(out_path), image,
                [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    digest = hashlib.sha256(out_path.read_bytes()).hexdigest()
    return {"render_width": width, "render_height": height, "sha256": digest}


def main(per_row_csv: str, source_receipts: str, out_dir: str) -> None:
    """Render one card per drawn tick for each target class and index them."""
    out = Path(out_dir)
    renders = out / "renders"
    renders.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(open(per_row_csv, newline="", encoding="ascii")))
    sources = {(r["draw_kind"], r["section_id"]): r["receiver_path"]
               for r in csv.DictReader(open(source_receipts, newline="",
                                            encoding="utf-8"))}
    mask = {(r["draw_kind"], r["section_id"], r["frame"], r["player_id"]): r
            for r in rows}
    sealed = set((d["class"], d["draw_kind"], d["section_id"], d["frame"])
                 for d in csv.DictReader(open(Path(out_dir) / "draw.csv",
                                              newline="", encoding="ascii")))
    index = []
    for label in ("CLAMP", "SUBPIXEL"):
        picked = {}
        for row in rows:
            if row["position_source"] != label or row["role"] != "SELECTED":
                continue
            key = (row["draw_kind"], row["section_id"], row["frame"])
            if key in picked:
                continue
            picked[key] = row
        for key in sorted(picked, key=lambda k: (k[0], k[1], int(k[2]))):
            row = picked[key]
            path = Path(sources[(row["draw_kind"], row["section_id"])])
            image, reported = decode(path, int(row["frame"]))
            name = "%s_%s_f%s_p%s.jpg" % (label, row["section_id"],
                                          row["frame"], row["player_id"])
            record = {"class": label, "draw_kind": row["draw_kind"],
                      "section_id": row["section_id"], "frame": row["frame"],
                      "player_id": row["player_id"], "render": name,
                      "decoded_index_reported": reported,
                      "decode_status": "OK" if image is not None else "DECODE_FAILED",
                      "on_sealed_class_draw": int(
                          (label, row["draw_kind"], row["section_id"],
                           row["frame"]) in sealed)}
            if image is None:
                index.append({**record, "render_width": "", "render_height": "",
                              "sha256": ""})
                continue
            prior = mask.get((row["draw_kind"], row["section_id"],
                              row["predecessor_frame"], row["player_id"]))
            record.update(draw_card(image, row,
                                    box_of(prior) if prior else None,
                                    renders / name))
            index.append(record)
    write_csv(out / "eye_index.csv", index)
    print("cards=%d" % len(index))


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])
