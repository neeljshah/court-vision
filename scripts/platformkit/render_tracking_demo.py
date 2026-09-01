"""Render tracking output as demo video: pixel overlays or a top-down court.

Two honest modes -- both draw ONLY what the pipeline actually emitted:

  overlay  -- for image_px rows (football/soccer/baseball): x,y ARE pixels, so
              dots go straight onto the source frames. No projection invented.
  topdown  -- for court-space rows (tennis court_feet): animate the tracked
              positions on a schematic court. This is the pipeline's actual
              output space; overlaying it on video would require inverting the
              homography per frame, which the CSV does not carry.

Headless only (cv2.VideoWriter, never imshow). Output mp4 is small on purpose:
these are GitHub evidence clips, not archives.

Run:
  python -m scripts.platformkit.render_tracking_demo overlay \
      --video data/videos/reference/football.mp4 --csv <csv> --out demo.mp4
  python -m scripts.platformkit.render_tracking_demo topdown \
      --csv <csv> --sport tennis --out demo.mp4
"""
from __future__ import annotations

import argparse
import collections
import csv
import sys
from pathlib import Path

import cv2
import numpy as np

COLORS = [(60, 200, 60), (60, 120, 255), (255, 160, 40), (200, 60, 200),
          (40, 220, 220), (120, 120, 255), (255, 255, 80), (160, 255, 120)]
COURTS = {"tennis": (78.0, 36.0), "basketball": (94.0, 50.0)}


def _rows_by_frame(path: Path) -> dict:
    table: dict = collections.defaultdict(list)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for row in csv.DictReader(handle):
            if (row.get("cls") or "player") != "player":
                continue
            try:
                table[int(float(row["frame"]))].append(
                    (int(float(row["track_id"])), float(row["x"]), float(row["y"])))
            except (KeyError, TypeError, ValueError):
                continue
    return table


def overlay(video: Path, csv_path: Path, out: Path, max_seconds: int) -> int:
    """Draw image_px tracking dots onto the source frames."""
    table = _rows_by_frame(csv_path)
    if not table:
        print("no rows in %s" % csv_path)
        return 1
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        print("cannot open %s" % video)
        return 1
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height))
    first, last = min(table), max(table)
    frame_index, written = 0, 0
    budget = int(max_seconds * fps)
    held: list = []
    held_age = 0
    while written < budget:
        ok, frame = capture.read()
        if not ok or frame_index > last:
            break
        if frame_index >= first:
            # Display-only carry: the tracker samples every Nth frame (stride),
            # so 2 of 3 video frames have no rows and dots would flicker. Rows
            # are held for at most 3 frames -- real observations, re-drawn,
            # never interpolated or invented.
            if frame_index in table:
                held, held_age = table[frame_index], 0
            else:
                held_age += 1
                if held_age > 3:
                    held = []
            for track_id, x, y in held:
                color = COLORS[track_id % len(COLORS)]
                cv2.circle(frame, (int(x), int(y)), 6, color, 2)
                cv2.putText(frame, str(track_id), (int(x) + 8, int(y) - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
            cv2.putText(frame, "declared image_px -- preserved corpus, not court coordinates",
                        (10, height - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (255, 255, 255), 1)
            writer.write(frame)
            written += 1
        frame_index += 1
    capture.release()
    writer.release()
    print("wrote %s (%d frames)" % (out, written))
    return 0 if written else 1


def topdown(csv_path: Path, sport: str, out: Path, max_seconds: int) -> int:
    """Animate court-space rows on a schematic court."""
    length, breadth = COURTS[sport]
    table = _rows_by_frame(csv_path)
    if not table:
        print("no rows in %s" % csv_path)
        return 1
    scale, margin = 9, 40
    width = int(length * scale) + 2 * margin
    height = int(breadth * scale) + 2 * margin
    fps = 30.0
    writer = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"),
                             fps, (width, height))

    def to_px(x: float, y: float) -> tuple:
        return int(margin + x * scale), int(margin + (breadth - y) * scale)

    trails: dict = collections.defaultdict(list)
    frames = sorted(table)
    budget = int(max_seconds * fps)
    for frame_number in frames[:budget]:
        canvas = np.full((height, width, 3), (40, 90, 45), dtype=np.uint8)
        cv2.rectangle(canvas, to_px(0, breadth), to_px(length, 0), (255, 255, 255), 2)
        if sport == "tennis":
            cv2.line(canvas, to_px(length / 2, 0), to_px(length / 2, breadth),
                     (255, 255, 255), 2)                       # net
            for x in (21.0, 57.0):                             # service lines
                cv2.line(canvas, to_px(x, 4.5), to_px(x, 31.5), (255, 255, 255), 1)
            cv2.line(canvas, to_px(21, 18), to_px(57, 18), (255, 255, 255), 1)
            for y in (4.5, 31.5):                              # singles sidelines
                cv2.line(canvas, to_px(0, y), to_px(length, y), (255, 255, 255), 1)
        for track_id, x, y in table[frame_number]:
            trails[track_id].append((x, y))
            color = COLORS[track_id % len(COLORS)]
            for a, b in zip(trails[track_id][-25:], trails[track_id][-24:]):
                cv2.line(canvas, to_px(*a), to_px(*b), color, 1)
            cv2.circle(canvas, to_px(x, y), 7, color, -1)
        cv2.putText(canvas, "%s -- tracked positions in court feet (homography-calibrated)"
                    % sport, (margin, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (255, 255, 255), 1)
        cv2.putText(canvas, "frame %d" % frame_number, (margin, height - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
        writer.write(canvas)
    writer.release()
    print("wrote %s (%d frames)" % (out, min(len(frames), budget)))
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("overlay", "topdown"))
    parser.add_argument("--video", type=Path)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--sport", default="tennis", choices=sorted(COURTS))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=12)
    args = parser.parse_args(argv[1:])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "overlay":
        if args.video is None:
            print("overlay needs --video")
            return 2
        return overlay(args.video, args.csv, args.out, args.seconds)
    return topdown(args.csv, args.sport, args.out, args.seconds)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
