"""G396 fixed geometry and qualification gates for sol and ASTRA."""
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
RATERS = ("sol", "astra")
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
    """A three-point observation from one rater."""

    tile: int
    family: str
    first: Point
    second: Point
    third: Point
    fragment_id: str

    def line(self) -> Band:
        return Band(self.first, self.second)


def _projection(point: Point, band: Band) -> tuple[float, float]:
    dx, dy = band.second[0] - band.first[0], band.second[1] - band.first[1]
    norm = dx * dx + dy * dy
    if norm == 0:
        return float("inf"), float("inf")
    position = ((point[0] - band.first[0]) * dx + (point[1] - band.first[1]) * dy) / norm
    distance = abs((point[0] - band.first[0]) * dy - (point[1] - band.first[1]) * dx) / math.sqrt(norm)
    return position, distance


def control_passes(truth: Band, points: tuple[Point, Point, Point] | None) -> bool:
    """Enforce every finite-band, span, and third-point clause."""
    if points is None or truth.length() < MIN_SPAN or math.dist(points[0], points[1]) < MIN_SPAN:
        return False
    checks = [_projection(point, truth) for point in points]
    return (all(0.0 <= position <= 1.0 and distance <= POINT_TOLERANCE for position, distance in checks)
            and 0.0 < checks[2][0] < 1.0 and points[2] not in points[:2])


def qualification(rows: list[dict[str, object]]) -> dict[str, object]:
    """Return the fixed same-control gate before any real dispatch."""
    if len(rows) != CONTROL_COUNT or len({str(row["control_id"]) for row in rows}) != CONTROL_COUNT:
        raise ValueError("qualification requires 30 unique controls")
    passed = {rater: [] for rater in RATERS}
    for row in rows:
        truth = row.get("truth")
        if not isinstance(truth, Band):
            raise ValueError("each control requires finite Band truth")
        for rater in RATERS:
            passed[rater].append(control_passes(truth, row.get(rater)))
    totals = {rater: sum(values) for rater, values in passed.items()}
    joint = sum(all(passed[rater][index] for rater in RATERS) for index in range(CONTROL_COUNT))
    allowed = all(totals[rater] >= CONTROL_BAR for rater in RATERS) and joint >= CONTROL_BAR
    return {"controls": CONTROL_COUNT, "bar": CONTROL_BAR, "per_rater": totals,
            "joint": joint, "qualified": allowed, "real_dispatch_allowed": allowed}


def fragment_valid(fragment: Fragment) -> bool:
    """Validate a real-fragment independent third point."""
    position, distance = _projection(fragment.third, fragment.line())
    return fragment.line().length() >= MIN_SPAN and 0.0 < position < 1.0 and distance <= POINT_TOLERANCE


def _line_distance(point: Point, band: Band) -> float:
    return _projection(point, band)[1]


def pair_compatible(left: Fragment, right: Fragment) -> bool:
    """Require same tile/family and all six points within the pair tolerance."""
    if (left.tile, left.family) != (right.tile, right.family) or not fragment_valid(left) or not fragment_valid(right):
        return False
    return (all(_line_distance(point, right.line()) <= PAIR_TOLERANCE for point in (left.first, left.second, left.third))
            and all(_line_distance(point, left.line()) <= PAIR_TOLERANCE for point in (right.first, right.second, right.third)))


def audit_pair(candidate_id: str, pair: tuple[Fragment, Fragment], paint_distance, used: set[str]) -> bool:
    """Audit a candidate once; reusing an audit token is invalid."""
    if candidate_id in used:
        return False
    used.add(candidate_id)
    for fragment in pair:
        line = fragment.line()
        points = [(line.first[0] + index * (line.second[0] - line.first[0]) / (AUDIT_POINTS - 1),
                   line.first[1] + index * (line.second[1] - line.first[1]) / (AUDIT_POINTS - 1))
                  for index in range(AUDIT_POINTS)]
        if sum(paint_distance(point) <= POINT_TOLERANCE for point in points) < AUDIT_REQUIRED:
            return False
    return True
