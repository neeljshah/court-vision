"""Exact integer-PTS mechanics prepared for G411 measurement.

These pure helpers do not open media, score an outcome, or invoke production
code.  The finisher supplies retained integer PTS records and a stream time
base after the sealed prerequisite binding has been reproduced.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


HUNDRED_SECONDS = Fraction(100, 1)


def time_base(value: str | Fraction) -> Fraction:
    """Parse a native stream time base without decimal conversion."""
    if isinstance(value, Fraction):
        return value
    numerator, denominator = value.split("/", 1)
    base = Fraction(int(numerator), int(denominator))
    if base <= 0:
        raise ValueError("time base must be positive")
    return base


def pts_to_seconds(pts: int, base: str | Fraction) -> Fraction:
    """Return the exact rational time of an integer PTS."""
    return pts * time_base(base)


def decimal_text_to_fraction(value: str) -> Fraction:
    """Preserve an archived decimal serialization exactly as text."""
    return Fraction(value)


@dataclass(frozen=True)
class RationalStop:
    """Result of one exact schedule replay before stride filtering."""

    admitted_indices: tuple[int, ...]
    last_admitted_index: int | None
    first_excluded_index: int | None
    origin: Fraction | None
    deadline: Fraction | None
    reason: str
    unknown_reason: str | None


def replay_integer_pts(
    values: Iterable[int | None], base: str | Fraction, *, stride: int = 1,
    frame_cap: int | None = None,
) -> RationalStop:
    """Replay exact deadline admission, validating all PTS before stride."""
    if stride <= 0:
        raise ValueError("stride must be positive")
    schedule = list(values)
    if not schedule or schedule[0] is None:
        return RationalStop((), None, None, None, None, "UNKNOWN",
                            "missing_start_pts")
    unit = time_base(base)
    origin = pts_to_seconds(schedule[0], unit)
    deadline = origin + HUNDRED_SECONDS
    admitted: list[int] = []
    previous: int | None = None
    for index, value in enumerate(schedule):
        if frame_cap is not None and len(admitted) >= frame_cap:
            return RationalStop(tuple(admitted), admitted[-1] if admitted else None,
                                None, origin, deadline, "FRAME_CAP", None)
        if value is None:
            return RationalStop(tuple(admitted), admitted[-1] if admitted else None,
                                None, origin, deadline, "UNKNOWN",
                                "missing_pts")
        if previous is not None and value < previous:
            return RationalStop(tuple(admitted), admitted[-1] if admitted else None,
                                None, origin, deadline, "UNKNOWN",
                                "backwards_pts")
        previous = value
        if pts_to_seconds(value, unit) >= deadline:
            return RationalStop(tuple(admitted), admitted[-1] if admitted else None,
                                index, origin, deadline, "DEADLINE", None)
        if index % stride == 0:
            admitted.append(index)
    return RationalStop(tuple(admitted), admitted[-1] if admitted else None,
                        None, origin, deadline, "EOF_SHORT", None)


def within_inherited_bar(first_boundary: Fraction, fps: str | Fraction) -> bool:
    """Apply the unmodified one-native-interval G408 extent bar exactly."""
    return abs(first_boundary - HUNDRED_SECONDS) <= Fraction(1, 1) / time_base(fps)
