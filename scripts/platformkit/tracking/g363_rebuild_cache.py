"""G363 phase 2: rebuild the lost decode cache and verify frame identity (G361).

The pod that held the phase-1 PNG cache died.  The sealed reference frames.csv
survives, and every reference frame is named by the SHA-256 of its own decoded
bytes, so identity is recoverable without trusting any frame number: re-fetch the
section, decode it sequentially, hash every frame, and keep only the frames whose
hash is one the sealed table already names.  A sealed frame whose hash never
reproduces is an identity failure and is reported UNKNOWN-ALIGNMENT and excluded
from the scored set; no nearby frame is ever substituted for it.

Writes only the cache directory and the two report tables.  Reads frames.csv.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
import sys
from pathlib import Path

from scripts.platformkit.tracking.g363_ball_coverage import (FRAME_FIELDS, frame_key,
                                                             read_csv, write_csv)

IDENTITY_FIELDS = ("frame_key", "split", "section", "frame_index", "role", "status")
FOUND, MISSING = "REPRODUCED", "UNKNOWN-ALIGNMENT"
ROLES = (("frame_key", "reference"), ("m1_sha256", "neighbour_t1"), ("m2_sha256", "neighbour_t2"))


def wanted_by_section(rows: list[dict]) -> dict[str, set[str]]:
    """Every sealed hash a given section is expected to reproduce."""
    wanted: dict[str, set[str]] = {}
    for row in rows:
        bucket = wanted.setdefault(row["section"], set())
        for field, _role in ROLES:
            bucket.add(row[field])
    return wanted


def build_section(cv2, path: Path, wanted: set[str], cache: Path) -> tuple[int, int]:
    """Decode one section once and cache every frame whose hash is sealed."""
    have = {key for key in wanted if (cache / (key + ".png")).exists()}
    if have == wanted:
        return len(have), 0
    capture = cv2.VideoCapture(str(path))
    decoded = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        decoded += 1
        key = frame_key(frame)
        if key in wanted and key not in have:
            cv2.imwrite(str(cache / (key + ".png")), frame)
            have.add(key)
    capture.release()
    return len(have), decoded


def verify(cv2, rows: list[dict], cache: Path) -> list[dict]:
    """Re-hash every cached PNG: the arms read the PNG, so the PNG must reproduce."""
    status: dict[str, str] = {}
    report: list[dict] = []
    for row in rows:
        for field, role in ROLES:
            key = row[field]
            if key not in status:
                image = cv2.imread(str(cache / (key + ".png")))
                status[key] = FOUND if image is not None and frame_key(image) == key else MISSING
            report.append({"frame_key": key, "split": row["split"], "section": row["section"],
                           "frame_index": row["frame_index"], "role": role,
                           "status": status[key]})
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="g363_rebuild_cache")
    parser.add_argument("cmd", choices=("build", "verify"))
    parser.add_argument("--frames", required=True)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--sections-dir", default="")
    parser.add_argument("--section", default="")
    parser.add_argument("--identity-out", default="")
    parser.add_argument("--scored-out", default="")
    args = parser.parse_args(argv)

    import cv2

    cv2.setNumThreads(1)
    rows = read_csv(Path(args.frames))
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)

    if args.cmd == "build":
        wanted = wanted_by_section(rows)
        for section in ([args.section] if args.section else sorted(wanted)):
            path = Path(args.sections_dir) / (section + ".mp4")
            if not path.exists():
                print(f"ABSENT-SECTION {section} {path}")
                continue
            cached, decoded = build_section(cv2, path, wanted[section], cache)
            print(f"BUILD {section} cached={cached}/{len(wanted[section])} decoded={decoded}")
        return 0

    report = verify(cv2, rows, cache)
    bad = {row["frame_key"] for row in report if row["status"] == MISSING}
    refs = [row for row in rows if row["frame_key"] not in bad]
    failed_refs = len(rows) - len(refs)
    neighbours_lost = sum(1 for row in refs if row["m1_sha256"] in bad or row["m2_sha256"] in bad)
    if args.identity_out:
        write_csv(Path(args.identity_out), IDENTITY_FIELDS, report)
    if args.scored_out:
        write_csv(Path(args.scored_out), FRAME_FIELDS, refs)
    share = failed_refs / len(rows) if rows else 0.0
    print(f"IDENTITY sealed={len(rows)} reproduced={len(refs)} unknown_alignment={failed_refs} "
          f"share={share:.6f} neighbour_lost_frames={neighbours_lost}")
    for split in sorted({row["split"] for row in rows}):
        total = sum(1 for row in rows if row["split"] == split)
        kept = sum(1 for row in refs if row["split"] == split)
        print(f"IDENTITY split={split} sealed={total} reproduced={kept} unknown_alignment={total - kept}")
    print("IDENTITY GATE " + ("STOP-LIMIT" if share > 0.10 else "PROCEED"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
