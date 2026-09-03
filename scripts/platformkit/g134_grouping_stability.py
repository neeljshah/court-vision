"""Measure G134 grouping instability without changing frozen acceptance values."""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2

from domains.basketball.tracking.line_calibration import CandidateLineGroup, ObservedSegment, candidate_line_group_details, detect_lsd_segments
from scripts.platformkit.g115_paint_line_recall import REBUILT_TILES, frame_key, valid_manifest
from scripts.platformkit.g123_low_contrast_lines import _audited_labels, _hand_segment, _load_marks, enhance_contrast
from scripts.platformkit.g132_additive_candidate_union import union_segments
from scripts.platformkit.g84_candidate_line_quality import _endpoint_pair
from scripts.platformkit.g93_line_detection_limit import ROLE_COLOURS, ROLES, _matches, wilson_interval


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g134_grouping"
OUTCOMES = ("SURVIVED", "MOVED", "ABSORBED", "FRAGMENTED")
Segment = tuple[tuple[int, int], tuple[int, int]]


def _segment_key(segment: ObservedSegment) -> tuple[float, float, float, float]:
    return tuple(float(value) for value in segment.endpoints)


def _group_keys(group: CandidateLineGroup) -> frozenset[tuple[float, float, float, float]]:
    return frozenset(_segment_key(segment) for segment in group.segments)


def stable_groups(baseline: list[ObservedSegment], enlarged: list[ObservedSegment]) -> list[CandidateLineGroup]:
    """Keep baseline fits immutable and group only G132-added proposals."""
    baseline_keys = {_segment_key(segment) for segment in baseline}
    added = [segment for segment in enlarged if _segment_key(segment) not in baseline_keys]
    return [*candidate_line_group_details(baseline, 5.0, 10.0), *candidate_line_group_details(added, 5.0, 10.0)]


def classify_group(baseline: CandidateLineGroup, enlarged: list[CandidateLineGroup]) -> str:
    """Classify baseline membership under the preregistered enlarged grouping."""
    original = _group_keys(baseline)
    memberships = [_group_keys(group) for group in enlarged if original & _group_keys(group)]
    if original in memberships:
        return "SURVIVED"
    if any(original < members for members in memberships):
        return "ABSORBED"
    if len(memberships) > 1 and original <= set().union(*memberships):
        return "FRAGMENTED"
    return "MOVED"


def _role_outcome(group_outcomes: list[str]) -> str:
    for outcome in OUTCOMES:
        if outcome in group_outcomes:
            return outcome
    raise ValueError("baseline match has no group outcome")


def _groups(image: Any) -> tuple[list[CandidateLineGroup], list[CandidateLineGroup], list[CandidateLineGroup]]:
    baseline = detect_lsd_segments(image, 28.0)
    enhanced = detect_lsd_segments(enhance_contrast(image), 28.0)
    enlarged = union_segments(baseline, enhanced)
    return candidate_line_group_details(baseline, 5.0, 10.0), candidate_line_group_details(enlarged, 5.0, 10.0), stable_groups(baseline, enlarged)


def _segments(groups: list[CandidateLineGroup]) -> list[Segment]:
    return [_endpoint_pair(group) for group in groups]


def measure() -> tuple[list[dict[str, str]], dict[str, list[Segment]], dict[str, list[Segment]], dict[str, list[Segment]]]:
    """Score all frozen role rows and group outcomes from local G115 tiles."""
    marks = _load_marks()
    rows: list[dict[str, str]] = []
    baseline_by_frame: dict[str, list[Segment]] = {}
    enlarged_by_frame: dict[str, list[Segment]] = {}
    stable_by_frame: dict[str, list[Segment]] = {}
    for source in valid_manifest():
        key = frame_key(source)
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        baseline, enlarged, stable = _groups(image)
        baseline_by_frame[key], enlarged_by_frame[key], stable_by_frame[key] = _segments(baseline), _segments(enlarged), _segments(stable)
        for role in ROLES:
            mark = marks[key][role]
            visible = str(bool(mark["visible"])).lower()
            hand = _hand_segment(mark) if visible == "true" else None
            base_indices = [] if hand is None else [index for index, candidate in enumerate(baseline_by_frame[key]) if _matches(candidate, hand)]
            enlarged_indices = [] if hand is None else [index for index, candidate in enumerate(enlarged_by_frame[key]) if _matches(candidate, hand)]
            stable_indices = [] if hand is None else [index for index, candidate in enumerate(stable_by_frame[key]) if _matches(candidate, hand)]
            group_outcomes = [classify_group(baseline[index], enlarged) for index in base_indices]
            outcome = "" if not group_outcomes else _role_outcome(group_outcomes)
            rows.append({
                "clip": source["clip"], "frame_index": source["frame_index"], "role": role, "visible": visible,
                "baseline_detected": str(bool(base_indices)).lower(), "enlarged_detected": str(bool(enlarged_indices)).lower(),
                "stable_detected": str(bool(stable_indices)).lower(), "outcome": outcome,
                "baseline_group_indices": ";".join(map(str, base_indices)), "enlarged_group_indices": ";".join(map(str, enlarged_indices)),
                "stable_group_indices": ";".join(map(str, stable_indices)),
                "group_outcomes": ";".join(group_outcomes),
                "endpoints": "" if hand is None else json.dumps(mark["endpoints"], separators=(",", ":")),
            })
    return rows, baseline_by_frame, enlarged_by_frame, stable_by_frame


