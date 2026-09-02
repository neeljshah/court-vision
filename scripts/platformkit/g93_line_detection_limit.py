"""Measure G93 recall of fixed candidate groups on visible paint lines."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import cv2

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    candidate_line_group_details,
    detect_lsd_segments,
)
from scripts.platformkit.g84_candidate_line_quality import _endpoint_pair, _tile


ROOT = Path("docs/evidence/tracking")
G84 = ROOT / "g84_candidate_quality"
OUT = ROOT / "g93_detection_limit"
MARKS = OUT / "hand_marks.json"
ROLES = ("baseline", "free_throw", "lane_left", "lane_right")
MISS_REASONS = {
    "low_contrast",
    "occluded_partial",
    "too_short",
    "merged_with_neighbour",
    "split_into_fragments",
    "painted_over_by_court_logo",
    "other",
}
ANGLE_TOLERANCE_DEGREES = 12.0
PERPENDICULAR_TOLERANCE_PIXELS = 12.0
ENDPOINT_EXTENSION_PIXELS = 20.0
ROLE_COLOURS = {
    "baseline": (0, 0, 255),
    "free_throw": (0, 255, 0),
    "lane_left": (255, 0, 0),
    "lane_right": (0, 255, 255),
}


def _frame_key(row: dict[str, str]) -> str:
    return f"{row['clip']}:{row['frame_index']}"


def _segments_for(image: Any) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    groups: Iterable[CandidateLineGroup] = candidate_line_group_details(
        detect_lsd_segments(image, 28.0), 5.0, 10.0
    )
    return [_endpoint_pair(group) for group in groups]


def _angle_difference(first: tuple[int, int], second: tuple[int, int]) -> float:
    dx = first[0] - second[0]
    dy = first[1] - second[1]
    difference = abs(math.degrees(math.atan2(dy, dx))) % 180.0
    return min(difference, 180.0 - difference)


def _matches(
    candidate: tuple[tuple[int, int], tuple[int, int]],
    hand_segment: tuple[tuple[int, int], tuple[int, int]],
) -> bool:
    """Apply the preregistered G93 candidate-to-paint-line rule."""
    (cx1, cy1), (cx2, cy2) = candidate
    (hx1, hy1), (hx2, hy2) = hand_segment
    cdx, cdy = cx2 - cx1, cy2 - cy1
    hdx, hdy = hx2 - hx1, hy2 - hy1
    hand_length = math.hypot(hdx, hdy)
    if hand_length == 0 or math.hypot(cdx, cdy) == 0:
        return False
    if _angle_difference((cdx, cdy), (hdx, hdy)) > ANGLE_TOLERANCE_DEGREES:
        return False
    midpoint_x = (cx1 + cx2) / 2.0
    midpoint_y = (cy1 + cy2) / 2.0
    along = ((midpoint_x - hx1) * hdx + (midpoint_y - hy1) * hdy) / hand_length
    perpendicular = abs((midpoint_x - hx1) * hdy - (midpoint_y - hy1) * hdx) / hand_length
    return (
        perpendicular <= PERPENDICULAR_TOLERANCE_PIXELS
        and -ENDPOINT_EXTENSION_PIXELS <= along <= hand_length + ENDPOINT_EXTENSION_PIXELS
    )


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """Return the two-sided 95 percent Wilson interval."""
    if total == 0:
        return (float("nan"), float("nan"))
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return (centre - margin, centre + margin)


def _load_marks() -> dict[str, dict[str, dict[str, Any]]]:
    with MARKS.open(encoding="ascii") as handle:
        return json.load(handle)["frames"]


def _manifest() -> list[dict[str, str]]:
    with (G84 / "sample_manifest.csv").open(newline="", encoding="ascii") as handle:
        return list(csv.DictReader(handle))


def _hand_segment(mark: dict[str, Any]) -> tuple[tuple[int, int], tuple[int, int]]:
    points = mark["endpoints"]
    return ((int(points[0][0]), int(points[0][1])), (int(points[1][0]), int(points[1][1])))


def measure() -> tuple[list[dict[str, str]], Counter[str]]:
    """Score every pre-recorded visible line against regenerated candidates."""
    marks = _load_marks()
    rows: list[dict[str, str]] = []
    histogram: Counter[str] = Counter()
    manifest = _manifest()
    if set(marks) != {_frame_key(row) for row in manifest}:
        raise ValueError("hand marks must name exactly the 33 G84 frames")
    for source in manifest:
        key = _frame_key(source)
        image, _, _ = _tile(source["clip"], int(source["sheet_row"]))
        candidates = _segments_for(image)
        frame_marks = marks[key]
        if set(frame_marks) != set(ROLES):
            raise ValueError(f"{key} must mark all four paint-line roles")
        for role in ROLES:
            mark = frame_marks[role]
            visible = bool(mark["visible"])
            if not visible:
                if "endpoints" in mark or "miss_reason" in mark:
                    raise ValueError(f"non-visible {key} {role} cannot have endpoints or miss reason")
                continue
            hand = _hand_segment(mark)
            matching = [index for index, candidate in enumerate(candidates) if _matches(candidate, hand)]
            detected = bool(matching)
            reason = "" if detected else str(mark.get("miss_reason", ""))
            if not detected and reason not in MISS_REASONS:
                raise ValueError(f"missed {key} {role} needs a fixed-vocabulary reason")
            if detected and "miss_reason" in mark:
                raise ValueError(f"detected {key} {role} cannot have a miss reason")
            if reason:
                histogram[reason] += 1
            rows.append({
                "clip": source["clip"], "frame_index": source["frame_index"],
                "sheet_row": source["sheet_row"], "role": role, "visible": "true",
                "detected": str(detected).lower(), "matching_group_indices": ";".join(map(str, matching)),
                "miss_reason": reason, "endpoints": json.dumps(mark["endpoints"], separators=(",", ":")),
            })
    return rows, histogram


def _render_frame(
    source: dict[str, str], marks: dict[str, dict[str, Any]], rows: list[dict[str, str]],
) -> None:
    image, _, _ = _tile(source["clip"], int(source["sheet_row"]))
    for index, (first, last) in enumerate(_segments_for(image)):
        cv2.line(image, first, last, (180, 180, 180), 1)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (0, 0, 0), 2)
        cv2.putText(image, str(index), first, cv2.FONT_HERSHEY_SIMPLEX, .34, (255, 255, 255), 1)
    results = {row["role"]: row for row in rows if row["clip"] == source["clip"] and row["frame_index"] == source["frame_index"]}
    for role, mark in marks.items():
        colour = ROLE_COLOURS[role]
        if not mark["visible"]:
            cv2.putText(image, f"{role}: not visible", (8, 20 + 16 * ROLES.index(role)), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
            continue
        first, last = _hand_segment(mark)
        result = results[role]
        status = "found" if result["detected"] == "true" else f"miss {result['miss_reason']}"
        cv2.line(image, first, last, colour, 2)
        cv2.putText(image, f"{role}: {status}", (8, 20 + 16 * ROLES.index(role)), cv2.FONT_HERSHEY_SIMPLEX, .42, colour, 1)
    safe = f"{source['clip']}__f{source['frame_index']}.jpg"
    cv2.imwrite(str(OUT / "renders" / safe), image)


def write_artifacts() -> None:
    """Write G93 detail, summary, and every required candidate/mark overlay."""
    rows, histogram = measure()
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    for path in renders.glob("*.jpg"):
        path.unlink()
    with (OUT / "line_measurements.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary_rows: list[dict[str, str]] = []
    for role in (*ROLES, "overall"):
        subset = rows if role == "overall" else [row for row in rows if row["role"] == role]
        successes = sum(row["detected"] == "true" for row in subset)
        lower, upper = wilson_interval(successes, len(subset))
        summary_rows.append({"role": role, "detected": str(successes), "visible": str(len(subset)),
                             "recall": f"{successes / len(subset):.6f}", "wilson_95_low": f"{lower:.6f}",
                             "wilson_95_high": f"{upper:.6f}"})
    with (OUT / "recall_summary.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    with (OUT / "miss_reason_histogram.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["miss_reason", "count"])
        writer.writeheader()
        for reason in sorted(MISS_REASONS):
            writer.writerow({"miss_reason": reason, "count": histogram[reason]})
    marks = _load_marks()
    for source in _manifest():
        _render_frame(source, marks[_frame_key(source)], rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write committed measurement artifacts")
    arguments = parser.parse_args()
    if arguments.write:
        write_artifacts()
    else:
        results, _ = measure()
        print(f"visible_lines={len(results)} detected={sum(row['detected'] == 'true' for row in results)}")
