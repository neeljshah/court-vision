"""G385 pin-and-copy runner: one pass per section, container deleted after decode.

Sealed by `docs/evidence/tracking/g385_nonplay_shadow_mask_2026-09-10/
g385_prereg_2026-09-10.md` (SEAL sha256
1dd44f12075456bd18b5797815d23ba8b4bf3e13eb24417d08d813c0f085d589). Reads a ledger
census only; writes nothing under /workspace/data and moves no threshold or flag.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g385_sample import (SEED, TICKS_PER_SECTION,
                                                      even_sections, interior_indices)
from scripts.platformkit.tracking.g385_sheets import render_native

FORMAT = "270/312/137/best[height>=720]/best"
FIELDS = ("sheet_id", "tick_key", "section_id", "video_id", "competition", "sport",
          "offset_s", "source_duration", "window_start_s", "window_end_s",
          "container_bytes", "container_sha256", "width", "height", "frame_count",
          "avg_frame_rate", "codec_name", "frame_index", "sheet_bytes", "sheet_sha256",
          "evidence_status", "absent_reason", "pinned_utc")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields=FIELDS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def eligible_pool(census: list[dict[str, str]], dev_videos: set[str]) -> list[dict[str, str]]:
    """Development-disjoint eligible sections, shaped for the sealed even sampler."""
    out = []
    for row in census:
        if row.get("eligible") != "1" or row.get("video_id") in dev_videos:
            continue
        out.append({**row, "section_id": row["game_id"], "competition": row.get("prefix", "")})
    return out


def fetch(row: dict[str, str], scratch: Path, timeout: int) -> tuple[Path | None, str]:
    """Fetch the whole pinned section window in one pass; caller deletes it after decode."""
    target = scratch / (row["section_id"] + ".mp4")
    target.unlink(missing_ok=True)
    command = ["nice", "-n", "10", "yt-dlp", "-f", FORMAT, "--no-playlist", "--no-warnings",
               "--download-sections", "*%s-%s" % (row["window_start_s"], row["window_end_s"]),
               "--merge-output-format", "mp4", "-o", str(target), "--",
               "https://www.youtube.com/watch?v=" + row["video_id"]]
    try:
        subprocess.run(command, check=True, timeout=timeout, capture_output=True)
    except subprocess.CalledProcessError as error:
        tail = (error.stderr or b"").decode("ascii", "replace").strip().splitlines()
        return None, (tail[-1][:120] if tail else "no_stderr")
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, type(error).__name__
    if target.exists() and target.stat().st_size > 0:
        return target, ""
    return None, "empty_container"


def probe(path: Path) -> dict[str, str]:
    """Record the container facts every pinned source must carry (A9, G361)."""
    done = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=width,height,nb_read_frames,avg_frame_rate,codec_name",
         "-of", "json", str(path)], check=True, capture_output=True, text=True, timeout=900)
    stream = json.loads(done.stdout)["streams"][0]
    return {"width": str(stream.get("width")), "height": str(stream.get("height")),
            "frame_count": str(stream.get("nb_read_frames")),
            "avg_frame_rate": str(stream.get("avg_frame_rate")),
            "codec_name": str(stream.get("codec_name"))}


def plan_windows(sections: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pin each section window from its ledger offset and duration."""
    out = []
    for row in sections:
        start = int(float(row["offset_s"]))
        end = start + int(math.ceil(float(row["source_duration"])))
        out.append({**row, "window_start_s": str(start), "window_end_s": str(end)})
    return out


def absent_rows(section: dict[str, str], reason: str, stamp: str) -> list[dict[str, str]]:
    """Every planned tick of an unfetchable section is still one of the 360 attempts (B3)."""
    return [{"tick_key": "%s:%06d" % (section["section_id"], index), "sheet_id": "",
             "section_id": section["section_id"], "video_id": section["video_id"],
             "competition": section["competition"], "sport": section.get("sport", ""),
             "offset_s": section["offset_s"], "source_duration": section["source_duration"],
             "window_start_s": section["window_start_s"], "window_end_s": section["window_end_s"],
             "container_bytes": "", "container_sha256": "", "width": "", "height": "",
             "frame_count": "", "avg_frame_rate": "", "codec_name": "", "frame_index": str(index),
             "sheet_bytes": "", "sheet_sha256": "", "evidence_status": "ABSENT",
             "absent_reason": reason, "pinned_utc": stamp}
            for index in range(TICKS_PER_SECTION)]


