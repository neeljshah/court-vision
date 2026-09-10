"""G363 ball-detection coverage: eligibility census, sealed reference sampling,
blind rater sheets, and dispatch to the arm runner and the scorer.

Preregistration: docs/evidence/tracking/g363_ball_coverage_2026-09-09/g363_prereg_2026-09-09.md
Nothing here writes data/, src/, kernel/, api/ or intel/.  The deployed detector
is imported (never edited) by g363_arms.py.  No network call is made anywhere in
this module: the finisher fetches sections with /workspace/YTDLP_RECIPE.txt.
"""
from __future__ import annotations

import os

for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_var] = "1"

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable, Sequence

SEED_TAG = "G363-2026-09-09"
SECTION_ID = re.compile(r"^(?P<game>[A-Za-z0-9_-]{11})_s(?P<offset>\d+)$")
SPLITS = ("development", "heldout")
DEV_MODULUS, DEV_REMAINDER = 10, 4
SECTIONS = {"development": 30, "heldout": 40}
FRAMES_PER_SECTION = {"development": 12, "heldout": 16}
MAX_SECTIONS_PER_GAME = 3
MIN_SPACING = 4
NEIGHBOUR_OFFSETS = (1, 2)
SHEET_PANEL_WIDTH = 960

CENSUS_FIELDS = ("section", "game", "offset_s", "competition", "status", "rows",
                 "decoded_frames", "source_resolution", "source_fps", "has_dir",
                 "eligible", "split", "select_key")
FRAME_FIELDS = ("frame_key", "split", "competition", "game", "section", "offset_s",
                "section_path", "section_bytes", "section_sha256", "frame_index",
                "width", "height", "sheet_scale", "m1_sha256", "m2_sha256")


def digest(*parts: object) -> str:
    """Return the sealed seed digest for a tuple of identity parts."""
    payload = "|".join([SEED_TAG] + [str(part) for part in parts])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def split_for(game: str) -> str:
    """Assign one game to a split; game-disjointness follows from this rule alone."""
    return "development" if int(digest(game)[:8], 16) % DEV_MODULUS < DEV_REMAINDER else "heldout"


def frame_key(frame) -> str:
    """Identity of a decoded frame: its shape and raw bytes, never a frame number."""
    shape = "x".join(str(dim) for dim in frame.shape)
    return hashlib.sha256(b"G363|" + shape.encode("ascii") + b"|" + frame.tobytes()).hexdigest()


def file_sha256(path: Path) -> str:
    """Stream a file into SHA-256 so a pinned section is identified by content."""
    digested = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digested.update(chunk)
    return digested.hexdigest()


def even_indices(n_frames: int, count: int, section: str) -> list[int]:
    """Evenly spaced frame indices with a seeded start; never a head slice."""
    spacing = n_frames // count
    if spacing < MIN_SPACING:
        raise ValueError(f"{section}: spacing {spacing} below the sealed minimum {MIN_SPACING}")
    start = max(int(digest(section)[:8], 16) % spacing, max(NEIGHBOUR_OFFSETS))
    return [start + step * spacing for step in range(count)]


def load_ledger(path: Path) -> dict[str, dict]:
    """Return the last ledger record per game id; the ledger is only ever read."""
    latest: dict[str, dict] = {}
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("game_id"):
                latest[record["game_id"]] = record
    return latest


def census_rows(ledger: dict[str, dict], tracking_root: Path) -> list[dict]:
    """Eligibility census: a section is eligible only when it is source-pinnable."""
    rows: list[dict] = []
    for section, record in sorted(ledger.items()):
        matched = SECTION_ID.match(section)
        has_dir = (Path(tracking_root) / section).is_dir()
        eligible = bool(matched and has_dir and record.get("status") == "tracked")
        game = matched.group("game") if matched else ""
        rows.append({
            "section": section,
            "game": game,
            "offset_s": matched.group("offset") if matched else "",
            "competition": record.get("sport") or "",
            "status": record.get("status") or "",
            "rows": record.get("rows") or 0,
            "decoded_frames": record.get("decoded_frames") or 0,
            "source_resolution": record.get("source_resolution") or "",
            "source_fps": record.get("source_fps") or "",
            "has_dir": int(has_dir),
            "eligible": int(eligible),
            "split": split_for(game) if eligible else "",
            "select_key": digest(section) if eligible else "",
        })
    return rows


def select_sections(rows: Iterable[dict], split: str, count: int) -> list[dict]:
    """Round-robin over games so section diversity implies game diversity."""
    pool = [row for row in rows if str(row["eligible"]) == "1" and row["split"] == split]
    by_game: dict[str, list[dict]] = {}
    for row in sorted(pool, key=lambda row: row["select_key"]):
        by_game.setdefault(row["game"], []).append(row)
    chosen: list[dict] = []
    for slot in range(MAX_SECTIONS_PER_GAME):
        for game in sorted(by_game, key=digest):
            if len(chosen) >= count:
                return chosen
            if slot < len(by_game[game]):
                chosen.append(by_game[game][slot])
    return chosen


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict]) -> int:
    """Write an LF CSV and return the row count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            written += 1
    return written


def read_csv(path: Path) -> list[dict]:
    """Read one table and materialize additive micro-unit numeric aliases."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        encoded_key = row.get("frame_key", "")
        if re.fullmatch(r"[a-p]{64}", encoded_key):
            row["frame_key"] = encoded_key.translate(str.maketrans("abcdefghijklmnop", "0123456789abcdef"))
        for field, value in list(row.items()):
            if not field.endswith("_e6") or not value:
                continue
            base = field[:-3]
            if base in row:
                continue
            signed = int(value)
            prefix = "-" if signed < 0 else ""
            digits = str(abs(signed)).zfill(7)
            row[base] = prefix + digits[:-6] + "." + digits[-6:]
    return rows


