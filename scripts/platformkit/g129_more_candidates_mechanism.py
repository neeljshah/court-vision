"""Trace G120/G123 baseline recall losses without changing frozen detection."""
from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import (
    CandidateLineGroup,
    ObservedSegment,
    candidate_line_group_details,
    detect_lsd_segments,
)
from scripts.platformkit.g115_paint_line_recall import (
    REBUILT_TILES,
    _hand_segment,
    _load_marks,
    frame_key,
    valid_manifest,
)
from scripts.platformkit.g120_fragment_merge import _endpoints, _merge_details
from scripts.platformkit.g123_low_contrast_lines import enhance_contrast
from scripts.platformkit.g93_line_detection_limit import ROLE_COLOURS, ROLES, _matches


OUT = Path("docs/evidence/tracking/g129_mechanism")
Segment = tuple[tuple[int, int], tuple[int, int]]


@dataclass(frozen=True)
class Snapshot:
    """Frozen-stage segment and candidate geometry for one frame and variant."""

    image: np.ndarray
    segments: list[ObservedSegment]
    candidates: list[Segment]
    memberships: list[set[int]]


def _snapshot(image: np.ndarray, variant: str) -> Snapshot:
    """Run exactly the existing detector/grouping stages for a named variant."""
    transformed = enhance_contrast(image) if variant == "g123_clahe" else image
    raw = detect_lsd_segments(transformed, 28.0)
    entries = _merge_details(raw) if variant == "g120_merge" else [
        (segment, {index}) for index, segment in enumerate(raw)
    ]
    groups = candidate_line_group_details([segment for segment, _ in entries], 5.0, 10.0)
    memberships = []
    for group in groups:
        members: set[int] = set()
        for segment in group.segments:
            for prepared, source_indices in entries:
                if segment == prepared:
                    members.update(source_indices)
                    break
        memberships.append(members)
    return Snapshot(transformed, raw, [_endpoints(group) for group in groups], memberships)


def _matching(snapshot: Snapshot, hand: Segment) -> list[int]:
    return [index for index, candidate in enumerate(snapshot.candidates) if _matches(candidate, hand)]


def _closest(candidate: Segment, options: list[Segment]) -> int:
    """Return the candidate with the closest endpoint-pair squared distance."""
    def distance(option: Segment) -> int:
        direct = sum((a - b) ** 2 for point, other in zip(candidate, option) for a, b in zip(point, other))
        reverse = sum((a - b) ** 2 for point, other in zip(candidate, reversed(option)) for a, b in zip(point, other))
        return min(direct, reverse)
    return min(range(len(options)), key=lambda index: distance(options[index]))


def classify_loss(variant: str, shared_sources: int) -> tuple[str, str]:
    """Name the exact first non-superset stage, not a speculative matcher bug."""
    if variant == "g120_merge":
        detail = "merged fragment span refit changed the grouped candidate geometry"
        return "pre-group fragment merge", detail
    detail = "CLAHE changed the LSD proposal set before grouping"
    return "LSD proposal generation", detail


