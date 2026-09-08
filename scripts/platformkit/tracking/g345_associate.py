"""Associate fixed detector boxes for G345 without any appearance input."""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from scipy.optimize import linear_sum_assignment
from src.tracking.advanced_tracker import _kf_correct, _kf_predict_bbox, _make_kf

HIGH_CONFIDENCE = 0.35
IOU_GATE = 0.30
RECONNECT_AGE = 30
FORBIDDEN_ID_FIELDS = ("track", "instance", "player_id", "baseline_slot")

def iou(left: list[float], right: list[float]) -> float:
    """Return xyxy intersection over union."""
    x1, y1 = max(left[0], right[0]), max(left[1], right[1])
    x2, y2 = min(left[2], right[2]), min(left[3], right[3])
    overlap = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if not overlap:
        return 0.0
    a = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    b = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    return overlap / (a + b - overlap)

def detection_digest(detections: Iterable[dict[str, Any]]) -> str:
    """Digest fixed detection content and reject post-association id fields."""
    rows = []
    for row in detections:
        if any(token in key.lower() for key in row for token in FORBIDDEN_ID_FIELDS):
            raise ValueError("fixed detections carry a track-id field")
        rows.append({key: row[key] for key in ("section", "frame", "score", "bbox", "obs_key")})
    payload = json.dumps(sorted(rows, key=lambda item: item["obs_key"]), sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def assert_identical_digests(*digests: str) -> str:
    """Return the common detection digest or raise before an arm is compared."""
    if not digests or len(set(digests)) != 1:
        raise AssertionError("arms did not receive byte-identical detections")
    return digests[0]

def _prediction(track: dict[str, Any], tick: int) -> list[float]:
    if track.get("pred_tick") == tick:
        return track["pred_bbox"]
    age = tick - track["tick"]
    predicted = None
    for _ in range(max(1, age)):
        predicted = _kf_predict_bbox(track["kf"])
    assert predicted is not None
    track["pred_tick"] = tick
    track["pred_bbox"] = [predicted[1], predicted[0], predicted[3], predicted[2]]
    return track["pred_bbox"]

def _match(tracks: list[dict[str, Any]], detections: list[dict[str, Any]], tick: int,
           gate: float) -> list[tuple[int, int]]:
    if not tracks or not detections:
        return []
    matrix = [[1.0 - iou(_prediction(track, tick), det["bbox"]) for det in detections]
              for track in tracks]
    rows, cols = linear_sum_assignment(matrix)
    return [(row, col) for row, col in zip(rows, cols) if 1.0 - matrix[row][col] >= gate]

def _update(track: dict[str, Any], det: dict[str, Any], frame: int, tick: int) -> None:
    new = det["bbox"]
    _kf_correct(track["kf"], (new[1], new[0], new[3], new[2]))
    track["bbox"], track["frame"], track["tick"] = list(new), frame, tick
    track.pop("pred_tick", None)
    track.pop("pred_bbox", None)

def _associate(detections: list[dict[str, Any]], generation: str, arm: str,
               two_stage: bool, reconnect: bool) -> list[dict[str, Any]]:
    grouped: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for det in detections:
        grouped[str(det["section"])][int(det["frame"])].append(det)
    out = []
    for section, by_frame in sorted(grouped.items()):
        tracks: list[dict[str, Any]] = []
        next_id = 1
        for frame, current in sorted(by_frame.items()):
            current = sorted(current, key=lambda row: row["obs_key"])
            tick = int(current[0].get("tick", frame))
            stride = int(current[0].get("tick_stride", 1))
            immediate = [track for track in tracks if frame - track["frame"] == stride]
            lost = ([track for track in tracks if stride < frame - track["frame"] <= RECONNECT_AGE]
                    if reconnect else [])
            claimed_tracks: set[int] = set()
            claimed_dets: set[int] = set()
            stages = ([ [index for index, det in enumerate(current) if det["score"] >= HIGH_CONFIDENCE],
                        [index for index, det in enumerate(current) if det["score"] < HIGH_CONFIDENCE] ]
                      if two_stage else [list(range(len(current)))])
            for indices in stages:
                candidates = [track for track in immediate + lost if id(track) not in claimed_tracks]
                indexed = [(index, current[index]) for index in indices if index not in claimed_dets]
                dets = [item[1] for item in indexed]
                for row, col in _match(candidates, dets, tick, IOU_GATE):
                    track, det = candidates[row], dets[col]
                    _update(track, det, frame, tick)
                    claimed_tracks.add(id(track))
                    claimed_dets.add(indexed[col][0])
                    out.append({**det, "arm": arm, "track_id": track["id"], "new_start": 0})
            for index, det in enumerate(current):
                if index in claimed_dets:
                    continue
                box = det["bbox"]
                track = {"id": f"{section}:{generation}:{next_id}", "bbox": list(box), "frame": frame,
                         "tick": tick,
                         "kf": _make_kf((box[1], box[0], box[3], box[2]))}
                next_id += 1
                tracks.append(track)
                out.append({**det, "arm": arm, "track_id": track["id"], "new_start": 1})
    return sorted(out, key=lambda row: (row["section"], int(row["frame"]), row["obs_key"]))

def associate_arm_a(detections: list[dict[str, Any]], generation: str = "clean") -> list[dict[str, Any]]:
    """Use the route's frame-free Hungarian plus Kalman-geometry equivalent."""
    return _associate(detections, generation, "ARM_A", False, False)

def associate_arm_b(detections: list[dict[str, Any]], generation: str = "clean") -> list[dict[str, Any]]:
    """Confirm G336 importability, then use its geometry-only fixed-box form."""
    importlib.import_module("scripts.platformkit.tracking.g336_track_id_continuity")
    return _associate(detections, generation, "ARM_B", False, False)

def associate_arm_c(detections: list[dict[str, Any]], generation: str = "clean") -> list[dict[str, Any]]:
    """Use two-stage IoU matching and the sealed one-to-one 30-frame reconnect."""
    return _associate(detections, generation, "ARM_C", True, True)

def simultaneous_merges(records: Iterable[dict[str, Any]]) -> int:
    """Count duplicate assignments of one track id within a single frame."""
    counts = Counter((row["section"], int(row["frame"]), row["track_id"]) for row in records)
    return sum(value - 1 for value in counts.values() if value > 1)

def metrics(records: list[dict[str, Any]], detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Return additive G345 metrics with named fixed-detection denominators."""
    by_tick: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for det in detections:
        by_tick[(det["section"], int(det["tick"]))].append(det)
    supported = sum(min(len(by_tick[(section, tick)]), len(by_tick[(section, tick + 1)]))
                    for section, tick in by_tick if (section, tick + 1) in by_tick)
    linked = sum(not row["new_start"] for row in records)
    lengths = Counter(row["track_id"] for row in records)
    return {"n_detections": len(detections), "n_detection_supported_adjacent_pairs": supported,
            "track_starts_per_1000_pairs": 1000 * sum(row["new_start"] for row in records) / max(1, supported),
            "coverage": linked / max(1, len(detections)), "simultaneous_merges": simultaneous_merges(records),
            "mean_tracklet_length": statistics.mean(lengths.values()) if lengths else 0.0}

def read_detection_csv(path: Path) -> list[dict[str, Any]]:
    """Read fixed detections with source frames and additive evaluated-tick metadata."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"section", "frame", "score", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("capture CSV schema is not fixed-detection input")
        rows = [{"section": row["section"], "frame": int(row["frame"]), "score": float(row["score"]),
                 "bbox": [float(row[key]) for key in ("bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")]}
                for row in reader]
    _add_evaluated_ticks(rows)
    for ordinal, row in enumerate(rows):
        row["obs_key"] = f"{row['section']}:{row['frame']:06d}:{ordinal:06d}"
    detection_digest(rows)
    return rows

def _add_evaluated_ticks(rows: list[dict[str, Any]]) -> None:
    """Add per-section evaluated ticks without changing source-frame semantics."""
    by_section: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_section[row["section"]].append(row)
    for section, group in by_section.items():
        frames = sorted({row["frame"] for row in group})
        strides = {b - a for a, b in zip(frames, frames[1:])}
        if len(strides) > 1:
            raise ValueError(f"section {section} has an irregular source-frame stride")
        tick = {frame: index for index, frame in enumerate(frames)}
        stride = next(iter(strides), 1)
        for row in group:
            row["tick"], row["tick_stride"] = tick[row["frame"]], stride

def print_reconnect_gate_units(detections: list[dict[str, Any]]) -> None:
    """Print the sealed source-frame gate and its additive tick equivalent per section."""
    strides = {str(row["section"]): int(row["tick_stride"]) for row in detections}
    for section, stride in sorted(strides.items()):
        ticks = RECONNECT_AGE / stride
        print("RECONNECT_GATE", section, "source_frames", RECONNECT_AGE,
              "evaluated_ticks", f"{ticks:g}", "tick_stride", stride)

def write_fixed_detection_csv(raw_path: Path, output_path: Path) -> None:
    """Project one G336 raw detector stream to boxes/confidences with no track fields."""
    rows = []
    with raw_path.open(encoding="utf-8") as handle:
        for raw in handle:
            item = json.loads(raw)
            box = item["bbox"]
            rows.append({"section": item["section"], "frame": int(item["frame"]), "score": float(item["score"]),
                         "bbox_x1": box[0], "bbox_y1": box[1], "bbox_x2": box[2], "bbox_y2": box[3]})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["section", "frame", "score", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"],
                                lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def arm_rows(detections: list[dict[str, Any]], generation: str) -> list[dict[str, Any]]:
    """Return one named-denominator metrics row for each arm and section."""
    arms = (associate_arm_a(detections, generation), associate_arm_b(detections, generation),
            associate_arm_c(detections, generation))
    rows = []
    for records in arms:
        arm = records[0]["arm"] if records else "EMPTY"
        for section in sorted({row["section"] for row in detections}):
            fixed = [row for row in detections if row["section"] == section]
            rows.append({"arm": arm, "section": section, "detection_digest": detection_digest(fixed),
                         **metrics([row for row in records if row["section"] == section], fixed)})
    for section in {row["section"] for row in rows}:
        assert_identical_digests(*(row["detection_digest"] for row in rows if row["section"] == section))
    return rows

def write_arms_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write LF arm metrics, six-padding all integral count cells."""
    fields = ("arm", "section", "detection_digest", "n_detections", "n_detection_supported_adjacent_pairs",
              "track_starts_per_1000_pairs", "coverage", "simultaneous_merges", "mean_tracklet_length")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f"{value:06d}" if isinstance(value, int) else value for key, value in row.items()})

def _main() -> None:
    parser = argparse.ArgumentParser(description="G345 fixed-detection associators")
    parser.add_argument("--input", type=Path, action="append")
    parser.add_argument("--capture-raw", type=Path)
    parser.add_argument("--capture-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generation", default="clean")
    args = parser.parse_args()
    if args.capture_raw or args.capture_output:
        if not args.capture_raw or not args.capture_output or args.input:
            parser.error("use capture-raw and capture-output together, without input")
        write_fixed_detection_csv(args.capture_raw, args.capture_output)
        return
    if not args.input:
        parser.error("input is required for association")
    detections = [det for path in args.input for det in read_detection_csv(path)]
    print("INTERPRETER", sys.executable)
    print_reconnect_gate_units(detections)
    rows = arm_rows(detections, args.generation)
    if args.output:
        write_arms_csv(args.output, rows)
    for row in rows:
        print(row["arm"], row["section"], json.dumps(row, sort_keys=True))

if __name__ == "__main__":
    _main()