def _summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    visible = [row for row in rows if row["visible"] == "true"]
    result: list[dict[str, str]] = []
    for variant, field in (("baseline", "baseline_detected"), ("enlarged", "enlarged_detected"), ("stable", "stable_detected")):
        found = sum(row[field] == "true" for row in visible)
        low, high = wilson_interval(found, len(visible))
        result.append({"variant": variant, "detected": str(found), "visible": str(len(visible)), "recall": f"{found / len(visible):.6f}", "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    return result


def _precision(candidates: dict[str, list[Segment]]) -> list[dict[str, str]]:
    courts: dict[str, list[Segment]] = {}
    for label in _audited_labels():
        key = f"{label['clip']}:{label['frame_index']}"
        if key in candidates and label["label"] == "court_line":
            courts.setdefault(key, []).append(((int(label["x1"]), int(label["y1"])), (int(label["x2"]), int(label["y2"]))))
    records: list[dict[str, str]] = []
    for key, groups in candidates.items():
        clip, frame_index = key.rsplit(":", 1)
        for group_index, candidate in enumerate(groups):
            records.append({"clip": clip, "frame_index": frame_index, "group_index": str(group_index), "label_transfer": "court_line" if any(_matches(candidate, court) for court in courts.get(key, [])) else "other", "endpoints": json.dumps(candidate, separators=(",", ":"))})
    if len(records) != len({(row["clip"], row["frame_index"], row["group_index"]) for row in records}):
        raise ValueError("candidate precision units must be unique")
    return records


def _precision_summary(values: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    result = []
    for variant, rows in values.items():
        found = sum(row["label_transfer"] == "court_line" for row in rows)
        low, high = wilson_interval(found, len(rows))
        result.append({"variant": variant, "court_line_candidates": str(found), "candidates": str(len(rows)), "precision": f"{found / len(rows):.6f}", "wilson_95_low": f"{low:.6f}", "wilson_95_high": f"{high:.6f}"})
    return result


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_panel(image: Any, groups: list[Segment], mark: Segment, label: str) -> Any:
    panel = image.copy()
    for first, last in groups:
        cv2.line(panel, first, last, (180, 180, 180), 1)
    cv2.line(panel, *mark, (0, 0, 255), 2)
    cv2.putText(panel, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (0, 0, 255), 2)
    cv2.putText(panel, label, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
    return panel


def _write_renders(rows: list[dict[str, str]], baseline: dict[str, list[Segment]], enlarged: dict[str, list[Segment]]) -> None:
    affected = [row for row in rows if row["baseline_detected"] == "true" and row["outcome"] != "SURVIVED"]
    if len(affected) < 5:
        affected = [row for row in rows if row["baseline_detected"] == "true"][:5]
    render_dir = OUT / "renders"
    render_dir.mkdir(exist_ok=True)
    for row in affected:
        key = f"{row['clip']}:{row['frame_index']}"
        source = next(item for item in valid_manifest() if frame_key(item) == key)
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        mark = tuple(tuple(point) for point in json.loads(row["endpoints"]))
        combined = cv2.hconcat([_render_panel(image, baseline[key], mark, "baseline"), _render_panel(image, enlarged[key], mark, f"enlarged {row['outcome']}")])
        filename = f"{source['tile_filename'].removesuffix('.jpg')}__{row['role']}.jpg"
        if not cv2.imwrite(str(render_dir / filename), combined, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise ValueError(filename)


def write_artifacts() -> None:
    """Write G134 measurements and side-by-side eye-check renders."""
    OUT.mkdir(exist_ok=True)
    rows, baseline, enlarged, stable = measure()
    _write_csv(OUT / "line_outcomes.csv", rows)
    _write_csv(OUT / "recall_summary.csv", _summary(rows))
    precision = {"baseline": _precision(baseline), "enlarged": _precision(enlarged), "stable": _precision(stable)}
    for variant, values in precision.items():
        _write_csv(OUT / f"{variant}_candidate_label_transfer.csv", values)
    _write_csv(OUT / "candidate_precision_summary.csv", _precision_summary(precision))
    outcome_rows = [{"outcome": outcome, "count": str(sum(row["outcome"] == outcome for row in rows))} for outcome in OUTCOMES]
    _write_csv(OUT / "outcome_distribution.csv", outcome_rows)
    _write_renders(rows, baseline, enlarged)
    baseline_matches = [row for row in rows if row["baseline_detected"] == "true"]
    stable_survival = sum(row["stable_detected"] == "true" for row in baseline_matches)
    print(f"baseline_matches={len(baseline_matches)} stable_survival={stable_survival}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write local G134 evidence from fixed tiles")
    arguments = parser.parse_args()
    if arguments.write:
        write_artifacts()
        print("wrote_g134_artifacts")
