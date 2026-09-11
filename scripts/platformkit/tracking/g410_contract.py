"""Pure coordinate and serialization checks for the G410 observer handoff."""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor, isfinite
from typing import Iterable, Sequence

CLASSIFICATIONS = frozenset({"CONSISTENT_BY_CONTRACT", "FRAME_MISMATCH",
                             "BRANCH_MISMATCH", "STALE_BOX", "UNKNOWN"})


@dataclass(frozen=True)
class Projection:
    """A homogeneous projection together with the input coordinate frame."""

    x: float
    y: float
    frame: str


def box_foot(box: Sequence[float]) -> tuple[float, float]:
    """Return the center-bottom image foot for a nondegenerate xyxy box."""
    if len(box) != 4:
        raise ValueError("box-must-have-four-values")
    x1, y1, x2, y2 = (float(value) for value in box)
    if not all(isfinite(value) for value in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
        raise ValueError("box-must-be-finite-nondegenerate")
    return ((x1 + x2) / 2.0, y2)


def project_homogeneous(matrix: Sequence[Sequence[float]], point: Sequence[float],
                        frame: str) -> Projection:
    """Project one image point through a declared 3x3 homogeneous matrix."""
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix) or len(point) != 2:
        raise ValueError("projection-shape-invalid")
    x, y = (float(value) for value in point)
    flat = [float(value) for row in matrix for value in row]
    if not all(isfinite(value) for value in [x, y, *flat]):
        raise ValueError("projection-nonfinite")
    h0 = flat[0] * x + flat[1] * y + flat[2]
    h1 = flat[3] * x + flat[4] * y + flat[5]
    h2 = flat[6] * x + flat[7] * y + flat[8]
    if h2 == 0.0:
        raise ValueError("projection-zero-homogeneous-scale")
    return Projection(h0 / h2, h1 / h2, frame)


def native_to_cropped(point: Sequence[float], crop_origin: Sequence[float]) -> tuple[float, float]:
    """Translate a native image point into its declared cropped-pixel frame."""
    if len(point) != 2 or len(crop_origin) != 2:
        raise ValueError("coordinate-frame-shape-invalid")
    return (float(point[0]) - float(crop_origin[0]), float(point[1]) - float(crop_origin[1]))


def serialize_coordinate(value: float, rounding: str) -> float | int:
    """Apply only the writer rounding operation explicitly recorded by observation."""
    number = float(value)
    if not isfinite(number):
        raise ValueError("coordinate-nonfinite")
    if rounding == "NONE":
        return number
    if rounding == "FLOOR":
        return floor(number)
    if rounding == "CEIL":
        return ceil(number)
    if rounding == "ROUND_HALF_UP":
        return floor(number + 0.5) if number >= 0 else ceil(number - 0.5)
    raise ValueError("rounding-not-declared")


def exact_values_equal(left: Iterable[object], right: Iterable[object]) -> bool:
    """Compare serialized values without a tolerance chosen after observation."""
    return tuple(str(value) for value in left) == tuple(str(value) for value in right)


def classify(observed_branch: str | None, expected_branch: str | None,
             observed_position: Sequence[object] | None,
             expected_position: Sequence[object] | None,
             observed_box: Sequence[object] | None,
             expected_box: Sequence[object] | None,
             retained_position_age: int | None) -> str:
    """Classify one observed invocation without turning retained points into defects."""
    if (not observed_branch or not expected_branch or observed_position is None or
            expected_position is None or observed_box is None or expected_box is None):
        return "UNKNOWN"
    if observed_branch != expected_branch:
        return "BRANCH_MISMATCH"
    if not exact_values_equal(observed_box, expected_box):
        return "FRAME_MISMATCH"
    if (retained_position_age is not None and retained_position_age > 0 and
            not exact_values_equal(observed_position, expected_position)):
        return "STALE_BOX"
    return "CONSISTENT_BY_CONTRACT" if exact_values_equal(
        observed_position, expected_position) else "FRAME_MISMATCH"
