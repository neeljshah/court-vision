"""Frozen geometry and planned-state helpers for G399."""
from __future__ import annotations

import math
from dataclasses import dataclass

POINT_TOLERANCE = 3.0
PAIR_TOLERANCE = 6.0
MIN_SPAN = 60.0
AUDIT_POINTS = 9
AUDIT_REQUIRED = 8
RATERS = ("astra", "sol")

Point = tuple[float, float]


@dataclass(frozen=True)
class Fragment:
    """One three-point native fragment supplied by an independent rater."""

    rater: str
    tile: int
    family: str
    first: Point
    second: Point
    third: Point
    fragment_id: str


def planned_targets(first_pts: float, last_pts: float, decoded_pts: list[float]) -> tuple[float, float]:
    """Choose one-third and two-thirds targets, with earlier PTS breaking ties."""
    if not decoded_pts or first_pts >= last_pts:
        raise ValueError("usable PTS span requires ordered decoded PTS")
    ordered = sorted(set(decoded_pts))
    targets = (first_pts + (last_pts - first_pts) / 3.0,
               first_pts + 2.0 * (last_pts - first_pts) / 3.0)
    chosen = tuple(min(ordered, key=lambda value: (abs(value - target), value)) for target in targets)
    if chosen[0] == chosen[1]:
        raise ValueError("duplicate planned PTS")
    return chosen


def _projection(point: Point, first: Point, second: Point) -> tuple[float, float]:
    dx, dy = second[0] - first[0], second[1] - first[1]
    norm = dx * dx + dy * dy
    if norm == 0:
        return float("inf"), float("inf")
    position = ((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / norm
    distance = abs((point[0] - first[0]) * dy - (point[1] - first[1]) * dx) / math.sqrt(norm)
    return position, distance


def valid_fragment(fragment: Fragment) -> bool:
    """Apply the finite native fragment requirements before pairing."""
    if math.dist(fragment.first, fragment.second) < MIN_SPAN:
        return False
    position, distance = _projection(fragment.third, fragment.first, fragment.second)
    return 0.0 < position < 1.0 and distance <= POINT_TOLERANCE


def pair_compatible(left: Fragment, right: Fragment) -> bool:
    """Require distinct raters, same tile/family, and symmetric 6 px agreement."""
    if (left.rater == right.rater or left.tile != right.tile or left.family != right.family
            or not valid_fragment(left) or not valid_fragment(right)):
        return False
    left_to_right = (_projection(point, right.first, right.second)[1]
                     for point in (left.first, left.second, left.third))
    right_to_left = (_projection(point, left.first, left.second)[1]
                     for point in (right.first, right.second, right.third))
    return all(value <= PAIR_TOLERANCE for value in left_to_right) and all(value <= PAIR_TOLERANCE for value in right_to_left)


def audit_pair(token: str, pair: tuple[Fragment, Fragment], visible_distance, used: set[str]) -> bool:
    """Run the independent nine-point audit once for each candidate pair."""
    if token in used or not pair_compatible(*pair):
        return False
    used.add(token)
    for fragment in pair:
        points = [(fragment.first[0] + index * (fragment.second[0] - fragment.first[0]) / 8.0,
                   fragment.first[1] + index * (fragment.second[1] - fragment.first[1]) / 8.0)
                  for index in range(AUDIT_POINTS)]
        if sum(visible_distance(point) <= POINT_TOLERANCE for point in points) < AUDIT_REQUIRED:
            return False
    return True
