"""G380 eye check: 30 evenly spaced overlays coloured by position_source.

The even sample is the evidence (contract A3/B7); HELD and CLAMP runs are added
as clearly named supplementary frames when the even sample does not happen to
contain them, so the reviewer can see the two branches G368 could not separate.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2

COLORS = {"DETECTION": (0, 200, 0), "PREDICTION": (0, 165, 255), "CLAMP": (0, 0, 255),
          "SUBPIXEL": (255, 0, 255), "HELD": (255, 255, 0), "UNKNOWN": (128, 128, 128)}
FIELDS = ("file", "frame", "kind", "labels")


def _rows_by_frame(csv_path: Path) -> dict:
    grouped = defaultdict(list)
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            try:
                grouped[int(row["frame"])].append(row)
            except (KeyError, ValueError):
                continue
    return grouped


def _runs(grouped: dict, label: str) -> list:
    """Longest consecutive stretch of frames in which `label` appears."""
    frames = sorted(f for f, rows in grouped.items()
                    if any(r.get("position_source") == label for r in rows))
    best, current = [], []
    for frame in frames:
        if current and frame - current[-1] > 12:
            best, current = max(best, current, key=len), [frame]
        else:
            current.append(frame)
    return max(best, current, key=len) if frames else []


def _draw(frame_bgr, rows):
    for row in rows:
        try:
            box = [int(float(row["bbox_x1"])), int(float(row["bbox_y1"])),
                   int(float(row["bbox_x2"])), int(float(row["bbox_y2"]))]
        except (KeyError, ValueError):
            continue
        label = row.get("position_source", "UNKNOWN")
        color = COLORS.get(label, COLORS["UNKNOWN"])
        cv2.rectangle(frame_bgr, (box[0], box[1]), (box[2], box[3]), color, 2)
        cv2.putText(frame_bgr, label[:4], (box[0], max(12, box[1] - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    return frame_bgr


def render(video: Path, csv_path: Path, out: Path, count: int) -> dict:
    grouped = _rows_by_frame(csv_path)
    frames = sorted(grouped)
    if not frames:
        raise SystemExit("no rows in %s" % csv_path)
    step = len(frames) / float(count)
    picks = [(frames[min(len(frames) - 1, int(i * step))], "EVEN") for i in range(count)]
    even_labels = Counter(r.get("position_source", "UNKNOWN")
                          for frame, _ in picks for r in grouped[frame])
    for label in ("HELD", "CLAMP"):
        if even_labels.get(label):
            continue
        run = _runs(grouped, label)
        picks.extend((run[i * max(1, len(run) // 3)], "SUPP_" + label)
                     for i in range(min(3, len(run))))
    out.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video))
    index, written = [], 0
    for frame_id, kind in picks:
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ok, image = capture.read()
        if not ok or image is None:
            continue
        rows = grouped[frame_id]
        image = _draw(image, rows)
        scale = 640.0 / image.shape[1]
        image = cv2.resize(image, (640, int(image.shape[0] * scale)))
        name = "%s_%06d.jpg" % (kind.lower(), frame_id)
        cv2.imwrite(str(out / name), image, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
        index.append({"file": name, "frame": frame_id, "kind": kind,
                      "labels": json.dumps(dict(Counter(
                          r.get("position_source", "UNKNOWN") for r in rows)), sort_keys=True)})
        written += 1
    capture.release()
    with (out / "overlays_index.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIELDS))
        writer.writeheader()
        writer.writerows(index)
    return {"written": written, "even_requested": count,
            "even_label_counts": dict(even_labels),
            "distinct_frames": len(frames),
            "supplementary": sum(1 for item in index if item["kind"] != "EVEN")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n", type=int, default=30)
    args = parser.parse_args()
    print(json.dumps(render(Path(args.video), Path(args.csv), Path(args.out), args.n),
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
