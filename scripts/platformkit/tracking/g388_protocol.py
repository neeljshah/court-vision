"""G388 audited paint-band geometry and binding-premise receipt helpers.

This module prepares deterministic controls and validates sealed rater records.
It never opens a source store or performs a rating or historical rescore.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

CONTROL_COUNT = 30
CONTROL_BAR = 27
CONTROL_LENGTH = 240.0
CONTROL_WHITE_PX = 6
CONTROL_BLACK_PX = 10
POINT_TOLERANCE = 3.0
PAIR_TOLERANCE = 6.0
MIN_SPAN = 60.0
AUDIT_POINTS = 9
AUDIT_REQUIRED = 8
FAMILIES = frozenset(("SIDELINE", "BASELINE", "CENTRE_LINE", "LANE_LINE", "FREE_THROW",
                      "THREE_POINT_STRAIGHT", "UNKNOWN"))
Point = tuple[float, float]


@dataclass(frozen=True)
class Band:
    """A finite native-pixel centreline used by controls and observed fragments."""

    first: Point
    second: Point

    def vector(self) -> Point:
        return self.second[0] - self.first[0], self.second[1] - self.first[1]

    def length(self) -> float:
        return math.hypot(*self.vector())


@dataclass(frozen=True)
class Fragment:
    """One rater's three native-pixel observations of one visible fragment."""

    tile: int
    family: str
    first: Point
    second: Point
    third: Point
    fragment_id: str = ""

    def line(self) -> Band:
        return Band(self.first, self.second)


def control_band(index: int, tile_offsets: tuple[Point, ...]) -> tuple[int, Band]:
    """Return the sealed tile index and native centreline for one control context."""
    if not 0 <= index < CONTROL_COUNT or len(tile_offsets) != 6:
        raise ValueError("G388 controls require 30 rows and six inherited tile offsets")
    tile = index % 6
    angle = math.radians((index % 3) * 30)
    centre = tile_to_native((320.0, 270.0), tile_offsets[tile])
    half_x, half_y = math.cos(angle) * CONTROL_LENGTH / 2, math.sin(angle) * CONTROL_LENGTH / 2
    return tile, Band((centre[0] - half_x, centre[1] - half_y), (centre[0] + half_x, centre[1] + half_y))


def opaque_order(context_keys: list[str]) -> list[str]:
    """Return the seed-388 opaque presentation order for exactly 30 control cards."""
    if len(context_keys) != CONTROL_COUNT or len(set(context_keys)) != CONTROL_COUNT:
        raise ValueError("opaque order needs 30 unique control keys")
    ordered = list(context_keys)
    random.Random(388).shuffle(ordered)
    return ordered


def render_control_tile(tile_image, native_band: Band, tile_offset: Point):
    """Draw the frozen black-underlay and white finite band on a copied native tile."""
    import cv2

    local = Band(native_to_tile(native_band.first, tile_offset), native_to_tile(native_band.second, tile_offset))
    image = tile_image.copy()
    endpoints = tuple(tuple(int(round(value)) for value in point) for point in (local.first, local.second))
    cv2.line(image, endpoints[0], endpoints[1], (0, 0, 0), CONTROL_BLACK_PX, cv2.LINE_AA)
    cv2.line(image, endpoints[0], endpoints[1], (255, 255, 255), CONTROL_WHITE_PX, cv2.LINE_AA)
    return image


def selected_indices(size: int = 49, count: int = CONTROL_COUNT) -> list[int]:
    """Return the sealed G388 even-sample positions without substitutions."""
    if size != 49 or count != CONTROL_COUNT:
        raise ValueError("G388 selection is fixed at 49 retained contexts and 30 selections")
    indices = [math.floor(index * 48 / 29 + 0.5) for index in range(count)]
    if len(set(indices)) != count or indices[0] != 0 or indices[-1] != 48:
        raise ValueError("sealed selection is not unique and inclusive")
    return indices


