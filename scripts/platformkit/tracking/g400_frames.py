"""G400 retention receipt, PTS probe and native frame draw (PC side).

Every drawn section is re-hashed on this box against the pod digest BEFORE any
pixel is read, its full PTS schedule is probed, and ten interior targets nearest
k/11 are decoded at native resolution with sheet_scale 1.0. A failed decode stays
a planned state; it is never replaced, resampled or upscaled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

TARGETS = 10
MIN_SPACING_S = 1.0
RECEIPT_FIELDS = ("video_id", "median_section_file", "pod_source_digest",
                  "pc_source_digest", "byte_agreement", "receiver_path", "bytes",
                  "width", "height", "fps", "duration_s", "decode_ok", "status")
PTS_FIELDS = ("video_id", "median_section_file", "packets", "first_pts_s", "last_pts_s",
              "span_s", "median_delta_s", "schedule_sha256", "probe_status")
MANIFEST_FIELDS = ("frame_key", "video_id", "competition", "canonical_game",
                   "median_section_file", "k", "target_fraction", "target_pts_s",
                   "chosen_pts_s", "spacing_prev_s", "width", "height", "sheet_scale",
                   "sheet_path", "sheet_sha256", "raw_pixel_sha256", "status")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def pts_schedule(path: Path) -> list[float]:
    """Packet-derived presentation schedule of the video stream, ascending."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "packet=pts_time", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, timeout=900)
    values = []
    for line in out.stdout.splitlines():
        token = line.strip().rstrip(",")
        try:
            values.append(float(token))
        except ValueError:
            continue
    return sorted(values)


