"""Run the unchanged basketball gate funnel on G140's 17 native frames."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider, _line_support
from scripts.platformkit.basketball_gate_funnel import FrameGates, inspect_frame
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import (
    TOLERANCE_PX,
    _read_targets,
    _source_path,
    score_frame,
)


ROOT = Path("docs/evidence/tracking")
OUT = ROOT / "g229_keypoint_gate_funnel"
MIN_EDGE_SUPPORT = 0.16
GATE_1 = "1. _candidate_quads"
GATE_2 = "2. _paint area and shortest-side"
GATE_3 = "3. _paint _line_support"
GATE_4 = "4. baseline adjacency naming"
GATE_NAMES = (GATE_1, GATE_2, GATE_3, GATE_4)


def _gate_name(measured: FrameGates) -> str:
    return {
        "1_no_four_corner_outline": GATE_1,
        "2_no_physically_large_lane": GATE_2,
        "3_edge_support_below_minimum": GATE_3,
        "4_paint_named": GATE_4,
    }[measured.first_failure]


def _contour_counts(gray: np.ndarray) -> tuple[int, int, int, float]:
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    at_perimeter = [item for item in contours if cv2.arcLength(item, True) >= 120.0]
    four_vertices = [
        item for item in at_perimeter
        if len(cv2.approxPolyDP(item, 0.025 * cv2.arcLength(item, True), True)) == 4
    ]
    largest_perimeter = max((float(cv2.arcLength(item, True)) for item in contours), default=0.0)
    return len(contours), len(at_perimeter), len(four_vertices), largest_perimeter


def _metrics(frame: np.ndarray, provider: BasketballKeypointProvider, measured: FrameGates) -> tuple[dict[str, Any], np.ndarray | None]:
    """Retain unchanged-gate margins while invoking the canonical inspector."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    outlines = list(provider._candidate_quads(gray))
    if len(outlines) != measured.outline_quads:
        raise AssertionError("inspect_frame candidate count drifted")
    area_bar = 0.006 * width * height
    side_bar = 0.15 * height
    areas = [abs(float(cv2.contourArea(quad.reshape(-1, 1, 2)))) for quad in outlines]
    sides = [float(np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1).min()) for quad in outlines]
    physical = [quad for quad, area, side in zip(outlines, areas, sides)
                if area >= area_bar and side >= side_bar]
    supports = [_line_support(gray, quad) for quad in physical]
    if len(physical) != measured.physical_quads or sum(value >= MIN_EDGE_SUPPORT for value in supports) != measured.supported_quads:
        raise AssertionError("inspect_frame physical gate count drifted")
    gate = _gate_name(measured)
    best_quad: np.ndarray | None = None
    closeness = 0.0
    if gate == GATE_2 and outlines:
        choices = [(min(area / area_bar, side / side_bar), quad) for quad, area, side in zip(outlines, areas, sides)]
        closeness, best_quad = max(choices, key=lambda item: item[0])
    elif gate == GATE_3 and physical:
        choices = [(support / MIN_EDGE_SUPPORT, quad) for support, quad in zip(supports, physical)]
        closeness, best_quad = max(choices, key=lambda item: item[0])
    elif gate == GATE_4:
        closeness, best_quad = 1.0, physical[0] if physical else None
    raw_contours, perimeter_count, four_vertex_count, largest_perimeter = _contour_counts(gray)
    return ({
        "raw_contours": raw_contours,
        "contours_perimeter_ge_120": perimeter_count,
        "four_vertex_contours": four_vertex_count,
        "largest_contour_perimeter_px": largest_perimeter,
        "largest_contour_perimeter_fraction_of_bar": largest_perimeter / 120.0,
        "outline_quads": measured.outline_quads,
        "physical_quads": measured.physical_quads,
        "supported_quads": measured.supported_quads,
        "area_bar_px2": area_bar,
        "side_bar_px": side_bar,
        "largest_area_px2": max(areas, default=None),
        "largest_area_fraction_of_bar": max(areas) / area_bar if areas else None,
        "longest_shortest_side_px": max(sides, default=None),
        "longest_shortest_side_fraction_of_bar": max(sides) / side_bar if sides else None,
        "highest_line_support": max(supports, default=None),
        "line_support_fraction_of_bar": max(supports) / MIN_EDGE_SUPPORT if supports else None,
        "first_rejecting_gate": gate,
        "closest_fraction_of_rejected_gate_bar": closeness,
    }, best_quad)


