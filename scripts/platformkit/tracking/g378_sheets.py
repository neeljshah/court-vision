"""G378 blind anchor sheets and the eye-check renders.

A sheet carries the frame and nothing else: no annotation, no overlay, no cue output, no section
name and no other rater's label. Its file name is the first 12 hex characters of the frame key, so
it leaks no ordering. The renders are built only AFTER scoring and are never shown to a rater.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2

SHEET_WIDTH, SHEET_CAP, RENDER_WIDTH, RENDER_CAP = 960, 200_000, 640, 90_000
RENDER_MINIMUM = 30
ANCHOR_COLUMNS = ("frame_key,sheet,section,game,cache").split(",")
RENDER_COLUMNS = ("frame_key,render,reason,call,reference,left_mass,right_mass").split(",")


def _rows(path: Path) -> list:
    with path.open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, image, cap: int) -> bool:
    for quality in (85, 72, 60, 48, 36):
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok and encoded.nbytes <= cap:
            path.write_bytes(encoded.tobytes())
            return True
    return False


def _resize(frame, width: int):
    height = int(round(frame.shape[0] * width / frame.shape[1]))
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)


def sheets(frames: Path, cache: Path, out: Path, anchors: Path) -> int:
    """One blind sheet per decoded frame, in frame-key order."""
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in sorted(_rows(frames), key=lambda row: row["frame_key"]):
        frame = cv2.imread(str(cache / item["cache"]), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("missing cache for %s" % item["frame_key"])
        name = item["frame_key"][:12] + ".jpg"
        if not _write(out / name, _resize(frame, SHEET_WIDTH), SHEET_CAP):
            raise ValueError("cannot write sheet for %s" % item["frame_key"])
        rows.append({"frame_key": item["frame_key"], "sheet": name, "section": item["section"],
                     "game": item["game"], "cache": item["cache"]})
    anchors.parent.mkdir(parents=True, exist_ok=True)
    with anchors.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=ANCHOR_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("SHEETS n=%d unique=%d" % (len(rows), len({row["sheet"] for row in rows})))
    return 0


def _even(items: list, count: int) -> list:
    """Evenly spaced over the whole sorted set -- never a head slice (contract A3, B7)."""
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    step = len(items) / float(count)
    return [items[min(len(items) - 1, int(index * step))] for index in range(count)]


def render_set(scored: list) -> list:
    """Every UNKNOWN call, every wrong case, then an even sample up to the sealed minimum."""
    chosen, reasons = [], {}
    for row in sorted(scored, key=lambda item: item["frame_key"]):
        if row["call"] == "UNKNOWN":
            reasons[row["frame_key"]] = "cue_unknown"
        elif row["reference"] in ("left", "right") and row["call"].lower() != row["reference"]:
            reasons[row["frame_key"]] = "wrong"
    chosen = [row for row in sorted(scored, key=lambda item: item["frame_key"])
              if row["frame_key"] in reasons]
    remainder = [row for row in sorted(scored, key=lambda item: item["frame_key"])
                 if row["frame_key"] not in reasons]
    for row in _even(remainder, max(0, RENDER_MINIMUM - len(chosen))):
        reasons[row["frame_key"]] = "even_sample"
        chosen.append(row)
    return sorted(chosen, key=lambda item: item["frame_key"]), reasons


def renders(scored_csv: Path, cache: Path, out: Path, index: Path) -> int:
    """The eye check: the anchor band border plus the call, the reference and the two masses."""
    from scripts.platformkit.tracking.g378_cue import band_bounds

    scored = _rows(scored_csv)
    chosen, reasons = render_set(scored)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for row in chosen:
        frame = cv2.imread(str(cache / row["cache"]), cv2.IMREAD_COLOR)
        if frame is None:
            raise ValueError("missing cache for %s" % row["frame_key"])
        top, bottom = band_bounds(frame.shape[0])
        image = _resize(frame, RENDER_WIDTH)
        scale = RENDER_WIDTH / float(frame.shape[1])
        cv2.rectangle(image, (1, int(top * scale)), (RENDER_WIDTH - 2, int(bottom * scale)),
                      (0, 255, 255), 2)
        cv2.line(image, (RENDER_WIDTH // 2, 0), (RENDER_WIDTH // 2, image.shape[0]), (0, 0, 255), 1)
        text = "%s ref=%s L=%s R=%s" % (row["call"], row["reference"] or "NONE",
                                        row["left_mass"], row["right_mass"])
        cv2.putText(image, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(image, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        name = row["frame_key"][:12] + ".jpg"
        if not _write(out / name, image, RENDER_CAP):
            raise ValueError("cannot write render for %s" % row["frame_key"])
        written.append({"frame_key": row["frame_key"], "render": name,
                        "reason": reasons[row["frame_key"]], "call": row["call"],
                        "reference": row["reference"], "left_mass": row["left_mass"],
                        "right_mass": row["right_mass"]})
    index.parent.mkdir(parents=True, exist_ok=True)
    with index.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=RENDER_COLUMNS)
        writer.writeheader()
        writer.writerows(written)
    counts = {"cue_unknown": 0, "wrong": 0, "even_sample": 0}
    for row in written:
        counts[row["reason"]] += 1
    print("RENDERS n=%d unknown=%d wrong=%d even=%d"
          % (len(written), counts["cue_unknown"], counts["wrong"], counts["even_sample"]))
    return 0


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("sheets")
    for name in ("frames", "cache", "out", "anchors"):
        one.add_argument("--" + name, required=True)
    two = sub.add_parser("renders")
    for name in ("scored", "cache", "out", "index"):
        two.add_argument("--" + name, required=True)
    args = parser.parse_args(argv[1:])
    if args.action == "sheets":
        return sheets(Path(args.frames), Path(args.cache), Path(args.out), Path(args.anchors))
    return renders(Path(args.scored), Path(args.cache), Path(args.out), Path(args.index))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
