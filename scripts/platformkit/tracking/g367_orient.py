"""Pinned, even orientation sampling and blind-sheet construction for G367."""
from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np

SECTIONS_TARGET, MAX_PER_GAME, FRAMES_PER_SECTION, SHEET_WIDTH = 20, 2, 3, 960
PLAN_HEADER = ("section,game,video_id,offset_s,bytes,sha256,n_frames,frame_index,"
               "prev2_index,prev1_index,frame_key")
MANIFEST_HEADER = "frame_key,sheet,cache,prev1_cache,section,frame_index,strip_complete"


def _digest(text: str) -> bytes:
    return hashlib.sha256(("G367-2026-09-09|" + text).encode("ascii")).digest()


def _value(row: dict, *names: str) -> str:
    for name in names:
        if row.get(name, ""):
            return row[name]
    return ""


def _source_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    out = []
    for row in rows:
        video = _value(row, "video_id", "youtube_id", "id")
        game, offset = _value(row, "game", "game_id"), _value(row, "offset_s", "offset")
        section = _value(row, "section") or ("%s_s%s" % (video, offset))
        if not (video and game and offset and _value(row, "bytes") and _value(row, "sha256")):
            continue
        out.append({"section": section, "game": game, "video_id": video, "offset_s": offset,
                    "bytes": _value(row, "bytes"), "sha256": _value(row, "sha256")})
    return out


def select_sections(rows: list[dict]) -> list[dict]:
    """Round-robin the hash-ordered games with the sealed per-game cap."""
    buckets = {}
    for row in rows:
        buckets.setdefault(row["game"], []).append(row)
    games = sorted(buckets, key=lambda item: _digest(item))
    for game in games:
        buckets[game].sort(key=lambda item: _digest(item["section"]))
    selected, used, index = [], {game: 0 for game in games}, 0
    while len(selected) < SECTIONS_TARGET:
        progressed = False
        for game in games:
            if len(selected) >= SECTIONS_TARGET:
                break
            if used[game] < MAX_PER_GAME and index < len(buckets[game]):
                selected.append(buckets[game][index])
                used[game] += 1
                progressed = True
        if not progressed:
            break
        index += 1
    return selected


def sample(sources: Path, out: Path) -> int:
    """Write only the sealed section plan; no media is opened in this command."""
    selected = select_sections(_source_rows(sources))
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_HEADER.split(","))
        writer.writeheader()
        for row in selected:
            writer.writerow({**row, "n_frames": "", "frame_index": "", "prev2_index": "",
                             "prev1_index": "", "frame_key": ""})
    print("ORIENTATION sections=%d games=%d" % (len(selected), len({r["game"] for r in selected})))
    return 0 if len(selected) == SECTIONS_TARGET else 2


def _frame_key(frame: np.ndarray) -> str:
    return hashlib.sha256(b"G367|" + str(frame.shape).encode("ascii") + b"|" + frame.tobytes()).hexdigest()


def _indices(section: str, n_frames: int) -> list[int]:
    spacing = n_frames // FRAMES_PER_SECTION
    if spacing < 4:
        raise ValueError("section %s has insufficient frames" % section)
    start = max(int.from_bytes(_digest(section)[:8], "big") % spacing, 2)
    return [start + number * spacing for number in range(FRAMES_PER_SECTION)]


def _read_frames(path: Path, wanted: set[int]) -> dict[int, np.ndarray]:
    cap, result, index = cv2.VideoCapture(str(path)), {}, 0
    if not cap.isOpened():
        raise ValueError("cannot open %s" % path)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if index in wanted:
            result[index] = frame
        index += 1
    cap.release()
    return result


def _sheet(target: np.ndarray, previous: list[np.ndarray]) -> np.ndarray:
    top_h = int(round(target.shape[0] * SHEET_WIDTH / target.shape[1]))
    top = cv2.resize(target, (SHEET_WIDTH, top_h), interpolation=cv2.INTER_AREA)
    tile_w, tile_h = SHEET_WIDTH // 3, max(1, top_h // 4)
    strip = [cv2.resize(frame, (tile_w, tile_h), interpolation=cv2.INTER_AREA) for frame in previous]
    return np.vstack((top, np.hstack(strip)))


def _write_jpeg(path: Path, image: np.ndarray) -> bool:
    for quality in (80, 65, 50, 35):
        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if ok and encoded.nbytes <= 200_000:
            path.write_bytes(encoded.tobytes())
            return True
    return False


def sheets(orientation: Path, sections_dir: Path, cache: Path, out: Path) -> int:
    """Decode sequentially, update the frame plan, and build sheets without annotation text."""
    with orientation.open(newline="", encoding="ascii") as handle:
        plans = list(csv.DictReader(handle))
    cache.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    expanded, manifest = [], []
    for plan in plans:
        matches = list(sections_dir.glob(plan["section"] + ".*"))
        if len(matches) != 1:
            raise ValueError("expected one section container for %s" % plan["section"])
        cap = cv2.VideoCapture(str(matches[0]))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        wanted = _indices(plan["section"], count)
        frames = _read_frames(matches[0], {i for point in wanted for i in (point - 2, point - 1, point)})
        for index in wanted:
            prior = [frames.get(index - 2), frames.get(index - 1), frames.get(index)]
            if any(item is None for item in prior):
                raise ValueError("incomplete sequential strip for %s" % plan["section"])
            key, target = _frame_key(frames[index]), frames[index]
            cache_path, prev1_path = cache / (key + ".png"), cache / (key + "_prev1.png")
            sheet_path = out / (key[:12] + ".jpg")
            if (not cv2.imwrite(str(cache_path), target) or not cv2.imwrite(str(prev1_path), prior[1])
                    or not _write_jpeg(sheet_path, _sheet(target, prior))):
                raise ValueError("cannot write blind sheet for %s" % key)
            expanded.append({**plan, "n_frames": count, "frame_index": index, "prev2_index": index - 2,
                             "prev1_index": index - 1, "frame_key": key})
            manifest.append({"frame_key": key, "sheet": sheet_path.name, "cache": cache_path.name,
                             "prev1_cache": prev1_path.name, "section": plan["section"],
                             "frame_index": index, "strip_complete": 1})
    with orientation.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=PLAN_HEADER.split(","))
        writer.writeheader(); writer.writerows(expanded)
    with (out / "manifest.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_HEADER.split(","))
        writer.writeheader(); writer.writerows(manifest)
    print("SHEETS n=%d" % len(manifest))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    one = sub.add_parser("sample"); one.add_argument("--sources", required=True); one.add_argument("--out", required=True)
    two = sub.add_parser("sheets"); two.add_argument("--orientation", required=True); two.add_argument("--sections-dir", required=True)
    two.add_argument("--cache", required=True); two.add_argument("--out", required=True)
    args = parser.parse_args(argv[1:])
    return sample(Path(args.sources), Path(args.out)) if args.action == "sample" else sheets(
        Path(args.orientation), Path(args.sections_dir), Path(args.cache), Path(args.out))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
