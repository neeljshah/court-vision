"""Independent off-pod read-back of every retained source this row replayed.

Re-hashes the retained bytes on the PC, re-decodes the container's own
dimensions, frame count and frame rate, and compares them against G402's landed
source receipt.  A disagreement is recorded, never silently corrected.
"""
from __future__ import annotations

import csv
import hashlib
from fractions import Fraction
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g410_measure import write_csv


def rehash(path: Path) -> tuple:
    """Return (bytes, sha256) read back from the retained copy on this machine."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def probe(path: Path) -> dict:
    """Read back container dimensions, frame count and rational frame rate."""
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"readback_status": "OPEN_FAILED", "readback_width": "",
                "readback_height": "", "readback_frames": "",
                "readback_fps_rational": "", "readback_fps_float": ""}
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    rational = Fraction(fps).limit_denominator(1001) if fps > 0 else Fraction(0)
    return {"readback_status": "OK", "readback_width": width,
            "readback_height": height, "readback_frames": frames,
            "readback_fps_rational": "%d/%d" % (rational.numerator,
                                                rational.denominator),
            "readback_fps_float": "%.6f" % fps}


def main(parent: str, queue_tsv: str, out_csv: str) -> None:
    """Write the G410 source receipt for every section in the sealed queue."""
    landed = {(r["draw_kind"], r["section_id"]): r for r in
              csv.DictReader(open(Path(parent) / "source_receipts.csv",
                                  newline="", encoding="utf-8"))}
    rows = []
    for line in Path(queue_tsv).read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        kind, section, local, sha, start, frames, pod_path = line.split(chr(9))
        path = Path(local)
        if not path.exists():
            rows.append({"draw_kind": kind, "section_id": section,
                         "retained_path": local, "retained_status": "ABSENT"})
            continue
        size, digest = rehash(path)
        reference = landed.get((kind, section), {})
        record = {
            "draw_kind": kind, "section_id": section, "retained_path": local,
            "retained_status": "RETAINED", "retained_bytes": size,
            "retained_sha256": digest,
            "matches_g402_receipt": int(digest == sha),
            "g402_sha256": sha, "pod_source_path": pod_path,
            "replay_start_frame": start, "replay_frames": frames,
            "g402_width": reference.get("width", ""),
            "g402_height": reference.get("height", ""),
            "g402_avg_fps": reference.get("avg_fps", ""),
        }
        record.update(probe(path))
        record["dimensions_agree"] = int(
            str(record["readback_width"]) == str(record["g402_width"])
            and str(record["readback_height"]) == str(record["g402_height"]))
        rows.append(record)
    write_csv(Path(out_csv), rows)
    print("sources=%d matched=%d" % (
        len(rows), sum(1 for r in rows if r.get("matches_g402_receipt") == 1)))


if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2], sys.argv[3])
