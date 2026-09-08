"""Create and score G345's sealed gap and crossing injections on fixed boxes."""
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from scripts.platformkit.tracking.g345_associate import (
    associate_arm_a, associate_arm_b, associate_arm_c, read_detection_csv, simultaneous_merges,
)

SEED = 3450908
GAP_COUNT, CROSSING_COUNT = 100, 100
GAP_MIN, GAP_MAX, CROSSING_FRAMES = 3, 20, 5
ARM_FUNCTIONS: tuple[tuple[str, Callable[..., list[dict[str, Any]]]], ...] = (
    ("ARM_A", associate_arm_a), ("ARM_B", associate_arm_b), ("ARM_C", associate_arm_c),
)


def _track_rows(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        grouped[row["track_id"]].append(row)
    return {key: sorted(rows, key=lambda row: int(row["frame"])) for key, rows in grouped.items()}


def gap_specs(clean: list[dict[str, Any]], seed: int = SEED, count: int = GAP_COUNT) -> list[dict[str, Any]]:
    """Select source-frame gaps with a sealed length in [3,20]."""
    rng, candidates = random.Random(seed), []
    for track_id, rows in _track_rows(clean).items():
        by_frame = {int(row["frame"]): row for row in rows}
        for start in sorted(by_frame):
            length = rng.randint(GAP_MIN, GAP_MAX)
            removed = [row for frame, row in by_frame.items() if start <= frame < start + length]
            before = [row for frame, row in by_frame.items() if frame < start]
            after = [row for frame, row in by_frame.items() if frame >= start + length]
            if removed and before and after:
                candidates.append({"reference_track_id": track_id, "length": length,
                                   "before_key": max(before, key=lambda row: int(row["frame"]))["obs_key"],
                                   "after_key": min(after, key=lambda row: int(row["frame"]))["obs_key"],
                                   "removed_keys": [row["obs_key"] for row in removed]})
    rng.shuffle(candidates)
    if len(candidates) < count:
        raise ValueError(f"only {len(candidates)} valid gap injections; need {count}")
    return [{**spec, "case_id": index} for index, spec in enumerate(candidates[:count])]


def crossing_specs(clean: list[dict[str, Any]], seed: int = SEED + 1,
                   count: int = CROSSING_COUNT) -> list[dict[str, Any]]:
    """Select distinct five-source-frame reference-pair swaps from ARM_C clean records."""
    rng, tracks, candidates = random.Random(seed), _track_rows(clean), []
    keys = sorted(tracks)
    for left_index, left_id in enumerate(keys):
        left = {int(row["frame"]): row for row in tracks[left_id]}
        for right_id in keys[left_index + 1:]:
            right = {int(row["frame"]): row for row in tracks[right_id]}
            for start in sorted(set(left).intersection(right)):
                frames = sorted(frame for frame in set(left).intersection(right)
                                if start <= frame < start + CROSSING_FRAMES)
                if frames:
                    candidates.append({"left_track_id": left_id, "right_track_id": right_id,
                                       "left_keys": [left[frame]["obs_key"] for frame in frames],
                                       "right_keys": [right[frame]["obs_key"] for frame in frames]})
    rng.shuffle(candidates)
    if len(candidates) < count:
        raise ValueError(f"only {len(candidates)} valid crossing injections; need {count}")
    return [{**spec, "case_id": index} for index, spec in enumerate(candidates[:count])]


def apply_gap(detections: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Delete only the sealed reference observation keys for one independent gap case."""
    removed = set(spec["removed_keys"])
    return [dict(row) for row in detections if row["obs_key"] not in removed]


def apply_crossing(detections: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Swap box positions, not observation keys, for the sealed five-frame crossing."""
    swaps = dict(zip(spec["left_keys"], spec["right_keys"]))
    swaps.update(dict(zip(spec["right_keys"], spec["left_keys"])))
    boxes = {row["obs_key"]: list(row["bbox"]) for row in detections}
    return [{**row, "bbox": boxes[swaps[row["obs_key"]]] if row["obs_key"] in swaps else list(row["bbox"])}
            for row in detections]


def reconnect_correct(records: list[dict[str, Any]], spec: dict[str, Any]) -> int:
    """Return one when the arm retains its own id across a reference-selected gap."""
    by_key = {row["obs_key"]: row["track_id"] for row in records}
    return int(by_key.get(spec["before_key"]) == by_key.get(spec["after_key"]) and
               spec["before_key"] in by_key)


def run_injections(detections: list[dict[str, Any]], seed: int = SEED) -> list[dict[str, Any]]:
    """Run all sealed independent cases; errors if 100 plus 100 cannot be enumerated."""
    clean = associate_arm_c(detections, "clean")
    rows: list[dict[str, Any]] = []
    for spec in gap_specs(clean, seed):
        altered = apply_gap(detections, spec)
        for arm, fn in ARM_FUNCTIONS:
            records = fn(altered, f"gap{spec['case_id']:06d}")
            rows.append({"case_id": spec["case_id"], "kind": "gap", "arm": arm, "gap_length": spec["length"],
                         "reconnect_correct": reconnect_correct(records, spec),
                         "simultaneous_merges": simultaneous_merges(records)})
    for spec in crossing_specs(clean, seed + 1):
        altered = apply_crossing(detections, spec)
        for arm, fn in ARM_FUNCTIONS:
            records = fn(altered, f"crossing{spec['case_id']:06d}")
            rows.append({"case_id": spec["case_id"], "kind": "crossing", "arm": arm, "gap_length": 0,
                         "reconnect_correct": "", "simultaneous_merges": simultaneous_merges(records)})
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write the required LF artifact with every integer cell zero-padded to six digits."""
    fields = ("case_id", "kind", "arm", "gap_length", "reconnect_correct", "simultaneous_merges")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f"{value:06d}" if isinstance(value, int) else value for key, value in row.items()})


def _main() -> None:
    parser = argparse.ArgumentParser(description="G345 sealed fixed-detection injections")
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    detections = [row for path in args.input for row in read_detection_csv(path)]
    rows = run_injections(detections)
    write_csv(args.output, rows)
    print(f"INJECTIONS {len(rows)}")


if __name__ == "__main__":
    _main()
