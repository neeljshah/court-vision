"""G375 blind sheet builder: pin one native midpoint frame per sampled section.

Sealed by `docs/evidence/tracking/g375_corpus_sport_purity_2026-09-10/
g375_prereg_2026-09-10.md` (SEAL sha256
2f178a9d533cd9a36f90477ef5b81d499fbe282708433fa29a55344a830242b2). Each container is
deleted as soon as its frame is extracted; nothing is written under /workspace/data.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g375_census import read_csv, write_csv

FORMAT = "270/312/137/best[height>=720]/best"
QUALITIES = (85, 75, 65, 55, 45)
SHEET_WIDTH = 1280
SHEET_MAX_BYTES = 200_000
FIELDS = ("sheet_id", "game_id", "prefix", "video_id", "target_tick_s",
          "window_start_s", "window_end_s", "container_bytes", "container_sha256",
          "width", "height", "frame_count", "avg_frame_rate", "codec_name",
          "frame_index", "frame_pts_s", "sheet_bytes", "sheet_sha256", "fetched_utc")
ABSENT_FIELDS = ("sheet_id", "game_id", "prefix", "reason")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fetch(row: dict[str, str], scratch: Path, timeout: int) -> tuple[Path | None, str]:
    """Fetch the sealed five-second window around the section midpoint, with its reason."""
    target = scratch / (row["sheet_id"] + ".mp4")
    target.unlink(missing_ok=True)
    command = ["nice", "-n", "10", "yt-dlp", "-f", FORMAT, "--no-playlist", "--no-warnings",
               "--download-sections", "*%s-%s" % (row["window_start_s"], row["window_end_s"]),
               "--merge-output-format", "mp4", "-o", str(target), "--",
               "https://www.youtube.com/watch?v=" + row["video_id"]]
    try:
        subprocess.run(command, check=True, timeout=timeout, capture_output=True)
    except subprocess.CalledProcessError as error:
        tail = (error.stderr or b"").decode("ascii", "replace").strip().splitlines()
        return None, (tail[-1][:160] if tail else "no_stderr")
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
         "-of", "json", str(path)], check=True, capture_output=True, text=True, timeout=600)
    stream = json.loads(done.stdout)["streams"][0]
    return {"width": str(stream.get("width")), "height": str(stream.get("height")),
            "frame_count": str(stream.get("nb_read_frames")),
            "avg_frame_rate": str(stream.get("avg_frame_rate")),
            "codec_name": str(stream.get("codec_name"))}


def render(container: Path, index: int, sheet: Path) -> tuple[int, float]:
    """Write one overlay-free JPEG at or below the sealed size cap."""
    capture = cv2.VideoCapture(str(container))
    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        pts = float(capture.get(cv2.CAP_PROP_POS_MSEC)) / 1000.0
        ok, frame = capture.read()
    finally:
        capture.release()
    if not ok or frame is None:
        raise ValueError("unreadable sealed frame")
    height, width = frame.shape[:2]
    if width > SHEET_WIDTH:
        scale = SHEET_WIDTH / float(width)
        frame = cv2.resize(frame, (SHEET_WIDTH, max(1, int(round(height * scale)))),
                           interpolation=cv2.INTER_AREA)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    for quality in QUALITIES:
        cv2.imwrite(str(sheet), frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if sheet.stat().st_size <= SHEET_MAX_BYTES:
            return sheet.stat().st_size, pts
    raise ValueError("sheet exceeds the sealed size cap")


def build(row: dict[str, str], scratch: Path, sheets: Path, timeout: int) -> dict[str, str]:
    """Fetch, pin, render and delete the container for one sampled section."""
    sheet = sheets / (row["sheet_id"] + ".jpg")
    container, reason = fetch(row, scratch, timeout)
    if container is None:
        return {"sheet_id": row["sheet_id"], "game_id": row["game_id"],
                "prefix": row["prefix"], "reason": "fetch_failed:" + reason}
    try:
        facts = probe(container)
        digest, size = sha256_file(container), container.stat().st_size
        index = int(facts["frame_count"]) // 2
        sheet_bytes, pts = render(container, index, sheet)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sheet.unlink(missing_ok=True)
        return {"sheet_id": row["sheet_id"], "game_id": row["game_id"],
                "prefix": row["prefix"], "reason": "decode_failed:" + type(error).__name__}
    finally:
        container.unlink(missing_ok=True)
    return {**{key: row[key] for key in FIELDS[:7]}, **facts,
            "container_bytes": str(size), "container_sha256": digest,
            "frame_index": str(index), "frame_pts_s": "%.3f" % pts,
            "sheet_bytes": str(sheet_bytes), "sheet_sha256": sha256_file(sheet),
            "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def main() -> None:
    parser = argparse.ArgumentParser(description="G375 blind sheet builder")
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--sheets", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--absent", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    args.scratch.mkdir(parents=True, exist_ok=True)
    args.sheets.mkdir(parents=True, exist_ok=True)
    rows = read_csv(args.sample)
    pinned: list[dict[str, str]] = []
    absent: list[dict[str, str]] = []
    with futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(build, row, args.scratch, args.sheets, args.timeout): row
                for row in rows}
        for done in futures.as_completed(jobs):
            result = done.result()
            (absent if "reason" in result else pinned).append(result)
            print("%s %s" % ("ABSENT" if "reason" in result else "PINNED",
                             result["sheet_id"]), flush=True)
    write_csv(args.reference, sorted(pinned, key=lambda r: r["sheet_id"]), FIELDS)
    write_csv(args.absent, sorted(absent, key=lambda r: r["sheet_id"]), ABSENT_FIELDS)
    print("pinned=%d absent=%d" % (len(pinned), len(absent)))


if __name__ == "__main__":
    main()
