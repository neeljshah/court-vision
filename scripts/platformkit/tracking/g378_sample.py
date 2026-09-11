"""G378 premise re-measurement and the sealed, pinned, immutable input manifest.

Sealed by ``g378_prereg_2026-09-10.md``: the salt, the development hold-out, the round-robin
section selection, the strictly interior even ticks and the pin fields all come from that file.
Nothing under ``/workspace/data`` is written; containers are opened read only.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import cv2

from scripts.platformkit.tracking.g367_orient import _frame_key

SALT = "G378-2026-09-10|"
SECTIONS_TARGET, MAX_PER_GAME, TICKS = 20, 2, 12
DEVELOPMENT_HOLDOUT, MIN_SECTION_FRAMES, JPEG_QUALITY = 3, 200, 95
CONTAINER_RE = re.compile(r"^(?P<game>.+)_s(?P<offset>\d+)\.mp4$")
FRAME_COLUMNS = ("frame_key,section,game,video_id,offset_s,tick_index,frame_index,n_frames,"
                 "fps,width,height,cache").split(",")
EXCLUSION_COLUMNS = ("section,game,reason").split(",")


def sha(text: str) -> str:
    return hashlib.sha256((SALT + text).encode("ascii")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _containers(corpus: Path) -> dict:
    """Sections grouped by game, both orders fixed by the sealed salt."""
    buckets = collections.defaultdict(list)
    for path in sorted(corpus.iterdir()):
        match = CONTAINER_RE.match(path.name)
        if match:
            buckets[match.group("game")].append(path)
    for game in buckets:
        buckets[game].sort(key=lambda item: sha(item.stem))
    return buckets


def split_games(buckets: dict) -> tuple:
    """Sealed hash order; the last DEVELOPMENT_HOLDOUT games never reach a scored artifact."""
    order = sorted(buckets, key=sha)
    return order[:-DEVELOPMENT_HOLDOUT], order[-DEVELOPMENT_HOLDOUT:]


def _facts(path: Path) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {}
    facts = {"n_frames": int(capture.get(cv2.CAP_PROP_FRAME_COUNT)),
             "fps": round(float(capture.get(cv2.CAP_PROP_FPS)), 4),
             "width": int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
             "height": int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))}
    capture.release()
    facts["duration_s"] = round(facts["n_frames"] / facts["fps"], 3) if facts["fps"] else 0.0
    return facts


def ticks(n_frames: int) -> list:
    """TICKS strictly interior indices, evenly spaced, never a head slice."""
    step = n_frames // (TICKS + 1)
    if step < 1:
        return []
    return [step * (index + 1) for index in range(TICKS)]


def select(corpus: Path, out: Path) -> int:
    """Round robin the sealed game order under the per-game cap; pin every held section."""
    buckets = _containers(corpus)
    pool, development = split_games(buckets)
    held, used, excluded, index = [], {game: 0 for game in pool}, [], 0
    while len(held) < SECTIONS_TARGET and index < max((len(buckets[g]) for g in pool), default=0):
        for game in pool:
            if len(held) >= SECTIONS_TARGET or used[game] >= MAX_PER_GAME or index >= len(buckets[game]):
                continue
            path = buckets[game][index]
            facts = _facts(path)
            if not facts or facts["n_frames"] < MIN_SECTION_FRAMES:
                excluded.append({"section": path.stem, "game": game,
                                 "reason": "unreadable" if not facts else "frames_below_%d" % MIN_SECTION_FRAMES})
                continue
            match = CONTAINER_RE.match(path.name)
            held.append({"section": path.stem, "game": game, "video_id": game,
                         "offset_s": match.group("offset"), "path": str(path),
                         "bytes": path.stat().st_size, "sha256": _file_sha256(path), **facts})
            used[game] += 1
        index += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"row": "G378", "salt": SALT, "sections_target": SECTIONS_TARGET,
               "max_per_game": MAX_PER_GAME, "ticks_per_section": TICKS,
               "min_section_frames": MIN_SECTION_FRAMES, "jpeg_quality": JPEG_QUALITY,
               "development_games": development, "evaluation_pool_games": pool,
               "n_games_held": len({item["game"] for item in held}), "sections": held,
               "exclusions": excluded}
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    with out.with_name("exclusions.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXCLUSION_COLUMNS)
        writer.writeheader()
        writer.writerows(excluded)
    print("SELECT sections=%d games=%d excluded=%d development=%s"
          % (len(held), payload["n_games_held"], len(excluded), ",".join(development)))
    return 0 if len(held) == SECTIONS_TARGET else 2


def decode(manifest: Path, cache: Path, frames_out: Path) -> int:
    """One sequential pass per container; the sealed ticks are cached at native resolution."""
    payload = json.loads(manifest.read_text(encoding="ascii"))
    cache.mkdir(parents=True, exist_ok=True)
    rows = []
    for section in payload["sections"]:
        wanted = ticks(section["n_frames"])
        if len(wanted) != TICKS:
            raise ValueError("section %s cannot supply %d interior ticks" % (section["section"], TICKS))
        capture, index, seen = cv2.VideoCapture(section["path"]), 0, {}
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index in wanted:
                seen[index] = frame
            index += 1
        capture.release()
        for tick, frame_index in enumerate(wanted):
            frame = seen.get(frame_index)
            if frame is None:
                raise ValueError("missing tick %d of %s" % (frame_index, section["section"]))
            key = _frame_key(frame)
            path = cache / (key[:16] + ".jpg")
            if not cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]):
                raise ValueError("cannot cache %s" % key)
            rows.append({"frame_key": key, "section": section["section"], "game": section["game"],
                         "video_id": section["video_id"], "offset_s": section["offset_s"],
                         "tick_index": tick, "frame_index": frame_index,
                         "n_frames": section["n_frames"], "fps": section["fps"],
                         "width": section["width"], "height": section["height"],
                         "cache": path.name})
        print("DECODED %s ticks=%d" % (section["section"], len(wanted)))
    frames_out.parent.mkdir(parents=True, exist_ok=True)
    with frames_out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=FRAME_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print("DECODE frames=%d unique=%d sections=%d games=%d"
          % (len(rows), len({r["frame_key"] for r in rows}),
             len({r["section"] for r in rows}), len({r["game"] for r in rows})))
    return 0


def premise(g371_dir: Path, g367_dir: Path, out: Path) -> int:
    """Spec step 0: the landed counts this row rests on, re-read rather than assumed."""
    with (g371_dir / "sweep.csv").open(newline="", encoding="utf-8") as handle:
        sweep = [row for row in csv.DictReader(handle) if row["geometry"] != "geometry"]
    statuses = collections.Counter(row["geometry_status"] for row in sweep)
    orientation = collections.Counter(row["orientation_status"] for row in sweep)
    with (g371_dir / "selected.csv").open(newline="", encoding="utf-8") as handle:
        selected = [row for row in csv.DictReader(handle) if row["geometry"] != "geometry"]
    clean_orientation = collections.Counter(row["orientation_status"] for row in selected)
    agreement = json.loads((g367_dir / "agreement.json").read_text(encoding="utf-8"))
    reference = agreement["reference_label_counts"]
    accepts = sum(count for status, count in statuses.items() if status.upper().startswith("ACCEPT"))
    non_unknown = sum(count for status, count in orientation.items() if status != "UNKNOWN")
    payload = {"row": "G378", "g371_sweep_status_counts": dict(statuses),
               "g371_sweep_orientation_counts": dict(orientation),
               "g371_selected_orientation_counts": dict(clean_orientation),
               "g371_n_sweep_cells": len(sweep), "g371_n_selected": len(selected),
               "g371_accepts": accepts, "g371_orientation_not_unknown": non_unknown,
               "g367_reference_label_counts": reference,
               "g367_n_labelled_left_right": agreement["n_labelled_left_right"],
               "g367_cohen_kappa": agreement["cohen_kappa"],
               "g367_per_class_rail_meets": agreement["per_class_rail_n_ge_30"]["meets_rail"],
               "premise_true": accepts == 0 and non_unknown == 0}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="ascii")
    print("PREMISE g371_status=%s g371_orientation=%s g371_selected_orientation=%s"
          % (dict(statuses), dict(orientation), dict(clean_orientation)))
    print("PREMISE g367_reference=%s labelled=%d kappa=%s rail_meets=%s"
          % (reference, agreement["n_labelled_left_right"], agreement["cohen_kappa"],
             agreement["per_class_rail_n_ge_30"]["meets_rail"]))
    print("PREMISE_TRUE %s" % payload["premise_true"])
    return 0 if payload["premise_true"] else 3


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("select")
    one.add_argument("--corpus", required=True)
    one.add_argument("--out", required=True)
    two = sub.add_parser("decode")
    for name in ("manifest", "cache", "frames-out"):
        two.add_argument("--" + name, required=True)
    three = sub.add_parser("premise")
    for name in ("g371-dir", "g367-dir", "out"):
        three.add_argument("--" + name, required=True)
    args = parser.parse_args(argv[1:])
    if args.action == "select":
        return select(Path(args.corpus), Path(args.out))
    if args.action == "decode":
        return decode(Path(args.manifest), Path(args.cache), Path(args.frames_out))
    return premise(Path(args.g371_dir), Path(args.g367_dir), Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
