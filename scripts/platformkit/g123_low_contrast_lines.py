"""Measure one preregistered CLAHE treatment on frozen basketball line inputs."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.g115_paint_line_recall import (
    MARKS,
    MISS_REASON_FILE,
    REBUILT_TILES,
    frame_key,
    rebuild_valid_tiles,
    valid_manifest,
)
from scripts.platformkit.g93_line_detection_limit import (
    MISS_REASONS,
    ROLE_COLOURS,
    ROLES,
    _matches,
    _segments_for,
    wilson_interval,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g123_contrast"
G84_LABELS = ROOT / "g84_candidate_quality/per_group_labels.csv"
G115_ROWS = ROOT / "g115_recall/line_measurements.csv"
CLIP_LIMIT = 2.0
TILE_GRID = (8, 8)
Segment = tuple[tuple[int, int], tuple[int, int]]
SegmentsByFrame = dict[str, list[Segment]]


def enhance_contrast(frame: np.ndarray) -> np.ndarray:
    """Apply the preregistered whole-frame CIELAB-L CLAHE transformation."""
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    lightness, channel_a, channel_b = cv2.split(lab)
    enhanced = cv2.createCLAHE(clipLimit=CLIP_LIMIT, tileGridSize=TILE_GRID).apply(lightness)
    return cv2.cvtColor(cv2.merge((enhanced, channel_a, channel_b)), cv2.COLOR_LAB2BGR)


def _load_marks() -> dict[str, dict[str, dict[str, Any]]]:
    with MARKS.open(encoding="ascii") as handle:
        return json.load(handle)["frames"]


def _load_baseline_misses() -> dict[str, str]:
    with MISS_REASON_FILE.open(encoding="ascii") as handle:
        return json.load(handle)["miss_reasons"]


def _hand_segment(mark: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    first, last = mark["endpoints"]
    return ((int(first[0]), int(first[1])), (int(last[0]), int(last[1])))


def _audited_labels() -> list[dict[str, str]]:
    with G84_LABELS.open(newline="", encoding="ascii") as handle:
        labels = list(csv.DictReader(handle))
    identities = {(row["clip"], row["frame_index"], row["group_index"]) for row in labels}
    if len(labels) != 1764 or len(identities) != len(labels):
        raise ValueError("G84 audited labels must contain 1764 unique candidates")
    return labels


def _label_endpoints(label: dict[str, str]) -> tuple[tuple[int, int], tuple[int, int]]:
    return ((int(label["x1"]), int(label["y1"])), (int(label["x2"]), int(label["y2"])))


def _baseline_precision(labels: list[dict[str, str]], identities: set[str]) -> list[dict[str, str]]:
    subset = [row for row in labels if f"{row['clip']}:{row['frame_index']}" in identities]
    if len(subset) != len({(row["clip"], row["frame_index"], row["group_index"]) for row in subset}):
        raise ValueError("G84 subset labels must be unique")
    rows = []
    for scope, values in (("G84_audited_33", labels), ("G115_valid_30", subset)):
        court = sum(row["label"] == "court_line" for row in values)
        low, high = wilson_interval(court, len(values))
        rows.append({"scope": scope, "court_line_candidates": str(court), "candidates": str(len(values)),
                     "precision": f"{court / len(values):.6f}",
                     "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    return rows


def _measure_recall() -> tuple[list[dict[str, str]], Counter[str], SegmentsByFrame]:
    marks = _load_marks()
    old_misses = _load_baseline_misses()
    manifest = valid_manifest()
    expected = {frame_key(row) for row in manifest}
    if set(marks) != expected:
        raise ValueError("G123 must use exactly G115's 30 hand-marked frames")
    rows: list[dict[str, str]] = []
    candidates_by_frame: SegmentsByFrame = {}
    histogram: Counter[str] = Counter()
    for source in manifest:
        key = frame_key(source)
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        candidates = _segments_for(enhance_contrast(image))
        candidates_by_frame[key] = candidates
        if set(marks[key]) != set(ROLES):
            raise ValueError(f"{key} does not mark all frozen roles")
        for role in ROLES:
            mark = marks[key][role]
            visible = bool(mark["visible"])
            row = {"clip": source["clip"], "frame_index": source["frame_index"], "role": role,
                   "visible": str(visible).lower(), "detected": "", "matching_group_indices": "",
                   "miss_reason": "", "baseline_miss_reason": "", "endpoints": ""}
            if not visible:
                rows.append(row)
                continue
            match = [index for index, candidate in enumerate(candidates) if _matches(candidate, _hand_segment(mark))]
            detected = bool(match)
            reason_key = f"{key}:{role}"
            reason = "" if detected else old_misses.get(reason_key, "other")
            if reason not in MISS_REASONS and reason:
                raise ValueError(f"invalid after miss reason for {reason_key}")
            if reason:
                histogram[reason] += 1
            row.update({"detected": str(detected).lower(), "matching_group_indices": ";".join(map(str, match)),
                        "miss_reason": reason, "baseline_miss_reason": old_misses.get(reason_key, ""),
                        "endpoints": json.dumps(mark["endpoints"], separators=(",", ":"))})
            rows.append(row)
    return rows, histogram, candidates_by_frame


def _after_precision(
    labels: list[dict[str, str]], identities: set[str],
    candidates_by_frame: SegmentsByFrame,
) -> tuple[list[dict[str, str]], SegmentsByFrame]:
    courts: SegmentsByFrame = {}
    for label in labels:
        key = f"{label['clip']}:{label['frame_index']}"
        if key in identities and label["label"] == "court_line":
            courts.setdefault(key, []).append(_label_endpoints(label))
    rows: list[dict[str, str]] = []
    for key, candidates in candidates_by_frame.items():
        clip, frame_index = key.rsplit(":", 1)
        for index, candidate in enumerate(candidates):
            transferred = any(_matches(candidate, court) for court in courts.get(key, []))
            rows.append({"clip": clip, "frame_index": frame_index, "group_index": str(index),
                         "label_transfer": "court_line" if transferred else "other",
                         "endpoints": json.dumps(candidate, separators=(",", ":"))})
    if not rows or len({(row["clip"], row["frame_index"], row["group_index"]) for row in rows}) != len(rows):
        raise ValueError("post-contrast candidate rows must be unique")
    return rows, courts


def _recall_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    visible = [row for row in rows if row["visible"] == "true"]
    summary = []
    for role in (*ROLES, "overall"):
        subset = visible if role == "overall" else [row for row in visible if row["role"] == role]
        found = sum(row["detected"] == "true" for row in subset)
        low, high = wilson_interval(found, len(subset))
        summary.append({"role": role, "detected": str(found), "visible": str(len(subset)),
                        "recall": f"{found / len(subset):.6f}", "wilson_95_low": f"{low:.6f}",
                        "wilson_95_high": f"{high:.6f}"})
    return summary


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render(source: dict[str, str], marks: dict[str, dict[str, Any]], rows: list[dict[str, str]]) -> None:
    image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
    if image is None:
        raise FileNotFoundError(source["tile_filename"])
    image = enhance_contrast(image)
    for index, (first, last) in enumerate(_segments_for(image)):
        cv2.line(image, first, last, (180, 180, 180), 1)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (255, 255, 255), 1)
    scored = {row["role"]: row for row in rows if row["clip"] == source["clip"] and row["frame_index"] == source["frame_index"]}
    for position, role in enumerate(ROLES):
        mark, colour = marks[role], ROLE_COLOURS[role]
        if not mark["visible"]:
            text = f"{role}: not visible"
        else:
            first, last = _hand_segment(mark)
            cv2.line(image, first, last, colour, 2)
            score = scored[role]
            text = f"{role}: found" if score["detected"] == "true" else f"{role}: miss {score['miss_reason']}"
        cv2.putText(image, text, (8, 42 + 16 * position), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
    if not cv2.imwrite(str(OUT / "renders" / source["tile_filename"]), image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(source["tile_filename"])


def write_artifacts() -> None:
    """Write all G123 frozen-sample measurements and CLAHE segment overlays."""
    rebuild_valid_tiles()
    OUT.mkdir(exist_ok=True)
    (OUT / "renders").mkdir(exist_ok=True)
    rows, histogram, candidates_by_frame = _measure_recall()
    identities = set(candidates_by_frame)
    labels = _audited_labels()
    precision_rows = _baseline_precision(labels, identities)
    candidate_rows, _ = _after_precision(labels, identities, candidates_by_frame)
    courts = sum(row["label_transfer"] == "court_line" for row in candidate_rows)
    low, high = wilson_interval(courts, len(candidate_rows))
    precision_rows.append({"scope": "CLAHE_fixed_label_transfer_30", "court_line_candidates": str(courts),
                           "candidates": str(len(candidate_rows)), "precision": f"{courts / len(candidate_rows):.6f}",
                           "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    _write_csv(OUT / "line_measurements.csv", rows)
    _write_csv(OUT / "recall_summary.csv", _recall_summary(rows))
    _write_csv(OUT / "candidate_precision_summary.csv", precision_rows)
    _write_csv(OUT / "candidate_label_transfer.csv", candidate_rows)
    with (OUT / "after_miss_reason_histogram.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["miss_reason", "count"])
        writer.writeheader()
        for reason in sorted(MISS_REASONS):
            writer.writerow({"miss_reason": reason, "count": histogram[reason]})
    marks = _load_marks()
    for source in valid_manifest():
        _render(source, marks[frame_key(source)], rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="read-only rebuild and write G123 evidence")
    arguments = parser.parse_args()
    if arguments.write:
        write_artifacts()
        print("wrote_g123_artifacts")