def _render(name: str, role: str, hand: Segment, baseline: Snapshot, intervention: Snapshot,
            baseline_match: list[int]) -> None:
    """Render a side-by-side baseline/intervention view of a lost visible line."""
    panels = []
    for title, snapshot, matches in (
        ("baseline", baseline, baseline_match), ("intervention", intervention, []),
    ):
        panel = snapshot.image.copy()
        for index, segment in enumerate(snapshot.candidates):
            colour = (0, 200, 0) if index in matches else (160, 160, 160)
            cv2.line(panel, segment[0], segment[1], colour, 1)
            cv2.putText(panel, str(index), segment[0], cv2.FONT_HERSHEY_SIMPLEX, .34, colour, 1)
        colour = ROLE_COLOURS[role]
        cv2.line(panel, hand[0], hand[1], colour, 3)
        cv2.putText(panel, f"{title}: {role}", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2)
        cv2.putText(panel, f"groups={len(snapshot.candidates)} segments={len(snapshot.segments)}",
                    (8, 62), cv2.FONT_HERSHEY_SIMPLEX, .42, (255, 255, 255), 1)
        panels.append(panel)
    divider = np.zeros((panels[0].shape[0], 8, 3), dtype=np.uint8)
    combined = cv2.hconcat((panels[0], divider, panels[1]))
    if not cv2.imwrite(str(OUT / "renders" / name), combined, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(name)


def trace() -> list[dict[str, str]]:
    """Trace every baseline-found visible role that either intervention loses."""
    marks = _load_marks()
    rows: list[dict[str, str]] = []
    for source in valid_manifest():
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        baseline = _snapshot(image, "baseline")
        for variant in ("g120_merge", "g123_clahe"):
            intervention = _snapshot(image, variant)
            for role in ROLES:
                mark = marks[frame_key(source)][role]
                if not mark["visible"]:
                    continue
                hand = _hand_segment(mark)
                before = _matching(baseline, hand)
                after = _matching(intervention, hand)
                if not before or after:
                    continue
                closest = _closest(baseline.candidates[before[0]], intervention.candidates)
                shared = len(baseline.memberships[before[0]] & intervention.memberships[closest])
                stage, mechanism = classify_loss(variant, shared)
                name = f"{variant}__{source['tile_filename'].replace('.jpg', '')}__{role}.jpg"
                rows.append({
                    "variant": variant, "clip": source["clip"], "frame_index": source["frame_index"],
                    "role": role, "stage_lost": stage, "mechanism": mechanism,
                    "baseline_segment_count": str(len(baseline.segments)),
                    "intervention_segment_count": str(len(intervention.segments)),
                    "baseline_group_count": str(len(baseline.candidates)),
                    "intervention_group_count": str(len(intervention.candidates)),
                    "baseline_matching_indices": ";".join(map(str, before)),
                    "intervention_matching_indices": "", "closest_intervention_index": str(closest),
                    "shared_baseline_source_segments": str(shared),
                    "baseline_matching_endpoints": json.dumps(baseline.candidates[before[0]], separators=(",", ":")),
                    "closest_intervention_endpoints": json.dumps(intervention.candidates[closest], separators=(",", ":")),
                    "render": f"renders/{name}",
                })
                _render(name, role, hand, baseline, intervention, before)
    return rows


def variant_measurements() -> list[dict[str, str]]:
    """Write every frozen role outcome with its frame's upstream counts."""
    marks = _load_marks()
    rows: list[dict[str, str]] = []
    for source in valid_manifest():
        image = cv2.imread(str(REBUILT_TILES / source["tile_filename"]))
        if image is None:
            raise FileNotFoundError(source["tile_filename"])
        for variant in ("baseline", "g120_merge", "g123_clahe"):
            snapshot = _snapshot(image, variant)
            for role in ROLES:
                mark = marks[frame_key(source)][role]
                visible = bool(mark["visible"])
                rows.append({"variant": variant, "clip": source["clip"], "frame_index": source["frame_index"],
                             "role": role, "visible": str(visible).lower(),
                             "detected": str(bool(_matching(snapshot, _hand_segment(mark))) if visible else False).lower(),
                             "lsd_segments": str(len(snapshot.segments)), "candidate_groups": str(len(snapshot.candidates))})
    return rows


def variant_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Summarize unique role and frame units without recycled counts."""
    summary = []
    for variant in ("baseline", "g120_merge", "g123_clahe"):
        subset = [row for row in rows if row["variant"] == variant]
        frames = {(row["clip"], row["frame_index"], row["lsd_segments"], row["candidate_groups"]) for row in subset}
        visible = [row for row in subset if row["visible"] == "true"]
        summary.append({"variant": variant, "visible_lines": str(len(visible)),
                        "detected_lines": str(sum(row["detected"] == "true" for row in visible)),
                        "total_lsd_segments": str(sum(int(frame[2]) for frame in frames)),
                        "total_candidate_groups": str(sum(int(frame[3]) for frame in frames))})
    return summary


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_artifacts() -> None:
    """Write the G129 per-case traces and summary from frozen local tiles."""
    OUT.mkdir(parents=True, exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    for path in renders.glob("*.jpg"):
        path.unlink()
    rows = trace()
    if not rows:
        raise ValueError("G129 expected at least one baseline-to-intervention loss")
    _write_csv(OUT / "lost_line_traces.csv", rows)
    measurements = variant_measurements()
    _write_csv(OUT / "variant_role_measurements.csv", measurements)
    summaries = variant_summary(measurements)
    _write_csv(OUT / "variant_summary.csv", summaries)
    counts = Counter((row["variant"], row["stage_lost"], row["mechanism"]) for row in rows)
    summary = [{"variant": variant, "stage_lost": stage, "mechanism": mechanism, "lost_lines": str(count)}
               for (variant, stage, mechanism), count in sorted(counts.items())]
    _write_csv(OUT / "mechanism_summary.csv", summary)
    print(f"lost_lines={len(rows)} renders={len(list(renders.glob('*.jpg')))}")


if __name__ == "__main__":
    write_artifacts()
