"""Pure presentation-time stop mechanics for the G408 proposed contract.

These helpers never open a video or invoke a production route.  A finisher
supplies sealed decoded PTS schedules and may serialize their receipts.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Iterable


DEFAULT_DURATION_SECONDS = 100.0


@dataclass(frozen=True)
class StopReceipt:
    """One immutable schedule replay receipt."""

    admitted_indices: tuple[int, ...]
    deadline: float | None
    first_boundary_index: int | None
    first_boundary_pts: float | None
    last_admitted_pts: float | None
    reason: str
    stride_work_count: int
    unknown_reason: str | None

    def record(self) -> dict[str, object]:
        """Return an additive, JSON-ready receipt."""
        return asdict(self)


def _valid(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def replay_pts_stop(
    pts: Iterable[float | None],
    *,
    start_index: int = 0,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    explicit_frame_cap: int | None = None,
) -> StopReceipt:
    """Replay PTS admission before any stride or detector operation.

    The first valid PTS at ``start_index`` establishes ``t0``.  Values at the
    deadline are boundary records, not admitted work.  Duplicates retain order;
    missing, nonfinite, and backwards timestamps are explicit UNKNOWN results.
    """
    values = list(pts)
    if start_index < 0 or start_index >= len(values):
        return StopReceipt((), None, None, None, None, "EOF_SHORT", 0,
                           "start_outside_schedule")
    if duration_seconds <= 0 or not math.isfinite(duration_seconds):
        return StopReceipt((), None, None, None, None, "UNKNOWN", 0,
                           "invalid_duration")
    t0 = values[start_index]
    if not _valid(t0):
        return StopReceipt((), None, None, None, None, "UNKNOWN", 0,
                           "invalid_start_pts")
    deadline = float(t0) + duration_seconds
    admitted: list[int] = []
    previous: float | None = None
    for index in range(start_index, len(values)):
        if explicit_frame_cap is not None and len(admitted) >= explicit_frame_cap:
            return StopReceipt(tuple(admitted), deadline, None, None,
                               _last(values, admitted), "FRAME_CAP", len(admitted),
                               None)
        value = values[index]
        if not _valid(value):
            return StopReceipt(tuple(admitted), deadline, None, None,
                               _last(values, admitted), "UNKNOWN", len(admitted),
                               "missing_or_nonfinite_pts")
        point = float(value)
        if previous is not None and point < previous:
            return StopReceipt(tuple(admitted), deadline, None, None,
                               _last(values, admitted), "UNKNOWN", len(admitted),
                               "backwards_pts")
        previous = point
        if point >= deadline:
            return StopReceipt(tuple(admitted), deadline, index, point,
                               _last(values, admitted), "DEADLINE", len(admitted),
                               None)
        admitted.append(index)
    return StopReceipt(tuple(admitted), deadline, None, None,
                       _last(values, admitted), "EOF_SHORT", len(admitted), None)


def replay_frame_cap(pts: Iterable[float | None], *, frame_cap: int,
                     start_index: int = 0) -> StopReceipt:
    """Replay a pure frame-count cap (the legacy and G401 arms).

    No deadline exists for these arms, so ``deadline`` stays ``None`` and the
    termination reason is ``FRAME_CAP`` or ``EOF_SHORT``.
    """
    values = list(pts)
    admitted = [index for index in range(start_index,
                                         min(len(values), start_index + frame_cap))
                if _valid(values[index])]
    capped = start_index + frame_cap <= len(values)
    boundary = start_index + frame_cap if capped else None
    boundary_pts = None
    if boundary is not None and _valid(values[boundary]):
        boundary_pts = float(values[boundary])
    return StopReceipt(tuple(admitted), None, boundary, boundary_pts,
                       _last(values, admitted),
                       "FRAME_CAP" if capped else "EOF_SHORT",
                       len(admitted), None)


def replay_pts_prefetch(pts: Iterable[float | None], *, stride: int) -> StopReceipt:
    """Model the proposed prefetcher: validate every frame before stride skip."""
    values = list(pts)
    if stride <= 0:
        raise ValueError("stride must be positive")
    admitted: list[int] = []
    previous: float | None = None
    t0: float | None = None
    deadline: float | None = None
    for index, value in enumerate(values):
        if not _valid(value):
            return StopReceipt(tuple(admitted), deadline, None, None,
                               _last(values, admitted), "UNKNOWN",
                               len(admitted), "missing_or_nonfinite_pts")
        point = float(value)
        if previous is not None and point < previous:
            return StopReceipt(tuple(admitted), deadline, None, None,
                               _last(values, admitted), "UNKNOWN",
                               len(admitted), "backwards_pts")
        previous = point
        if t0 is None:
            t0, deadline = point, point + DEFAULT_DURATION_SECONDS
        if point >= deadline:
            return StopReceipt(tuple(admitted), deadline, index, point,
                               _last(values, admitted), "DEADLINE",
                               len(admitted), None)
        if index % stride:
            continue
        admitted.append(index)
    return StopReceipt(tuple(admitted), deadline, None, None,
                       _last(values, admitted), "EOF_SHORT", len(admitted), None)


def _last(values: list[float | None], indices: list[int]) -> float | None:
    return None if not indices else float(values[indices[-1]])


# Sealed 5 x 6 control grid. PREFIX carries the timestamp class, ENDPOINTS the
# frame under test. EXPECTED is enumerated by hand from the contract text, NOT
# produced by replay_pts_stop, so the controls can actually falsify the code.
PREFIX = {"regular": [0.0, 0.5],
          "duplicate": [0.0, 0.5, 0.5],
          "missing": [0.0, 0.5, None],
          "backward": [0.0, 0.5, 0.25],
          "boundary_gap": [0.0, 99.5]}
ENDPOINTS = (("before_start", -1.0), ("at_start", 0.0), ("inside", 50.0),
             ("just_below_deadline", 99.999), ("exact_deadline", 100.0),
             ("above_deadline", 100.5))
_BACK = ("UNKNOWN", [0, 1], "backwards_pts")
_MISS = ("UNKNOWN", [0, 1], "missing_or_nonfinite_pts")
EXPECTED = {
    "regular": {"before_start": _BACK, "at_start": _BACK,
                "inside": ("EOF_SHORT", [0, 1, 2], None),
                "just_below_deadline": ("EOF_SHORT", [0, 1, 2], None),
                "exact_deadline": ("DEADLINE", [0, 1], None),
                "above_deadline": ("DEADLINE", [0, 1], None)},
    "duplicate": {"before_start": ("UNKNOWN", [0, 1, 2], "backwards_pts"),
                  "at_start": ("UNKNOWN", [0, 1, 2], "backwards_pts"),
                  "inside": ("EOF_SHORT", [0, 1, 2, 3], None),
                  "just_below_deadline": ("EOF_SHORT", [0, 1, 2, 3], None),
                  "exact_deadline": ("DEADLINE", [0, 1, 2], None),
                  "above_deadline": ("DEADLINE", [0, 1, 2], None)},
    "missing": {name: _MISS for name, _ in ENDPOINTS},
    "backward": {name: _BACK for name, _ in ENDPOINTS},
    "boundary_gap": {"before_start": _BACK, "at_start": _BACK,
                     "inside": _BACK,
                     "just_below_deadline": ("EOF_SHORT", [0, 1, 2], None),
                     "exact_deadline": ("DEADLINE", [0, 1], None),
                     "above_deadline": ("DEADLINE", [0, 1], None)},
}


def construct_cases() -> list[dict[str, object]]:
    """Return the sealed exhaustive five-by-six G408 schedule controls.

    Each row carries the schedule, the hand-declared expectation, and the
    replayed outcome, so a reader can see the two agree instead of trusting
    that the expectation was derived from the implementation.
    """
    rows: list[dict[str, object]] = []
    for kind, prefix in PREFIX.items():
        for endpoint, offset in ENDPOINTS:
            schedule: list[float | None] = list(prefix) + [offset]
            reason, admitted, unknown = EXPECTED[kind][endpoint]
            receipt = replay_pts_stop(schedule)
            rows.append({"case": "%s__%s" % (kind, endpoint), "kind": kind,
                         "endpoint": endpoint, "endpoint_offset_s": offset,
                         "pts": schedule,
                         "declared_reason": reason,
                         "declared_admitted_indices": admitted,
                         "declared_unknown_reason": unknown,
                         "expected_reason": receipt.reason,
                         "expected_admitted_indices":
                             list(receipt.admitted_indices),
                         "expected_unknown_reason": receipt.unknown_reason,
                         "first_boundary_index": receipt.first_boundary_index,
                         "matches_declared":
                             receipt.reason == reason
                             and list(receipt.admitted_indices) == admitted
                             and receipt.unknown_reason == unknown})
    return rows
