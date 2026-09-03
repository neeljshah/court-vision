"""Build and recompute the G130 source-first basketball visibility census."""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ClipInfo:
    """Immutable source metadata used for the stratified frame draw."""

    source_file: str
    decoded_frames: int
    width: int
    height: int


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Return the two-sided Wilson confidence interval for a binomial share."""
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("successes must be between zero and a positive total")
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    radius = z * ((proportion * (1 - proportion) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return centre - radius, centre + radius


def stratified_draw(clips: Iterable[ClipInfo], seed: int, strata_per_clip: int) -> list[dict[str, object]]:
    """Draw one unique zero-based frame index from every equal temporal stratum."""
    if strata_per_clip <= 0:
        raise ValueError("strata_per_clip must be positive")
    rng = random.Random(seed)
    rows: list[dict[str, object]] = []
    for clip in sorted(clips, key=lambda item: item.source_file):
        if clip.decoded_frames < strata_per_clip:
            raise ValueError(f"{clip.source_file} has fewer frames than strata")
        clip_id = clip.source_file.removesuffix(".mp4")
        for slot in range(strata_per_clip):
            start = clip.decoded_frames * slot // strata_per_clip
            stop = clip.decoded_frames * (slot + 1) // strata_per_clip
            source_frame = rng.randrange(start, stop)
            rows.append(
                {
                    "audit_id": f"{clip_id}__s{slot:02d}__f{source_frame:06d}",
                    "clip": clip_id,
                    "source_file": clip.source_file,
                    "slot": slot,
                    "source_frame": source_frame,
                    "decoded_frames": clip.decoded_frames,
                    "width": clip.width,
                    "height": clip.height,
                }
            )
    keys = {(str(row["source_file"]), int(row["source_frame"])) for row in rows}
    if len(keys) != len(rows):
        raise AssertionError("stratified draw unexpectedly recycled a source frame")
    return rows


def probe_clip(path: Path) -> ClipInfo:
    """Read exact decode count and frame dimensions from a local source clip."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=nb_frames,width,height",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    stream = json.loads(result.stdout)["streams"][0]
    raw_count = stream.get("nb_frames")
    if raw_count and raw_count != "N/A":
        count = int(raw_count)
    else:
        import cv2

        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise RuntimeError(f"cannot open source clip: {path.name}")
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        capture.release()
    if count <= 0:
        raise RuntimeError(f"no indexed frame count for source clip: {path.name}")
    return ClipInfo(path.name, count, int(stream["width"]), int(stream["height"]))


def load_manifest(path: Path) -> list[dict[str, object]]:
    """Load the frame rows from a G130 sample manifest."""
    return json.loads(path.read_text(encoding="utf-8"))["frames"]


def extract_source_frames(source_root: Path, manifest_rows: list[dict[str, object]], output_root: Path) -> None:
    """Sequentially decode every selected source index and save only selected JPEGs."""
    import cv2

    output_root.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[dict[str, object]]] = {}
    for row in manifest_rows:
        by_source.setdefault(str(row["source_file"]), []).append(row)
    for source_file, rows in by_source.items():
        pending = {int(row["source_frame"]): row for row in rows}
        capture = cv2.VideoCapture(str(source_root / source_file))
        if not capture.isOpened():
            raise RuntimeError(f"cannot open source clip: {source_file}")
        frame_index = 0
        while pending:
            ok, frame = capture.read()
            if not ok:
                capture.release()
                raise RuntimeError(f"decode ended before requested frame in {source_file}")
            row = pending.pop(frame_index, None)
            if row is not None:
                destination = output_root / f"{row['audit_id']}.jpg"
                if not cv2.imwrite(str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, 95]):
                    capture.release()
                    raise RuntimeError(f"could not write {destination}")
            frame_index += 1
        capture.release()


