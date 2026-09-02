"""Measure G132's preregistered original-plus-CLAHE segment union."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import cv2

from domains.basketball.tracking.line_calibration import (
    ObservedSegment,
    candidate_line_group_details,
    detect_lsd_segments,
)
from scripts.platformkit.g115_paint_line_recall import (
    MARKS, REBUILT_TILES, frame_key, rebuild_valid_tiles, valid_manifest,
)
from scripts.platformkit.g123_low_contrast_lines import (
    CLIP_LIMIT, TILE_GRID, _audited_labels, _hand_segment, _load_marks,
    enhance_contrast,
)
from scripts.platformkit.g84_candidate_line_quality import _endpoint_pair
from scripts.platformkit.g93_line_detection_limit import (
    ROLE_COLOURS, ROLES, _matches, wilson_interval,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g132_union"
DUPLICATE_ENDPOINT_TOLERANCE_PX = 1.0
Segment = tuple[tuple[int, int], tuple[int, int]]
CandidatesByFrame = dict[str, list[Segment]]


def _near_duplicate(first: ObservedSegment, second: ObservedSegment) -> bool:
    """Return whether two LSD fragments pair within the preregistered 1px guard."""
    a = ((first.endpoints[0], first.endpoints[1]), (first.endpoints[2], first.endpoints[3]))
    b = ((second.endpoints[0], second.endpoints[1]), (second.endpoints[2], second.endpoints[3]))
    paired = zip(a, b)
    reversed_paired = zip(a, reversed(b))
    return any(all(abs(x - y) <= DUPLICATE_ENDPOINT_TOLERANCE_PX for left, right in pairs for x, y in zip(left, right))
               for pairs in (paired, reversed_paired))


def union_segments(baseline: list[ObservedSegment], enhanced: list[ObservedSegment]) -> list[ObservedSegment]:
    """Keep baseline proposals and append only non-duplicate enhanced proposals."""
    return [*baseline, *(segment for segment in enhanced if not any(_near_duplicate(segment, old) for old in baseline))]


def _candidates(image: Any) -> tuple[list[Segment], list[Segment], list[Segment], int]:
    baseline = detect_lsd_segments(image, 28.0)
    enhanced = detect_lsd_segments(enhance_contrast(image), 28.0)
    combined = union_segments(baseline, enhanced)
    as_groups = lambda values: [_endpoint_pair(group) for group in candidate_line_group_details(values, 5.0, 10.0)]
    return as_groups(baseline), as_groups(enhanced), as_groups(combined), len(combined)


def _rows() -> tuple[list[dict[str, str]], CandidatesByFrame, CandidatesByFrame, list[dict[str, str]]]:
    marks = _load_marks()
    records: list[dict[str, str]] = []
    baseline_by_frame: CandidatesByFrame = {}
    union_by_frame: CandidatesByFrame = {}
    inventory: list[dict[str, str]] = []
    for source in valid_manifest():
        key = frame_key(source)
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        baseline, enhanced, union, union_segment_count = _candidates(image)
        baseline_by_frame[key], union_by_frame[key] = baseline, union
        inventory.append({"clip": source["clip"], "frame_index": source["frame_index"],
                          "baseline_groups": str(len(baseline)), "enhanced_groups": str(len(enhanced)),
                          "union_segments": str(union_segment_count), "union_groups": str(len(union))})
        for role in ROLES:
            mark = marks[key][role]
            visible = str(bool(mark["visible"])).lower()
            base_match = [] if visible == "false" else [i for i, candidate in enumerate(baseline) if _matches(candidate, _hand_segment(mark))]
            union_match = [] if visible == "false" else [i for i, candidate in enumerate(union) if _matches(candidate, _hand_segment(mark))]
            records.append({"clip": source["clip"], "frame_index": source["frame_index"], "role": role,
                            "visible": visible, "baseline_detected": str(bool(base_match)).lower(),
                            "union_detected": str(bool(union_match)).lower(),
                            "baseline_matching_group_indices": ";".join(map(str, base_match)),
                            "union_matching_group_indices": ";".join(map(str, union_match)),
                            "additive_survived": "" if visible == "false" else str(not base_match or bool(union_match)).lower(),
                            "endpoints": "" if visible == "false" else json.dumps(mark["endpoints"], separators=(",", ":"))})
    return records, baseline_by_frame, union_by_frame, inventory


def _summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    visible = [row for row in rows if row["visible"] == "true"]
    summary: list[dict[str, str]] = []
    for variant, field in (("baseline", "baseline_detected"), ("union", "union_detected")):
        for role in (*ROLES, "overall"):
            subset = visible if role == "overall" else [row for row in visible if row["role"] == role]
            found = sum(row[field] == "true" for row in subset)
            low, high = wilson_interval(found, len(subset))
            summary.append({"variant": variant, "role": role, "detected": str(found), "visible": str(len(subset)),
                            "recall": f"{found / len(subset):.6f}", "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    return summary


def _precision(candidates_by_frame: CandidatesByFrame) -> list[dict[str, str]]:
    courts: dict[str, list[Segment]] = {}
    for label in _audited_labels():
        key = f"{label['clip']}:{label['frame_index']}"
        if key in candidates_by_frame and label["label"] == "court_line":
            courts.setdefault(key, []).append(((int(label["x1"]), int(label["y1"])), (int(label["x2"]), int(label["y2"]))))
    rows: list[dict[str, str]] = []
    for key, candidates in candidates_by_frame.items():
        clip, frame_index = key.rsplit(":", 1)
        for group_index, candidate in enumerate(candidates):
            transferred = any(_matches(candidate, court) for court in courts.get(key, []))
            rows.append({"clip": clip, "frame_index": frame_index, "group_index": str(group_index),
                         "label_transfer": "court_line" if transferred else "other",
                         "endpoints": json.dumps(candidate, separators=(",", ":"))})
    if len(rows) != len({(row["clip"], row["frame_index"], row["group_index"]) for row in rows}):
        raise ValueError("candidate precision units must be unique")
    return rows


def _precision_summary(baseline: list[dict[str, str]], union: list[dict[str, str]]) -> list[dict[str, str]]:
    result = []
    for variant, rows in (("baseline", baseline), ("union", union)):
        courts = sum(row["label_transfer"] == "court_line" for row in rows)
        low, high = wilson_interval(courts, len(rows))
        result.append({"variant": variant, "court_line_candidates": str(courts), "candidates": str(len(rows)),
                       "precision": f"{courts / len(rows):.6f}", "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    return result


def _render(source: dict[str, str], marks: dict[str, dict[str, Any]], rows: list[dict[str, str]], candidates: list[Segment]) -> None:
    image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
    if image is None:
        raise FileNotFoundError(source["tile_filename"])
    for index, (first, last) in enumerate(candidates):
        cv2.line(image, first, last, (180, 180, 180), 1)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (255, 255, 255), 1)
    scored = {row["role"]: row for row in rows if row["clip"] == source["clip"] and row["frame_index"] == source["frame_index"]}
    for position, role in enumerate(ROLES):
        mark, colour = marks[role], ROLE_COLOURS[role]
        text = f"{role}: not visible" if not mark["visible"] else f"{role}: {'found' if scored[role]['union_detected'] == 'true' else 'miss'}"
        if mark["visible"]:
            cv2.line(image, *_hand_segment(mark), colour, 2)
        cv2.putText(image, text, (8, 42 + 16 * position), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
    if not cv2.imwrite(str(OUT / "renders" / source["tile_filename"]), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(source["tile_filename"])


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts(rebuild_tiles: bool = True) -> None:
    """Read-only rebuild and write the preregistered G132 evidence artifacts."""
    if rebuild_tiles:
        rebuild_valid_tiles()
    OUT.mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    rows, baseline_by_frame, union_by_frame, inventory = _rows()
    baseline_precision, union_precision = _precision(baseline_by_frame), _precision(union_by_frame)
    _write_csv(OUT / "line_measurements.csv", rows)
    _write_csv(OUT / "recall_summary.csv", _summary(rows))
    _write_csv(OUT / "segment_inventory.csv", inventory)
    _write_csv(OUT / "baseline_candidate_label_transfer.csv", baseline_precision)
    _write_csv(OUT / "union_candidate_label_transfer.csv", union_precision)
    _write_csv(OUT / "candidate_precision_summary.csv", _precision_summary(baseline_precision, union_precision))
    visible = [row for row in rows if row["visible"] == "true"]
    additive = [row for row in visible if row["baseline_detected"] == "true"]
    _write_csv(OUT / "additive_check.csv", additive)
    with (OUT / "preregistration.json").open("w", encoding="ascii") as handle:
        json.dump({"clahe_clip_limit": CLIP_LIMIT, "clahe_tile_grid": TILE_GRID,
                   "duplicate_endpoint_tolerance_px": DUPLICATE_ENDPOINT_TOLERANCE_PX,
                   "group_once_over_union": True, "baseline_first": True}, handle, indent=2)
    marks = _load_marks()
    for source in valid_manifest():
        _render(source, marks[frame_key(source)], rows, union_by_frame[frame_key(source)])
    if len(additive) != 25 or not all(row["additive_survived"] == "true" for row in additive):
        print(f"baseline_matches={len(additive)} union_survivors={sum(row['additive_survived'] == 'true' for row in additive)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="read-only rebuild and write G132 evidence")
    parser.add_argument("--reuse-local-tiles", action="store_true", help="use the verified G115 30-tile local cache")
    arguments = parser.parse_args()
    if arguments.write:
        write_artifacts(rebuild_tiles=not arguments.reuse_local_tiles)
        print("wrote_g132_artifacts")