def _cache_frame(cv2, cache: Path, frame) -> str:
    key = frame_key(frame)
    target = Path(cache) / f"{key}.png"
    if not target.exists():
        cv2.imwrite(str(target), frame)
    return key


def sample_split(cv2, rows: list[dict], split: str, sections_dir: Path, cache: Path) -> list[dict]:
    """Decode the sealed reference frames of one split exactly once into the cache."""
    out: list[dict] = []
    for section in select_sections(rows, split, SECTIONS[split]):
        path = Path(sections_dir) / (section["section"] + ".mp4")
        if not path.exists():
            print("ABSENT-SECTION " + section["section"] + " " + str(path))
            continue
        capture = cv2.VideoCapture(str(path))
        declared = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or int(section["decoded_frames"] or 0)
        wanted = set(even_indices(declared, FRAMES_PER_SECTION[split], section["section"]))
        sha, size, index = file_sha256(path), path.stat().st_size, 0
        buffer: list = []
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            buffer.append(frame)
            buffer[:] = buffer[-3:]
            if index in wanted and len(buffer) == 3:
                out.append({
                    "frame_key": _cache_frame(cv2, cache, buffer[-1]), "split": split,
                    "competition": section["competition"], "game": section["game"],
                    "section": section["section"], "offset_s": section["offset_s"],
                    "section_path": str(path), "section_bytes": size, "section_sha256": sha,
                    "frame_index": index, "width": frame.shape[1], "height": frame.shape[0],
                    "sheet_scale": round(SHEET_PANEL_WIDTH / frame.shape[1], 6),
                    "m1_sha256": _cache_frame(cv2, cache, buffer[-2]),
                    "m2_sha256": _cache_frame(cv2, cache, buffer[-3]),
                })
            index += 1
        capture.release()
        print(f"SECTION {section['section']} declared={declared} decoded={index} wanted={len(wanted)}")
    return out


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="g363_ball_coverage")
    sub = parser.add_subparsers(dest="cmd", required=True)
    census = sub.add_parser("census")
    census.add_argument("--ledger", required=True)
    census.add_argument("--tracking-root", required=True)
    census.add_argument("--out", required=True)
    sample = sub.add_parser("sample")
    sample.add_argument("--census", required=True)
    sample.add_argument("--sections-dir", required=True)
    sample.add_argument("--cache", required=True)
    sample.add_argument("--out", required=True)
    sheet = sub.add_parser("sheets")
    sheet.add_argument("--frames", required=True)
    sheet.add_argument("--cache", required=True)
    sheet.add_argument("--out", required=True)
    arms = sub.add_parser("arms")
    arms.add_argument("--arm", required=True)
    arms.add_argument("--frames", required=True)
    arms.add_argument("--cache", required=True)
    arms.add_argument("--split", required=True, choices=SPLITS)
    arms.add_argument("--deploy-root", required=True)
    arms.add_argument("--out", required=True)
    arms.add_argument("--inherit", default="")
    score = sub.add_parser("score")
    score.add_argument("--frames", required=True)
    score.add_argument("--ratings", required=True)
    score.add_argument("--predictions", required=True)
    score.add_argument("--frame-scores", required=True)
    score.add_argument("--arms-out", required=True)
    score.add_argument("--out", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.cmd == "census":
        rows = census_rows(load_ledger(Path(args.ledger)), Path(args.tracking_root))
        write_csv(Path(args.out), CENSUS_FIELDS, rows)
        for split in SPLITS:
            chosen = select_sections(rows, split, SECTIONS[split])
            games = {row["game"] for row in chosen}
            print(f"CENSUS {split} sections={len(chosen)} games={len(games)} "
                  f"competitions={len({row['competition'] for row in chosen})} "
                  f"frames={len(chosen) * FRAMES_PER_SECTION[split]}")
        print(f"CENSUS rows={len(rows)} eligible={sum(int(row['eligible']) for row in rows)}")
    elif args.cmd == "sample":
        import cv2

        cv2.setNumThreads(1)
        Path(args.cache).mkdir(parents=True, exist_ok=True)
        rows, frames = read_csv(Path(args.census)), []
        for split in SPLITS:
            frames.extend(sample_split(cv2, rows, split, Path(args.sections_dir), Path(args.cache)))
        print(f"SAMPLE frames={write_csv(Path(args.out), FRAME_FIELDS, frames)}")
    elif args.cmd == "sheets":
        from scripts.platformkit.tracking import g363_sheets

        manifest = g363_sheets.sheets(read_csv(Path(args.frames)), Path(args.cache),
                                      Path(args.out))
        write_csv(Path(args.out) / "sheets_manifest.csv", g363_sheets.SHEET_FIELDS, manifest)
        print(f"SHEETS n={len(manifest)} "
              f"max_bytes={max([row['sheet_bytes'] for row in manifest] or [0])}")
    elif args.cmd == "arms":
        from scripts.platformkit.tracking import g363_arms

        g363_arms.run(args)
    else:
        from scripts.platformkit.tracking import g363_score

        g363_score.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
