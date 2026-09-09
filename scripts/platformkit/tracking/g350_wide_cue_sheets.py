"""Build G350's sealed shot list and blind contact sheets."""

from __future__ import annotations

import argparse
import csv
import hashlib
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.shot_router import read_kept_frames, route_frames

CLASS_ORDER = ("WIDE", "CLOSEUP", "CROWD", "UNKNOWN")
GROUPS = {"WIDE": "WIDE", "CLOSEUP": "CLOSEUP", "CROWD": "CROWD_UNKNOWN", "UNKNOWN": "CROWD_UNKNOWN"}


def file_sha256(path: Path) -> str:
    """Hash one input at a time without loading its whole byte store."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata(video: Path, digest: str) -> dict[str, object]:
    capture = cv2.VideoCapture(str(video))
    width, height = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    capture.release()
    return {"source_path": str(video.absolute()), "video_sha256": digest,
            "byte_size": video.stat().st_size, "source_width": width, "source_height": height}


def candidate_units(video: Path) -> list[dict[str, object]]:
    """Route one source and return deterministic shot-level candidate metadata."""
    digest = file_sha256(video)
    frames, indices = read_kept_frames(video)
    records, cuts = route_frames(frames, indices)
    starts = [0] + [next(i for i, row in enumerate(records) if row.frame_index == cut) for cut in cuts]
    base = _metadata(video, digest)
    units: list[dict[str, object]] = []
    for shot_id, start in enumerate(starts):
        end = starts[shot_id + 1] if shot_id + 1 < len(starts) else len(records)
        segment = records[start:end]
        counts = Counter(row.view_class for row in segment)
        predicted = min(CLASS_ORDER, key=lambda label: (-counts[label], CLASS_ORDER.index(label)))
        middle = segment[len(segment) // 2]
        key = "%s:%06d" % (digest, shot_id)
        units.append({**base, "unit_id": key, "shot_id": "%06d" % shot_id,
                      "predicted_class": predicted, "selection_group": GROUPS[predicted],
                      "n_frames": len(segment), "representative_frame": middle.frame_index,
                      "strip_first_frame": segment[0].frame_index,
                      "strip_middle_frame": middle.frame_index,
                      "strip_last_frame": segment[-1].frame_index,
                      "selection_key": hashlib.sha256(("G350-2026-09-08|" + key).encode("ascii")).hexdigest()})
    return units


def choose_units(candidates: list[dict[str, object]]) -> list[dict[str, object]]:
    """Apply the sealed class balance and deterministic diversity-preserving selection."""
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in candidates:
        grouped[str(row["selection_group"])].append(row)
    missing = {name: len(grouped[name]) for name in ("WIDE", "CLOSEUP", "CROWD_UNKNOWN") if len(grouped[name]) < 20}
    if missing:
        raise ValueError("sealed selection unavailable: %s" % missing)
    selected = [row for name in ("WIDE", "CLOSEUP", "CROWD_UNKNOWN")
                for row in sorted(grouped[name], key=lambda item: str(item["selection_key"]))[:20]]
    selected_hashes = {str(row["video_sha256"]) for row in selected}
    if len(selected_hashes) < 6:
        raise ValueError("sealed selection lacks six games: %d" % len(selected_hashes))
    return sorted(selected, key=lambda row: (str(row["selection_group"]), str(row["selection_key"])))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["unit_id", "source_path", "video_sha256", "byte_size", "source_width", "source_height",
              "shot_id", "predicted_class", "selection_group", "n_frames", "representative_frame",
              "strip_first_frame", "strip_middle_frame", "strip_last_frame", "selection_key"]
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _sheet(frame_map: dict[int, np.ndarray], row: dict[str, str], target: Path) -> None:
    strip = [frame_map[int(row[name])] for name in ("strip_first_frame", "strip_middle_frame", "strip_last_frame")]
    tiles = [cv2.resize(frame, (240, 135), interpolation=cv2.INTER_AREA) for frame in strip]
    rep = cv2.resize(frame_map[int(row["representative_frame"])], (360, 203), interpolation=cv2.INTER_AREA)
    canvas = np.full((370, 720, 3), 18, dtype=np.uint8)
    for index, tile in enumerate(tiles):
        canvas[24:159, index * 240:(index + 1) * 240] = tile
    canvas[167:370, 180:540] = rep
    cv2.putText(canvas, "SHOT " + row["unit_id"][-13:], (12, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (245, 245, 245), 1, cv2.LINE_AA)
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (70, 55, 40):
        cv2.imwrite(str(target), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        if target.stat().st_size <= 200_000:
            return
    raise ValueError("sheet exceeds 200 KB: %s" % target)


def build_sheets(shots_csv: Path, sheet_dir: Path) -> None:
    """Create blind sheets, reopening and decoding one source video at a time."""
    with shots_csv.open(newline="", encoding="ascii") as handle:
        rows = list(csv.DictReader(handle))
    by_video: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_video[row["source_path"]].append(row)
    for source, selected in by_video.items():
        frames, indices = read_kept_frames(Path(source))
        frame_map = dict(zip(indices, frames))
        for row in selected:
            _sheet(frame_map, row, sheet_dir / (row["unit_id"].replace(":", "_") + ".jpg"))


def build_premise_contacts(router_shots: Path, videos: list[Path], sheet_dir: Path) -> None:
    """Render one first-frame-of-shot contact sheet per fresh premise section."""
    with router_shots.open(newline="", encoding="ascii") as handle:
        by_section: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in csv.DictReader(handle):
            by_section[row["section"]].append(row)
    sources = {video.name: video for video in videos}
    for section, rows in sorted(by_section.items()):
        if section not in sources:
            raise ValueError("premise section lacks source: %s" % section)
        frames, indices = read_kept_frames(sources[section])
        frame_map = dict(zip(indices, frames))
        tiles = [frame_map[int(row["start_frame"])] for row in sorted(rows, key=lambda item: int(item["shot_id"]))]
        contact = cv2.hconcat(tiles)
        target = sheet_dir / (Path(section).stem + "_contact.jpg")
        target.parent.mkdir(parents=True, exist_ok=True)
        for quality in (70, 55, 40):
            cv2.imwrite(str(target), contact, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            if target.stat().st_size <= 200_000:
                break
        if target.stat().st_size > 200_000:
            raise ValueError("premise contact exceeds 200 KB: %s" % target)


def main() -> None:
    parser = argparse.ArgumentParser(description="G350 sealed selection and blind sheets")
    parser.add_argument("--video", action="append", type=Path, default=[])
    parser.add_argument("--video-list", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--build-sheets", action="store_true")
    parser.add_argument("--premise-shots", type=Path)
    parser.add_argument("--premise-sheets", type=Path)
    args = parser.parse_args()
    listed = [] if args.video_list is None else [Path(line.strip()) for line in args.video_list.read_text(encoding="utf-8").splitlines() if line.strip()]
    videos = args.video + listed
    if not videos:
        parser.error("at least one --video or --video-list is required")
    if (args.premise_shots is None) != (args.premise_sheets is None):
        parser.error("--premise-shots and --premise-sheets must be supplied together")
    if args.premise_shots:
        build_premise_contacts(args.premise_shots, videos, args.premise_sheets)
        print("premise_contacts=%d" % len(videos))
        return
    candidates: list[dict[str, object]] = []
    for video in videos:
        candidates.extend(candidate_units(video))
    write_rows(args.out / "candidates.csv", candidates)
    print("candidate_groups=" + repr(Counter(str(row["selection_group"]) for row in candidates)))
    selected = choose_units(candidates)
    shots = args.out / "shots.csv"
    write_rows(shots, selected)
    if args.build_sheets:
        build_sheets(shots, args.out / "sheets")
    print("selected=%d games=%d" % (len(selected), len({row["video_sha256"] for row in selected})))


if __name__ == "__main__":
    main()
