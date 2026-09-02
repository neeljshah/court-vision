"""Measure a preregistered fragment merge without changing the detector."""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import cv2

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    ObservedSegment,
    candidate_line_group_details,
    detect_lsd_segments,
)
from scripts.platformkit.g93_line_detection_limit import (
    ROLE_COLOURS,
    ROLES,
    _matches,
    wilson_interval,
)
from scripts.platformkit.g115_paint_line_recall import (
    REBUILT_TILES,
    _hand_segment,
    _load_marks,
    frame_key,
    valid_manifest,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g120_merge"
G84 = ROOT / "g84_candidate_quality"
ANGLE_DEGREES = 4.0
PERPENDICULAR_PIXELS = 8.0
MAX_GAP_PIXELS = 24.0
MIN_MERGED_LENGTH = 28.0


def _angle(first: ObservedSegment, second: ObservedSegment) -> float:
    """Return the unsigned orientation difference in degrees."""
    x1, y1, x2, y2 = first.endpoints
    a1, b1, a2, b2 = second.endpoints
    direction = math.degrees(math.atan2(y2 - y1, x2 - x1))
    other = math.degrees(math.atan2(b2 - b1, a2 - a1))
    difference = abs(direction - other) % 180.0
    return min(difference, 180.0 - difference)


def _direction(segment: ObservedSegment) -> tuple[float, float]:
    x1, y1, x2, y2 = segment.endpoints
    length = segment.length
    return ((x2 - x1) / length, (y2 - y1) / length)


def _compatible(first: ObservedSegment, second: ObservedSegment) -> bool:
    """Apply the four preregistered fragment-join conditions."""
    if _angle(first, second) > ANGLE_DEGREES:
        return False
    vx, vy = _direction(first)
    x1, y1, _, _ = first.endpoints
    points = ((x1, y1), first.endpoints[2:], second.endpoints[:2], second.endpoints[2:])
    distances = [abs((x - x1) * vy - (y - y1) * vx) for x, y in points[2:]]
    if max(distances, default=0.0) > PERPENDICULAR_PIXELS:
        return False
    first_values = [0.0, first.length]
    second_values = [
        (x - x1) * vx + (y - y1) * vy for x, y in points[2:]
    ]
    return max(min(first_values), min(second_values)) - min(max(first_values), max(second_values)) <= MAX_GAP_PIXELS


def _span(segments: Iterable[ObservedSegment]) -> ObservedSegment:
    members = tuple(segments)
    reference = members[0]
    vx, vy = _direction(reference)
    x0, y0, _, _ = reference.endpoints
    values = [
        ((x - x0) * vx + (y - y0) * vy, x, y)
        for segment in members for x, y in (segment.endpoints[:2], segment.endpoints[2:])
    ]
    start, end = min(values), max(values)
    return ObservedSegment((start[1], start[2], end[1], end[2]))


def merge_collinear_fragments(segments: Iterable[ObservedSegment]) -> list[ObservedSegment]:
    """Merge only preregistered nearby collinear fragment spans."""
    return [segment for segment, _ in _merge_details(list(segments))]


def _merge_details(segments: list[ObservedSegment]) -> list[tuple[ObservedSegment, set[int]]]:
    """Return merge spans with source-fragment identities for audit mapping."""
    clusters: list[list[ObservedSegment]] = []
    source_indices: list[list[int]] = []
    for source_index, segment in sorted(enumerate(segments), key=lambda item: item[1].endpoints):
        for cluster, indices in zip(clusters, source_indices):
            span = _span(cluster)
            if _compatible(span, segment):
                cluster.append(segment)
                indices.append(source_index)
                break
        else:
            clusters.append([segment])
            source_indices.append([source_index])
    return [(_span(cluster), set(indices)) for cluster, indices in zip(clusters, source_indices)
            if _span(cluster).length >= MIN_MERGED_LENGTH]


def _segments(image: Any, merged: bool) -> list[ObservedSegment]:
    fragments = detect_lsd_segments(image, 28.0)
    return merge_collinear_fragments(fragments) if merged else fragments


def _candidate_segments(image: Any, merged: bool) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    candidates = candidate_line_group_details(_segments(image, merged), 5.0, 10.0)
    return [_endpoints(candidate) for candidate in candidates]


def _endpoints(group: CandidateLineGroup) -> tuple[tuple[int, int], tuple[int, int]]:
    x0, y0 = group.anchor
    vx, vy = group.direction
    first, last = group.extent
    return ((round(x0 + first * vx), round(y0 + first * vy)),
            (round(x0 + last * vx), round(y0 + last * vy)))


def _recall_rows(merged: bool) -> list[dict[str, str]]:
    marks = _load_marks()
    rows: list[dict[str, str]] = []
    for source in valid_manifest():
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        candidates = _candidate_segments(image, merged)
        for role in ROLES:
            mark = marks[frame_key(source)][role]
            if not mark["visible"]:
                rows.append({"clip": source["clip"], "frame_index": source["frame_index"],
                             "role": role, "visible": "false", "detected": "", "matching_indices": ""})
                continue
            matching = [index for index, candidate in enumerate(candidates) if _matches(candidate, _hand_segment(mark))]
            rows.append({"clip": source["clip"], "frame_index": source["frame_index"],
                         "role": role, "visible": "true", "detected": str(bool(matching)).lower(),
                         "matching_indices": ";".join(map(str, matching))})
    return rows


def _recall_summary(rows: list[dict[str, str]], variant: str) -> list[dict[str, str]]:
    visible = [row for row in rows if row["visible"] == "true"]
    result = []
    for role in (*ROLES, "overall"):
        subset = visible if role == "overall" else [row for row in visible if row["role"] == role]
        found = sum(row["detected"] == "true" for row in subset)
        low, high = wilson_interval(found, len(subset))
        result.append({"variant": variant, "role": role, "detected": str(found), "visible": str(len(subset)),
                       "recall": f"{found / len(subset):.6f}", "wilson_95_low": f"{low:.6f}",
                       "wilson_95_high": f"{high:.6f}"})
    return result


def _g84_labels() -> dict[tuple[str, str], list[dict[str, str]]]:
    with (G84 / "per_group_labels.csv").open(newline="", encoding="ascii") as handle:
        by_frame: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
        for row in csv.DictReader(handle):
            by_frame[(row["clip"], row["frame_index"])].append(row)
    return by_frame


def _audited_label(
    candidate: tuple[tuple[int, int], tuple[int, int]], label_rows: list[dict[str, str]],
) -> tuple[str, str]:
    """Carry over only an unambiguous G84 audit label under frozen G93 matching."""
    matched = [row for row in label_rows if _matches(
        candidate, ((int(row["x1"]), int(row["y1"])), (int(row["x2"]), int(row["y2"])))
    )]
    indices = ";".join(row["group_index"] for row in matched)
    if matched and all(row["label"] == "court_line" for row in matched):
        return "court_line", indices
    return "other", indices


def _precision_rows(merged: bool) -> list[dict[str, str]]:
    labels = _g84_labels()
    manifest = valid_manifest()
    rows: list[dict[str, str]] = []
    for source in manifest:
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        fragments = detect_lsd_segments(image, 28.0)
        details = _merge_details(fragments) if merged else [(segment, {index}) for index, segment in enumerate(fragments)]
        candidates = candidate_line_group_details([segment for segment, _ in details], 5.0, 10.0)
        for index, candidate in enumerate(candidates):
            ends = _endpoints(candidate)
            label, provenance = _audited_label(ends, labels[(source["clip"], source["frame_index"])])
            rows.append({"clip": source["clip"], "frame_index": source["frame_index"],
                         "group_index": str(index), "label": label, "source_group_indices": provenance,
                         "x1": str(ends[0][0]), "y1": str(ends[0][1]),
                         "x2": str(ends[1][0]), "y2": str(ends[1][1])})
    return rows


def _precision_summary(rows: list[dict[str, str]], variant: str) -> dict[str, str]:
    total = len(rows)
    court = sum(row["label"] == "court_line" for row in rows)
    low, high = wilson_interval(court, total)
    return {"variant": variant, "court_line_candidates": str(court), "all_candidates": str(total),
            "precision": f"{court / total:.6f}", "wilson_95_low": f"{low:.6f}",
            "wilson_95_high": f"{high:.6f}"}


def _render_precision(rows: list[dict[str, str]]) -> None:
    destination = OUT / "precision_renders"
    destination.mkdir(parents=True, exist_ok=True)
    by_frame: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_frame[f"{row['clip']}:{row['frame_index']}"] .append(row)
    for source in valid_manifest():
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        for row in by_frame[f"{source['clip']}:{source['frame_index']}"]:
            first, last = (int(row["x1"]), int(row["y1"])), (int(row["x2"]), int(row["y2"]))
            colour = (0, 255, 0) if row["label"] == "court_line" else (0, 0, 255)
            cv2.line(image, first, last, colour, 1)
            cv2.putText(image, row["group_index"], first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
            cv2.putText(image, row["group_index"], first, cv2.FONT_HERSHEY_SIMPLEX, .34, colour, 1)
        name = f"{source['clip']}__f{source['frame_index']}.jpg"
        cv2.imwrite(str(destination / name), image)


def _render_recall(rows: list[dict[str, str]]) -> None:
    marks = _load_marks()
    by_frame: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_frame[f"{row['clip']}:{row['frame_index']}"] .append(row)
    destination = OUT / "recall_renders"
    destination.mkdir(parents=True, exist_ok=True)
    for source in valid_manifest():
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        for index, (first, last) in enumerate(_candidate_segments(image, True)):
            cv2.line(image, first, last, (180, 180, 180), 1)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
            cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (255, 255, 255), 1)
        scores = {row["role"]: row for row in by_frame[frame_key(source)]}
        for position, role in enumerate(ROLES):
            mark = marks[frame_key(source)][role]
            colour = ROLE_COLOURS[role]
            text = f"{role}: not visible"
            if mark["visible"]:
                cv2.line(image, *_hand_segment(mark), colour, 2)
                text = f"{role}: {'found' if scores[role]['detected'] == 'true' else 'miss'}"
            cv2.putText(image, text, (8, 42 + 16 * position), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
        cv2.imwrite(str(destination / source["tile_filename"]), image)


def write_artifacts() -> None:
    """Write fixed-population before/after recall and the after-merge renders."""
    before, after = _recall_rows(False), _recall_rows(True)
    OUT.mkdir(exist_ok=True)
    with (OUT / "recall_measurements.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", *before[0]])
        writer.writeheader()
        writer.writerows([{"variant": "before", **row} for row in before])
        writer.writerows([{"variant": "after", **row} for row in after])
    summary = _recall_summary(before, "before") + _recall_summary(after, "after")
    with (OUT / "recall_summary.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    before_all = int(summary[4]["detected"]) / int(summary[4]["visible"])
    after_all = int(summary[9]["detected"]) / int(summary[9]["visible"])
    with (OUT / "implied_cooccurrence.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", "recall", "recall_to_fourth"])
        writer.writeheader()
        writer.writerows([{"variant": "before", "recall": f"{before_all:.6f}", "recall_to_fourth": f"{before_all ** 4:.6f}"},
                          {"variant": "after", "recall": f"{after_all:.6f}", "recall_to_fourth": f"{after_all ** 4:.6f}"}])
    before_precision, after_precision = _precision_rows(False), _precision_rows(True)
    with (OUT / "precision_measurements.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", *before_precision[0]])
        writer.writeheader()
        writer.writerows([{"variant": "before", **row} for row in before_precision])
        writer.writerows([{"variant": "after", **row} for row in after_precision])
    precision_summary = [_precision_summary(before_precision, "before"), _precision_summary(after_precision, "after")]
    with (OUT / "precision_summary.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(precision_summary[0]))
        writer.writeheader()
        writer.writerows(precision_summary)
    _render_recall(after)
    _render_precision(after_precision)
    print(f"before_recall={summary[4]['detected']}/{summary[4]['visible']}")
    print(f"after_recall={summary[9]['detected']}/{summary[9]['visible']}")
    print(f"before_precision={precision_summary[0]['court_line_candidates']}/{precision_summary[0]['all_candidates']}")
    print(f"after_precision={precision_summary[1]['court_line_candidates']}/{precision_summary[1]['all_candidates']}")


if __name__ == "__main__":
    write_artifacts()
