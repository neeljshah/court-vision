"""G392 geometry checks for separate rater qualification and later pair audit."""
from __future__ import annotations

import math
from dataclasses import dataclass

CONTROL_COUNT = 30
CONTROL_BAR = 27
POINT_TOLERANCE = 3.0
PAIR_TOLERANCE = 6.0
MIN_SPAN = 60.0
AUDIT_POINTS = 9
AUDIT_REQUIRED = 8
Point = tuple[float, float]


@dataclass(frozen=True)
class Band:
    """A finite native-pixel centreline."""

    first: Point
    second: Point

    def length(self) -> float:
        return math.dist(self.first, self.second)


@dataclass(frozen=True)
class Fragment:
    """One independent three-point paint observation."""

    tile: int
    family: str
    first: Point
    second: Point
    third: Point
    fragment_id: str

    def line(self) -> Band:
        return Band(self.first, self.second)


def tile_to_native(point: Point, offset: Point) -> Point:
    """Apply the explicit integer tile offset without rescaling."""
    return point[0] + offset[0], point[1] + offset[1]


def _projection(point: Point, band: Band) -> tuple[float, float]:
    dx, dy = band.second[0] - band.first[0], band.second[1] - band.first[1]
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return float("inf"), float("inf")
    position = ((point[0] - band.first[0]) * dx + (point[1] - band.first[1]) * dy) / length_sq
    perpendicular = abs((point[0] - band.first[0]) * dy - (point[1] - band.first[1]) * dx) / math.sqrt(length_sq)
    return position, perpendicular


def control_passes(truth: Band, points: tuple[Point, Point, Point] | None) -> bool:
    """Check all finite-band, span, and independent-third-point clauses."""
    if points is None or truth.length() < MIN_SPAN or math.dist(points[0], points[1]) < MIN_SPAN:
        return False
    positions = [_projection(point, truth) for point in points]
    return (all(0.0 <= place <= 1.0 and distance <= POINT_TOLERANCE for place, distance in positions)
            and 0.0 < positions[2][0] < 1.0 and points[2] not in points[:2])


def qualification(rows: list[dict[str, object]], raters: tuple[str, str] = ("terra", "sol")) -> dict[str, object]:
    """Apply per-rater and joint 27-of-30 bars before real dispatch."""
    if len(rows) != CONTROL_COUNT or len({str(row["control_id"]) for row in rows}) != CONTROL_COUNT:
        raise ValueError("qualification requires 30 unique controls")
    passes = {rater: [] for rater in raters}
    for row in rows:
        truth = row.get("truth")
        if not isinstance(truth, Band):
            raise ValueError("each control requires finite Band truth")
        for rater in raters:
            passes[rater].append(control_passes(truth, row.get(rater)))
    totals = {rater: sum(values) for rater, values in passes.items()}
    joint = sum(all(passes[rater][index] for rater in raters) for index in range(CONTROL_COUNT))
    return {"controls": CONTROL_COUNT, "bar": CONTROL_BAR, "per_rater": totals, "joint": joint,
            "qualified": all(totals[rater] >= CONTROL_BAR for rater in raters) and joint >= CONTROL_BAR,
            "real_dispatch_allowed": all(totals[rater] >= CONTROL_BAR for rater in raters) and joint >= CONTROL_BAR}


def _distance(point: Point, band: Band) -> float:
    return _projection(point, band)[1]


def fragment_valid(fragment: Fragment) -> bool:
    """Validate the required span and independent interior third point."""
    position, distance = _projection(fragment.third, fragment.line())
    return fragment.line().length() >= MIN_SPAN and 0.0 < position < 1.0 and distance <= POINT_TOLERANCE


def symmetric_line_distance(left: Fragment, right: Fragment) -> float:
    """Return the stable symmetric infinite-line distance for pairing."""
    values = [_distance(point, right.line()) for point in (left.first, left.second, left.third)]
    values += [_distance(point, left.line()) for point in (right.first, right.second, right.third)]
    return sum(values) / len(values)


def pair_fragments(left: list[Fragment], right: list[Fragment]) -> list[tuple[Fragment, Fragment]]:
    """Pair same tile/family fragments once with stable distance ties."""
    candidates = []
    for left_index, first in enumerate(left):
        for right_index, second in enumerate(right):
            if (first.tile, first.family) == (second.tile, second.family) and fragment_valid(first) and fragment_valid(second):
                candidates.append((symmetric_line_distance(first, second), left_index, right_index, first, second))
    used_left, used_right, pairs = set(), set(), []
    for _distance_value, left_index, right_index, first, second in sorted(candidates, key=lambda row: row[:3]):
        points = (first.first, first.second, first.third, second.first, second.second, second.third)
        compatible = all(_distance(point, second.line()) <= PAIR_TOLERANCE for point in points[:3])
        compatible = compatible and all(_distance(point, first.line()) <= PAIR_TOLERANCE for point in points[3:])
        if compatible and left_index not in used_left and right_index not in used_right:
            used_left.add(left_index); used_right.add(right_index); pairs.append((first, second))
    return pairs


def audit_pair(pair: tuple[Fragment, Fragment], paint_distance) -> bool:
    """Audit one pair only with two independent nine-point series."""
    for fragment in pair:
        line = fragment.line()
        points = [(line.first[0] + index * (line.second[0] - line.first[0]) / (AUDIT_POINTS - 1),
                   line.first[1] + index * (line.second[1] - line.first[1]) / (AUDIT_POINTS - 1))
                  for index in range(AUDIT_POINTS)]
        if sum(paint_distance(point) <= POINT_TOLERANCE for point in points) < AUDIT_REQUIRED:
            return False
    return True