def decode_section(section: dict[str, str], container: Path, raw: Path,
                   stamp: str) -> list[dict[str, str]]:
    """Decode the twelve sealed interior ticks of one pinned container."""
    facts = probe(container)
    pins = {"container_bytes": str(container.stat().st_size),
            "container_sha256": sha256_file(container), **facts}
    rows = []
    for index in interior_indices(int(facts["frame_count"])):
        key = "%s:%06d" % (section["section_id"], index)
        row = {"tick_key": key, "sheet_id": "", "section_id": section["section_id"],
               "video_id": section["video_id"], "competition": section["competition"],
               "sport": section.get("sport", ""), "offset_s": section["offset_s"],
               "source_duration": section["source_duration"],
               "window_start_s": section["window_start_s"],
               "window_end_s": section["window_end_s"], **pins, "frame_index": str(index),
               "pinned_utc": stamp}
        target = raw / (key.replace(":", "_") + ".jpg")
        try:
            size = render_native(container, index, target)
        except ValueError as error:
            rows.append({**row, "sheet_bytes": "", "sheet_sha256": "",
                         "evidence_status": "ABSENT", "absent_reason": str(error)[:120]})
            continue
        rows.append({**row, "sheet_bytes": str(size),
                     "sheet_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                     "evidence_status": "READABLE", "absent_reason": ""})
    return rows


def assign_blind(rows: list[dict[str, str]], raw: Path, sheets: Path) -> list[dict[str, str]]:
    """Shuffle with the sealed seed so consecutive sheet ids are not one section."""
    ordered = sorted(rows, key=lambda row: row["tick_key"])
    order = list(range(len(ordered)))
    random.Random(SEED).shuffle(order)
    sheets.mkdir(parents=True, exist_ok=True)
    out = []
    for sheet_index, position in enumerate(order):
        row = ordered[position]
        if row["evidence_status"] != "READABLE":
            out.append(row)
            continue
        sheet_id = "g385_%04d" % sheet_index
        source = raw / (row["tick_key"].replace(":", "_") + ".jpg")
        source.replace(sheets / (sheet_id + ".jpg"))
        out.append({**row, "sheet_id": sheet_id})
    return sorted(out, key=lambda row: row["tick_key"])


def main() -> None:
    parser = argparse.ArgumentParser(description="G385 pin, copy, decode, render in one pass")
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--dev-videos", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--frames", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    dev_videos = {line.strip() for line in args.dev_videos.read_text().splitlines() if line.strip()}
    sections = plan_windows(even_sections(eligible_pool(read_csv(args.census), dev_videos)))
    raw = args.scratch / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    for number, section in enumerate(sections, 1):
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        container, reason = fetch(section, args.scratch, args.timeout)
        if container is None:
            rows.extend(absent_rows(section, reason or "fetch_failed", stamp))
            print("SECTION %02d %s ABSENT %s" % (number, section["section_id"], reason))
            continue
        try:
            rows.extend(decode_section(section, container, raw, stamp))
            print("SECTION %02d %s OK" % (number, section["section_id"]))
        except (ValueError, subprocess.SubprocessError) as error:
            rows.extend(absent_rows(section, type(error).__name__, stamp))
            print("SECTION %02d %s ABSENT %s" % (number, section["section_id"],
                                                 type(error).__name__))
        finally:
            container.unlink(missing_ok=True)
    write_csv(args.frames, assign_blind(rows, raw, args.sheets))
    readable = sum(row["evidence_status"] == "READABLE" for row in rows)
    print("PLANNED %d READABLE %d SECTIONS %d VIDEOS %d" % (
        len(rows), readable, len(sections), len({row["video_id"] for row in sections})))


if __name__ == "__main__":
    main()
