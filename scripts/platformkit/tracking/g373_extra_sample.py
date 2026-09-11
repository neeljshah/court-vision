"""G373 phase 1: the sealed extra development-frame sample.

Development sections only -- no held-out game or section contributes a frame, and
the sealed split is game-disjoint by construction (g363_ball_coverage.split_for).
Each section is re-fetched with the G361 pinned recipe at the rung its sealed
sources.csv row records, decoded ONCE end to end, and the evenly spaced indices
of the sealed sampler are hashed and cached.  A selected frame that reproduces a
sealed reference key or one of its causal neighbours is dropped, never kept, and
selections inside one section stay at least MIN_INDEX_GAP decoded indices apart.
The sample is fixed here, before any rating and before any detector score.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
             "NUMEXPR_NUM_THREADS", "OPENCV_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
import subprocess
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import (SEED_TAG, digest, file_sha256,
                                                             frame_key, read_csv, write_csv)

FRAMES_PER_SECTION = 27
MIN_INDEX_GAP = 30
RUNG_FOR_STATUS = {"OK": "270", "OK-RUNG312": "312"}
SECTION_SECONDS = 130
EXTRA_FIELDS = ("frame_key", "split", "competition", "game", "section", "offset_s",
                "section_path", "section_bytes", "section_sha256", "format_id",
                "frame_index", "width", "height", "sheet_scale")


def plan_sections(frames_csv: Path, sources_csv: Path) -> list[dict]:
    """One fetch plan row per DEVELOPMENT section, at its own sealed rung."""
    frames = read_csv(frames_csv)
    development = [row for row in frames if row["split"] == "development"]
    heldout_games = {row["game"] for row in frames if row["split"] == "heldout"}
    status: dict[str, str] = {}
    for row in read_csv(sources_csv):
        if row["status"] in RUNG_FOR_STATUS:
            status[row["section"]] = row["status"]
    plan: dict[str, dict] = {}
    for row in development:
        section = row["section"]
        if row["game"] in heldout_games:
            raise SystemExit("held-out game in the development plan: " + row["game"])
        if section in plan or section not in status:
            continue
        plan[section] = {"section": section, "game": row["game"],
                         "offset_s": row["offset_s"], "competition": row["competition"],
                         "format_id": RUNG_FOR_STATUS[status[section]]}
    return [plan[key] for key in sorted(plan)]


def even_indices(n_frames: int, count: int, section: str) -> list[int]:
    """Evenly spaced indices over the WHOLE decoded sequence; never a head slice."""
    spacing = n_frames // count
    if spacing < MIN_INDEX_GAP:
        raise ValueError(f"{section}: spacing {spacing} below {MIN_INDEX_GAP}")
    start = max(int(digest(SEED_TAG, "G373-extra", section)[:8], 16) % spacing, 3)
    return [start + step * spacing for step in range(count)]


def fetch(row: dict, out_dir: Path) -> Path | None:
    """Pinned single-section fetch; returns None when the rung is unavailable."""
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / (row["section"] + ".mp4")
    if target.exists() and target.stat().st_size > 0:
        return target
    offset = int(row["offset_s"])
    command = ["yt-dlp", "-f", row["format_id"], "--no-playlist", "--no-warnings",
               "--download-sections", f"*{offset}-{offset + SECTION_SECONDS}",
               "-o", str(target), f"https://www.youtube.com/watch?v={row['game']}"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0 or not target.exists():
        print("ABSENT-SECTION " + row["section"] + " " + result.stderr.strip()[-160:], flush=True)
        return None
    return target


def decode_select(cv2, path: Path, row: dict, sealed: set[str], cache: Path) -> list[dict]:
    """Decode the section once and keep only the sealed evenly spaced indices."""
    capture = cv2.VideoCapture(str(path))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    if total < FRAMES_PER_SECTION * MIN_INDEX_GAP:
        capture.release()
        print(f"ABSENT-SHORT {row['section']} frames={total}", flush=True)
        return []
    wanted = set(even_indices(total, FRAMES_PER_SECTION, row["section"]))
    section_sha, section_bytes = file_sha256(path), path.stat().st_size
    cache.mkdir(parents=True, exist_ok=True)
    kept: list[dict] = []
    index = -1
    last_kept = -MIN_INDEX_GAP
    while True:
        ok, image = capture.read()
        if not ok:
            break
        index += 1
        if index not in wanted or index - last_kept < MIN_INDEX_GAP:
            continue
        key = frame_key(image)
        if key in sealed:
            print(f"DEDUP-SEALED {row['section']} index={index}", flush=True)
            continue
        cv2.imwrite(str(cache / (key + ".png")), image)
        last_kept = index
        kept.append({"frame_key": key, "split": "development",
                     "competition": row["competition"], "game": row["game"],
                     "section": row["section"], "offset_s": row["offset_s"],
                     "section_path": str(path), "section_bytes": section_bytes,
                     "section_sha256": section_sha, "format_id": row["format_id"],
                     "frame_index": index, "width": image.shape[1],
                     "height": image.shape[0], "sheet_scale": 1.0})
    capture.release()
    print(f"SECTION {row['section']} decoded={index + 1} kept={len(kept)}", flush=True)
    return kept


def sealed_keys(frames_csv: Path) -> set[str]:
    """Every sealed reference key and both causal neighbours of every split."""
    keys: set[str] = set()
    for row in read_csv(frames_csv):
        keys.update({row["frame_key"], row["m1_sha256"], row["m2_sha256"]})
    return keys


def run(args) -> int:
    """Resumable: a section whose rows are already in the output CSV is not
    re-fetched, so an interrupted run continues instead of re-drawing the sample.
    Rows are appended per section, so provenance is never held only in memory."""
    import csv

    import cv2

    cv2.setNumThreads(1)
    frames_csv = Path(args.frames)
    plan = plan_sections(frames_csv, Path(args.sources))
    sealed = sealed_keys(frames_csv)
    out = Path(args.out)
    rows = read_csv(out) if out.exists() else []
    done = {row["section"] for row in rows}
    print(f"PLAN sections={len(plan)} games={len({row['game'] for row in plan})} "
          f"target={len(plan) * FRAMES_PER_SECTION} resume_sections={len(done)} "
          f"resume_rows={len(rows)}", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    handle = out.open("a", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=list(EXTRA_FIELDS), lineterminator="\n")
    if not rows:
        writer.writeheader()
    for row in plan:
        if row["section"] in done:
            continue
        path = fetch(row, Path(args.sections))
        if path is None:
            continue
        fresh = decode_select(cv2, path, row, sealed, Path(args.cache))
        writer.writerows(fresh)
        handle.flush()
        os.fsync(handle.fileno())
        rows.extend(fresh)
        if args.delete_sections:
            path.unlink(missing_ok=True)
    handle.close()
    rows.sort(key=lambda item: (item["section"], int(item["frame_index"])))
    write_csv(out, EXTRA_FIELDS, rows)
    print(f"EXTRA-SAMPLE frames={len(rows)} unique={len({row['frame_key'] for row in rows})} "
          f"sections={len({row['section'] for row in rows})} "
          f"games={len({row['game'] for row in rows})}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g373_extra_sample")
    for flag in ("--frames", "--sources", "--sections", "--cache", "--out"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--delete-sections", action="store_true")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(_parser().parse_args()))