def decode_native(path: Path, pts: float, width: int, height: int) -> bytes | None:
    """Decode one frame at the sealed timestamp as native rgb24 bytes."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{pts:.6f}", "-i", str(path),
                          "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, timeout=600)
    expected = width * height * 3
    return out.stdout if len(out.stdout) == expected else None


def write_jpeg(raw: bytes, width: int, height: int, target: Path) -> None:
    from PIL import Image
    Image.frombytes("RGB", (width, height), raw).save(target, "JPEG", quality=92)


def choose_targets(schedule: list[float]) -> list[tuple[int, float, float]]:
    """Ten interior frames nearest k/11 of the decoded span; earlier wins a tie."""
    if len(schedule) < TARGETS:
        return []
    first, last = schedule[0], schedule[-1]
    chosen: list[tuple[int, float, float]] = []
    for k in range(1, TARGETS + 1):
        want = first + (last - first) * k / (TARGETS + 1)
        best = min(schedule, key=lambda value: (abs(value - want), value))
        chosen.append((k, want, best))
    return chosen


def run(args) -> int:
    out = Path(args.out_dir)
    receiver = Path(args.receiver)
    sheets = Path(args.sheets)
    sheets.mkdir(parents=True, exist_ok=True)
    with (out / "draw.csv").open(encoding="ascii", newline="") as handle:
        draw = list(csv.DictReader(handle))
    receipts, pts_rows, manifest = [], [], []
    for row in draw:
        name = Path(row["median_section_path"]).name
        local = receiver / name
        width, height = int(row["width"]), int(row["height"])
        receipt = {"video_id": row["video_id"], "median_section_file": name,
                   "pod_source_digest": row["source_digest"], "pc_source_digest": "",
                   "byte_agreement": 0, "receiver_path": str(local), "bytes": 0,
                   "width": width, "height": height, "fps": row["fps"],
                   "duration_s": row["duration_s"], "decode_ok": 0,
                   "status": "RECEIVER_ABSENT"}
        schedule: list[float] = []
        if local.is_file():
            receipt["bytes"] = local.stat().st_size
            receipt["pc_source_digest"] = sha256_file(local)
            receipt["byte_agreement"] = int(receipt["pc_source_digest"]
                                            == row["source_digest"])
            receipt["status"] = ("RETAINED" if receipt["byte_agreement"]
                                 else "RECEIVER_MISMATCH")
            if receipt["byte_agreement"]:
                schedule = pts_schedule(local)
        deltas = sorted(b - a for a, b in zip(schedule, schedule[1:])) if len(schedule) > 1 else []
        pts_rows.append({"video_id": row["video_id"], "median_section_file": name,
                         "packets": len(schedule),
                         "first_pts_s": schedule[0] if schedule else "",
                         "last_pts_s": schedule[-1] if schedule else "",
                         "span_s": round(schedule[-1] - schedule[0], 6) if schedule else "",
                         "median_delta_s": round(deltas[len(deltas) // 2], 6) if deltas else "",
                         "schedule_sha256": hashlib.sha256(
                             ("\n".join(f"{value:.6f}" for value in schedule)
                              ).encode("ascii")).hexdigest() if schedule else "",
                         "probe_status": "ok" if schedule else "no_schedule"})
        targets = choose_targets(schedule)
        previous = None
        for index in range(TARGETS):
            k = index + 1
            entry = {"frame_key": "", "video_id": row["video_id"],
                     "competition": row["competition"],
                     "canonical_game": row["canonical_game"],
                     "median_section_file": name, "k": k,
                     "target_fraction": round(k / (TARGETS + 1), 6),
                     "target_pts_s": "", "chosen_pts_s": "", "spacing_prev_s": "",
                     "width": width, "height": height, "sheet_scale": "1.0",
                     "sheet_path": "", "sheet_sha256": "", "raw_pixel_sha256": "",
                     "status": "DECODE_FAILED"}
            if index < len(targets):
                _, want, chosen = targets[index]
                entry["target_pts_s"] = round(want, 6)
                entry["chosen_pts_s"] = round(chosen, 6)
                entry["spacing_prev_s"] = ("" if previous is None
                                           else round(chosen - previous, 6))
                previous = chosen
                raw = decode_native(local, chosen, width, height)
                if raw:
                    digest = hashlib.sha256(raw).hexdigest()
                    sheet = sheets / (digest[:12] + ".jpg")
                    write_jpeg(raw, width, height, sheet)
                    entry.update({"frame_key": digest, "raw_pixel_sha256": digest,
                                  "sheet_path": str(sheet),
                                  "sheet_sha256": sha256_file(sheet),
                                  "status": "PLANNED"})
            if not entry["frame_key"]:
                entry["frame_key"] = hashlib.sha256(
                    (row["video_id"] + "|" + str(k)).encode("ascii")).hexdigest()
            manifest.append(entry)
        receipt["decode_ok"] = int(any(item["status"] == "PLANNED" for item in manifest
                                       if item["video_id"] == row["video_id"]))
        receipts.append(receipt)
        print("SECTION", row["video_id"], receipt["status"], "packets", len(schedule),
              flush=True)
    for path, fields, rows in (("source_receipts.csv", RECEIPT_FIELDS, receipts),
                               ("pts.csv", PTS_FIELDS, pts_rows),
                               ("native_manifest.csv", MANIFEST_FIELDS, manifest)):
        with (out / path).open("w", encoding="ascii", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    keys = [row["frame_key"] for row in manifest]
    summary = {"sections": len(receipts),
               "retained": sum(row["byte_agreement"] for row in receipts),
               "planned_states": len(manifest),
               "decoded": sum(1 for row in manifest if row["status"] == "PLANNED"),
               "distinct_frame_keys": len(set(keys)),
               "distinct_raw_pixel_digests": len({row["raw_pixel_sha256"]
                                                  for row in manifest
                                                  if row["raw_pixel_sha256"]})}
    (out / "native_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True)
                                             + "\n", encoding="ascii")
    print(json.dumps(summary, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g400_frames")
    for flag in ("--out-dir", "--receiver", "--sheets"):
        parser.add_argument(flag, required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