def _render(image: np.ndarray, targets: list[dict[str, str]], quad: np.ndarray | None, destination: Path) -> None:
    panel = image.copy()
    if quad is not None:
        cv2.polylines(panel, [quad.round().astype(np.int32)], True, (0, 165, 255), 3)
    for target in targets:
        point = (int(target["x_px"]), int(target["y_px"]))
        cv2.circle(panel, point, round(TOLERANCE_PX), (0, 255, 255), 1)
        cv2.drawMarker(panel, point, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 11, 2)
    if not cv2.imwrite(str(destination), panel, [cv2.IMWRITE_JPEG_QUALITY, 95]):
        raise ValueError(destination)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _control(frames: dict[str, list[dict[str, str]]], provider: BasketballKeypointProvider) -> dict[str, int]:
    """Reproduce G227 before running any gate-margin diagnostic."""
    abstentions = 0
    all_four_total = 0
    corners = 0
    for audit_id in sorted(frames):
        targets = frames[audit_id]
        image = cv2.imread(str(_source_path(targets[0])))
        if image is None:
            raise FileNotFoundError(audit_id)
        detections = provider.detect(image)
        scored, _, all_four = score_frame(targets, [(item[0], item[1]) for item in detections.values()])
        abstentions += int(not detections)
        all_four_total += int(all_four)
        corners += sum(bool(item["available"]) for item in scored)
    result = {"abstentions": abstentions, "all_four_g205": all_four_total, "corners_g205": corners}
    if result != {"abstentions": 17, "all_four_g205": 0, "corners_g205": 0}:
        raise AssertionError("G227 abstention control did not reproduce")
    return result


def run() -> dict[str, Any]:
    """Execute the fixed G229 construct and write additive evidence artifacts."""
    if TOLERANCE_PX != 12.0:
        raise ValueError("G205 tolerance changed")
    frames = _read_targets()
    provider = BasketballKeypointProvider(min_edge_support=MIN_EDGE_SUPPORT)
    OUT.mkdir(exist_ok=True)
    renders = OUT / "renders"
    renders.mkdir(exist_ok=True)
    control = _control(frames, provider)
    rows: list[dict[str, Any]] = []
    rendered: list[tuple[float, str, np.ndarray, list[dict[str, str]], np.ndarray | None]] = []
    cooccurrence: dict[str, int] = {}
    for audit_id in sorted(frames):
        targets = frames[audit_id]
        source = _source_path(targets[0])
        image = cv2.imread(str(source))
        if image is None:
            raise FileNotFoundError(source)
        height, width = image.shape[:2]
        if (width, height) != (int(targets[0]["image_width"]), int(targets[0]["image_height"])):
            raise ValueError("native dimension mismatch for " + audit_id)
        measured = inspect_frame(image, provider)
        values, best_quad = _metrics(image, provider, measured)
        landmark_key = ",".join(measured.landmarks) if measured.landmarks else "none"
        cooccurrence[landmark_key] = cooccurrence.get(landmark_key, 0) + 1
        rows.append({
            "audit_id": audit_id,
            "source_path": str(source),
            "source_bytes": source.stat().st_size,
            "resolution": f"{width}x{height}",
            "league": "wnba" if audit_id.startswith("wnba__") else "ncaa_basketball",
            "named_landmarks": landmark_key,
            **values,
        })
        if values["closest_fraction_of_rejected_gate_bar"] is not None:
            rendered.append((float(values["closest_fraction_of_rejected_gate_bar"]), audit_id, image, targets, best_quad))
    for rank, (_, audit_id, image, targets, quad) in enumerate(sorted(rendered, key=lambda item: (-item[0], item[1]))[:3], 1):
        _render(image, targets, quad, renders / f"closest_{rank:02d}_{audit_id}.jpg")
    _write_csv(OUT / "per_frame.csv", rows)
    distribution = {gate: sum(row["first_rejecting_gate"] == gate for row in rows) for gate in GATE_NAMES}
    summary = {
        "control": control,
        "frames": len(rows),
        "min_edge_support": MIN_EDGE_SUPPORT,
        "first_reject_distribution": distribution,
        "landmark_cooccurrence": cooccurrence,
        "route_sha256": {
            "domains/basketball/tracking/keypoints.py": _sha256(Path("domains/basketball/tracking/keypoints.py")),
            "scripts/platformkit/basketball_gate_funnel.py": _sha256(Path("scripts/platformkit/basketball_gate_funnel.py")),
            "scripts/platformkit/tracking/g205_zero_shot_corner_probe.py": _sha256(Path("scripts/platformkit/tracking/g205_zero_shot_corner_probe.py")),
            "scripts/platformkit/tracking/g229_keypoint_gate_funnel.py": _sha256(Path("scripts/platformkit/tracking/g229_keypoint_gate_funnel.py")),
        },
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print("control abstentions=%d/17 all_four=%d/17 corners=%d/68" % (control["abstentions"], control["all_four_g205"], control["corners_g205"]))
    print("first_reject_distribution=" + json.dumps(distribution, sort_keys=True))
    return summary


if __name__ == "__main__":
    run()