def write_review_sheet(rows: list[dict[str, object]], path: Path) -> None:
    """Write a blank source-first judgement sheet without a G111 label field."""
    fieldnames = [
        "audit_id",
        "clip",
        "source_file",
        "slot",
        "source_frame",
        "visible_paint_corners",
        "reachable_four_corners",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def blind_rejudge_rows(rows: list[dict[str, object]], seed: int) -> list[dict[str, object]]:
    """Select and shuffle an exact 20 percent re-judgement subset without labels."""
    if len(rows) % 5:
        raise ValueError("an exact 20 percent subset requires a frame count divisible by five")
    rng = random.Random(seed)
    selected = rng.sample(rows, len(rows) // 5)
    rng.shuffle(selected)
    return selected


def write_contact_sheets(rows: list[dict[str, object]], source_frames: Path, output_root: Path) -> None:
    """Create per-clip source-decode contact sheets with no judgement labels."""
    import cv2
    import numpy as np

    output_root.mkdir(parents=True, exist_ok=True)
    by_clip: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_clip.setdefault(str(row["clip"]), []).append(row)
    for clip, clip_rows in by_clip.items():
        tiles = []
        for row in sorted(clip_rows, key=lambda item: int(item["slot"])):
            image = cv2.imread(str(source_frames / f"{row['audit_id']}.jpg"))
            if image is None:
                raise RuntimeError(f"missing source decode for {row['audit_id']}")
            image = cv2.resize(image, (480, 270))
            cv2.putText(image, f"slot {row['slot']} frame {row['source_frame']}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
            cv2.putText(image, f"slot {row['slot']} frame {row['source_frame']}", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            tiles.append(image)
        rows_of_tiles = [np.hstack(tiles[index : index + 4]) for index in range(0, len(tiles), 4)]
        while len(rows_of_tiles[-1].shape) and rows_of_tiles[-1].shape[1] < 1920:
            rows_of_tiles[-1] = np.hstack((rows_of_tiles[-1], np.zeros((270, 480, 3), dtype=np.uint8)))
        sheet = np.vstack(rows_of_tiles)
        if not cv2.imwrite(str(output_root / f"{clip}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError(f"could not write contact sheet for {clip}")


def apply_decision_matrix(review_path: Path, matrix_path: Path) -> None:
    """Expand a clip-by-slot manual decision matrix into the row-level review CSV."""
    with matrix_path.open(newline="", encoding="utf-8") as handle:
        matrix = {row["clip"]: row for row in csv.DictReader(handle)}
    with review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        fieldnames = handle.seek(0) or list(csv.DictReader(handle).fieldnames or [])
    for row in rows:
        value = matrix[row["clip"]][f"s{int(row['slot']):02d}"]
        if value not in {"0", "4"}:
            raise ValueError(f"invalid decision {value!r} for {row['audit_id']}")
        row["visible_paint_corners"] = value
        row["reachable_four_corners"] = str(int(value == "4"))
    with review_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    """Run the reproducible G130 sampling and source-decode workflow."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("evidence_root", type=Path)
    parser.add_argument("--seed", type=int, default=13020260902)
    parser.add_argument("--strata-per-clip", type=int, default=15)
    parser.add_argument("--apply-matrix", type=Path)
    args = parser.parse_args()
    if args.apply_matrix:
        apply_decision_matrix(args.evidence_root / "first_pass_source_judgements.csv", args.apply_matrix)
        return
    clips = [probe_clip(path) for path in sorted(args.source_root.glob("*.mp4"))]
    if len(clips) != 14:
        raise RuntimeError(f"expected 14 current basketball source clips, found {len(clips)}")
    rows = stratified_draw(clips, args.seed, args.strata_per_clip)
    manifest = {
        "seed": args.seed,
        "method": "one seeded uniform draw from each equal temporal stratum of every current basketball source clip",
        "strata_per_clip": args.strata_per_clip,
        "per_clip": {clip.source_file.removesuffix(".mp4"): args.strata_per_clip for clip in clips},
        "frames": rows,
    }
    args.evidence_root.mkdir(parents=True, exist_ok=True)
    (args.evidence_root / "sample_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    extract_source_frames(args.source_root, rows, args.evidence_root / "source_decodes")
    write_contact_sheets(rows, args.evidence_root / "source_decodes", args.evidence_root / "contact_sheets")
    write_review_sheet(rows, args.evidence_root / "first_pass_source_judgements.csv")
    rejudge_seed = args.seed + 1
    rejudge_rows = blind_rejudge_rows(rows, rejudge_seed)
    (args.evidence_root / "rejudge_selection_manifest.json").write_text(
        json.dumps({"seed": rejudge_seed, "method": "seeded shuffled exact 20 percent subset", "frames": rejudge_rows}, indent=2) + "\n",
        encoding="utf-8",
    )
    write_review_sheet(rejudge_rows, args.evidence_root / "second_pass_source_judgements.csv")


if __name__ == "__main__":
    main()