def select_contexts(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort retained contexts by the sealed source order and select all 30 keys."""
    if len(rows) != 49:
        raise ValueError("expected exactly 49 retained native contexts")
    ordered = sorted(rows, key=lambda row: (row["video_id"], row["section_id"], int(row["frame_order"])))
    return [ordered[index] for index in selected_indices()]


def literal_sha256(path: Path) -> str:
    """Hash literal bytes, deliberately without newline normalization."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _projection(point: Point, line: Band) -> tuple[float, float]:
    dx, dy = line.vector()
    squared = dx * dx + dy * dy
    if squared == 0:
        raise ValueError("a line needs two distinct points")
    rx, ry = point[0] - line.first[0], point[1] - line.first[1]
    position = (rx * dx + ry * dy) / squared
    perpendicular = abs(rx * dy - ry * dx) / math.sqrt(squared)
    return position, perpendicular


def point_on_finite_band(point: Point, truth: Band, tolerance: float = POINT_TOLERANCE) -> bool:
    """Require a point to project inside a finite band and meet lateral tolerance."""
    position, perpendicular = _projection(point, truth)
    return 0.0 <= position <= 1.0 and perpendicular <= tolerance


def tile_to_native(point: Point, offset: Point) -> Point:
    """Translate a displayed native-resolution tile point by its recorded integer offset."""
    return point[0] + offset[0], point[1] + offset[1]


def native_to_tile(point: Point, offset: Point) -> Point:
    """Invert a tile offset without rescaling either native coordinate."""
    return point[0] - offset[0], point[1] - offset[1]


def fragment_valid(fragment: Fragment) -> bool:
    """Validate span and an independently placed, interior third point."""
    if fragment.family not in FAMILIES or fragment.family == "UNKNOWN":
        return False
    line = fragment.line()
    if line.length() < MIN_SPAN:
        return False
    position, perpendicular = _projection(fragment.third, line)
    return 0.0 < position < 1.0 and perpendicular <= POINT_TOLERANCE


def control_passes(truth: Band, points: tuple[Point, Point, Point] | None) -> bool:
    """Assess one rater's full three-point known-band response."""
    if points is None or not all(point_on_finite_band(point, truth) for point in points):
        return False
    if math.dist(points[0], points[1]) < MIN_SPAN:
        return False
    position, _perpendicular = _projection(points[2], truth)
    return 0.0 < position < 1.0 and points[2] not in points[:2]


def controls_qualify(rows: list[dict[str, object]]) -> dict[str, object]:
    """Apply the two-rater G388 control bar before real scoring is permitted."""
    keys = [str(row["context_key"]) for row in rows]
    if len(rows) != CONTROL_COUNT or len(set(keys)) != CONTROL_COUNT:
        raise ValueError("all 30 unique control contexts are required")
    passed = []
    for row in rows:
        truth = row["truth"]
        if not isinstance(truth, Band):
            raise ValueError("control truth must be a Band")
        both = control_passes(truth, row.get("rater_a")) and control_passes(truth, row.get("rater_b"))
        passed.append(bool(both))
    return {"controls": len(rows), "passed": sum(passed), "bar": CONTROL_BAR,
            "qualified": sum(passed) >= CONTROL_BAR, "per_context": passed}


def _distance_to_line(point: Point, line: Band) -> float:
    return _projection(point, line)[1]


def symmetric_line_distance(left: Fragment, right: Fragment) -> float:
    """Average each observed endpoint's distance to the other infinite line."""
    distances = [_distance_to_line(point, right.line()) for point in (left.first, left.second)]
    distances += [_distance_to_line(point, left.line()) for point in (right.first, right.second)]
    return sum(distances) / len(distances)


def pair_fragments(left: list[Fragment], right: list[Fragment]) -> list[tuple[Fragment, Fragment]]:
    """Pair only same tile/family fragments once by stable smallest line distance."""
    candidates = []
    for left_index, first in enumerate(left):
        if not fragment_valid(first):
            continue
        for right_index, second in enumerate(right):
            if (first.tile, first.family) != (second.tile, second.family) or not fragment_valid(second):
                continue
            candidates.append((symmetric_line_distance(first, second), left_index, right_index, first, second))
    used_left, used_right, pairs = set(), set(), []
    for distance, left_index, right_index, first, second in sorted(candidates, key=lambda item: item[:3]):
        all_points = (first.first, first.second, first.third, second.first, second.second, second.third)
        if left_index not in used_left and right_index not in used_right and all(
                _distance_to_line(point, second.line()) <= PAIR_TOLERANCE for point in all_points[:3]) and all(
                _distance_to_line(point, first.line()) <= PAIR_TOLERANCE for point in all_points[3:]):
            used_left.add(left_index); used_right.add(right_index); pairs.append((first, second))
    return pairs


def audit_pair(pair: tuple[Fragment, Fragment], paint_distance: Callable[[Point], float]) -> bool:
    """Apply an isolated nine-point native-paint audit to one paired fragment."""
    for fragment in pair:
        line = fragment.line()
        points = [(line.first[0] + index * (line.second[0] - line.first[0]) / (AUDIT_POINTS - 1),
                   line.first[1] + index * (line.second[1] - line.first[1]) / (AUDIT_POINTS - 1))
                  for index in range(AUDIT_POINTS)]
        if sum(paint_distance(point) <= POINT_TOLERANCE for point in points) < AUDIT_REQUIRED:
            return False
    return True


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def premise_receipt(states: Path, selection: Path, marking_only: Path, visibility: Path,
                    controls: Path, per_frame: Path) -> dict[str, object]:
    """Produce a receipt for the G388 binding condition; schema gaps fail closed.

    Columns follow the landed G387 tables (census/control_results/per_frame/visibility),
    not the placeholder names used during preparation; every bar value is unchanged.
    """
    state_rows, selection_rows = _read_csv(states), _read_csv(selection)
    visibility_rows, control_rows, frame_rows = _read_csv(visibility), _read_csv(controls), _read_csv(per_frame)
    payload = json.loads(marking_only.read_text(encoding="utf-8"))
    retained = [row for row in state_rows if row.get("retained", "").upper() in {"1", "TRUE", "RETAINED"}]
    ready = [row for row in retained if row.get("status", "").upper() == "READY"]
    passed = sum(row.get("pass", "").upper() in {"1", "TRUE", "YES", "PASS"} for row in control_rows)
    localized = sum(str(row.get("localized", "")).strip() in {"1", "TRUE", "YES", "PASS"} for row in frame_rows)
    values = [row.get("adjudicator_visibility", "") for row in visibility_rows]
    strokes = [stroke for frame in payload.get("frames", []) for stroke in frame.get("strokes", [])]
    native = {(row["frame_key"], row["native_sha256"], row["width"], row["height"]) for row in ready}
    receipt = {"states": len(state_rows), "retained": len(retained), "native_ready": len(ready),
               "native_identity_rows": len(native), "marking_only_strokes": len(strokes),
               "controls_passed": passed, "controls_denominator": len(control_rows),
               "real_localized": localized, "real_denominator": len(frame_rows),
               "selected": len(selection_rows),
               "visibility": {value: values.count(value) for value in sorted(set(values))},
               "selection_sha256": literal_sha256(selection)}
    receipt["holds"] = (receipt["states"] == 60 and receipt["retained"] == 49 and
                        receipt["native_ready"] == 49 and receipt["native_identity_rows"] == 49 and
                        receipt["marking_only_strokes"] == 0 and passed == 19 and localized == 1 and
                        receipt["selected"] == 30 and
                        receipt["visibility"] == {"NO": 6, "UNKNOWN": 2, "YES": 22})
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    premise = subparsers.add_parser("premise")
    for name in ("states", "selection", "marking_only", "visibility", "controls", "per_frame"):
        premise.add_argument("--" + name.replace("_", "-"), type=Path, required=True)
    premise.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = premise_receipt(args.states, args.selection, args.marking_only, args.visibility,
                              args.controls, args.per_frame)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["holds"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
