"""G402 off-pod retention receipts and the independent decoded-PTS window census.

The receiver directory is read back independently of the pod: every retained
object is re-digested from PC disk and its window PTS are probed here, so the
window boundary census never depends on the producer that was measured.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

RECEIPT_FIELDS = ("draw_kind", "draw_order", "section_id", "competition", "game",
                  "source_tree", "source_path", "source_bytes", "source_sha256",
                  "receiver_dir", "receiver_path", "receiver_bytes", "receiver_sha256",
                  "bytes_equal", "sha256_equal", "source_status", "usable_span_s",
                  "usable_start_s", "width", "height", "avg_fps", "codec_name")
PTS_FIELDS = ("draw_kind", "section_id", "start_frame", "frames", "window_start_s",
              "window_end_s", "probed_frames", "first_source_frame", "last_source_frame",
              "first_pts_s", "last_pts_s", "pts_elapsed_s", "monotonic", "probe_status")


def digest(path: Path) -> tuple:
    sha, total = hashlib.sha256(), 0
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 22), b""):
            sha.update(block)
            total += len(block)
    return sha.hexdigest(), total


def window_pts(path: Path, start_frame: int, frames: int) -> dict:
    """Probe the decoded presentation stamps of the sealed window only."""
    if not path.is_file():
        return {"probe_status": "RECEIVER_OBJECT_ABSENT", "probed_frames": 0}
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "frame=pts_time,best_effort_timestamp_time", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True)
    stamps = []
    for line in done.stdout.splitlines():
        token = line.split(",")[0].strip()
        try:
            stamps.append(float(token))
        except ValueError:
            continue
    window = stamps[start_frame:start_frame + frames]
    if not window:
        return {"probe_status": "WINDOW_PTS_EMPTY", "probed_frames": 0}
    return {"probe_status": "OK", "probed_frames": len(window),
            "first_source_frame": start_frame,
            "last_source_frame": start_frame + len(window) - 1,
            "first_pts_s": round(window[0], 6), "last_pts_s": round(window[-1], 6),
            "pts_elapsed_s": round(window[-1] - window[0], 6),
            "monotonic": int(window == sorted(window))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--receiver", required=True)
    args = parser.parse_args()
    evidence, receiver = Path(args.evidence), Path(args.receiver)
    with (evidence / "draw.csv").open(newline="", encoding="ascii") as handle:
        plan = list(csv.DictReader(handle))
    receipts, stamps = [], []
    for row in plan:
        local = receiver / Path(row["source_path"]).name
        entry = {key: row.get(key, "") for key in RECEIPT_FIELDS if key in row}
        entry["receiver_dir"] = str(receiver)
        entry["receiver_path"] = str(local)
        if local.is_file():
            sha, size = digest(local)
            entry.update(receiver_sha256=sha, receiver_bytes=size,
                         bytes_equal=int(str(size) == str(row["source_bytes"])),
                         sha256_equal=int(sha == row["source_sha256"]),
                         source_status="RETAINED")
        else:
            entry.update(receiver_sha256="", receiver_bytes=0, bytes_equal=0,
                         sha256_equal=0, source_status="NOT_RETAINED")
        receipts.append(entry)
        stamps.append({"draw_kind": row["draw_kind"], "section_id": row["section_id"],
                       "start_frame": row["start_frame"], "frames": row["frames"],
                       "window_start_s": row["window_start_s"],
                       "window_end_s": row["window_end_s"],
                       **window_pts(local, int(row["start_frame"]), int(row["frames"]))})
    for path, fields, rows in ((evidence / "source_receipts.csv", RECEIPT_FIELDS, receipts),
                               (evidence / "window_pts.csv", PTS_FIELDS, stamps)):
        with path.open("w", newline="", encoding="ascii") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    out = {"planned": len(plan),
           "retained": sum(1 for item in receipts if item["source_status"] == "RETAINED"),
           "sha256_equal": sum(item["sha256_equal"] for item in receipts),
           "window_pts_ok": sum(1 for item in stamps if item["probe_status"] == "OK"),
           "window_pts_monotonic": sum(1 for item in stamps if item.get("monotonic") == 1),
           "receiver_dir": str(receiver)}
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
