"""Exact-rational endpoint measurement for G411 against the archived decimals.

Nothing here opens media.  `g411_read` supplies retained integer PTS; the
archived float schedules come from the landed G408 directory.  Both are
replayed through the SAME inherited first-excluded extent definition.
"""
from __future__ import annotations

from fractions import Fraction

from scripts.platformkit.tracking import g411_rational as RAT

TARGET = Fraction(100, 1)
LEGACY_FRAME_CAP = 3000


def bar(fps_text: str) -> Fraction:
    """One native interval from the archived validated FPS decimal, exactly."""
    return Fraction(1, 1) / Fraction(fps_text)


def float_schedule_endpoints(pts: list, frame_cap: int | None,
                             interval: str) -> dict:
    """Replay the archived decimal schedule under the sealed mechanics."""
    values = [None if value is None else Fraction(repr(value)) for value in pts]
    return _endpoints(values, frame_cap, Fraction(interval))


def rational_schedule_endpoints(pts: list, base: Fraction, frame_cap: int | None,
                                interval: Fraction) -> dict:
    """Replay the same mechanics on native integer PTS times the time base."""
    values = [None if value is None else value * base for value in pts]
    return _endpoints(values, frame_cap, interval)


def _endpoints(values: list, frame_cap: int | None, interval: Fraction) -> dict:
    """Shared deadline/frame-cap replay; first excluded is the extent endpoint."""
    if not values:
        return _row(values, None, None, [], "EOF_SHORT", interval,
                    "start_outside_schedule")
    if values[0] is None:
        return _unknown("missing_start_pts", values, None, None, (),
                        "invalid_start_pts")
    origin = values[0]
    deadline = origin + TARGET
    previous = None
    admitted: list[int] = []
    for index, value in enumerate(values):
        if frame_cap is not None and len(admitted) >= frame_cap:
            return _row(values, origin, index, admitted, "FRAME_CAP", interval)
        if value is None:
            return _unknown("missing_pts", values, origin, deadline, admitted,
                            "missing_or_nonfinite_pts")
        if previous is not None and value < previous:
            return _unknown("backwards_pts", values, origin, deadline, admitted,
                            "backwards_pts")
        previous = value
        if frame_cap is None and value >= deadline:
            return _row(values, origin, index, admitted, "DEADLINE", interval)
        admitted.append(index)
    return _row(values, origin, None, admitted, "EOF_SHORT", interval)


def _unknown(alias: str, values: list, origin, deadline, admitted: tuple | list,
             parent_reason: str) -> dict:
    """Retain the parent state when malformed PTS ends the replay."""
    last = admitted[-1] if admitted else None
    last_pts = None if last is None else values[last]
    return {"termination_reason": "UNKNOWN", "unknown_reason": parent_reason,
            "unknown_reason_g411": alias,
            "first_excluded_index": None, "first_excluded_pts": None,
            "first_admitted_index": None if not admitted else admitted[0],
            "last_admitted_index": last,
            "last_admitted_pts": last_pts,
            "admitted_frames": len(admitted), "first_boundary_extent": None,
            "last_admitted_extent": None if last_pts is None else last_pts - origin,
            "origin": origin, "deadline": deadline}


def _row(values: list, origin: Fraction | None, excluded: int | None,
          admitted: list[int],
          reason: str, interval: Fraction, unknown_reason: str | None = None) -> dict:
    """Build one endpoint record under the inherited first-excluded definition."""
    if excluded is not None and excluded < len(values):
        first_boundary = values[excluded] - origin
    elif values and origin is not None:
        first_boundary = values[-1] - origin + interval
        excluded = None
    else:
        first_boundary = None
    last = admitted[-1] if admitted else None
    inside = last is not None and 0 <= last < len(values)
    return {"termination_reason": reason, "unknown_reason": unknown_reason,
            "unknown_reason_g411": None,
            "origin": origin,
            "deadline": None if origin is None else origin + TARGET,
            "first_excluded_index": excluded,
            "first_excluded_pts": None if excluded is None else values[excluded],
            "first_admitted_index": admitted[0] if admitted else None,
            "last_admitted_index": last,
            "last_admitted_pts": values[last] if inside else None,
            "admitted_frames": len(admitted),
            "first_boundary_extent": first_boundary,
            "last_admitted_extent": (values[last] - origin) if inside else None}


def within_bar(extent, fps_text: str):
    """Inherited bar, byte-identical: abs(extent - 100) <= 1/validated_fps."""
    if extent is None:
        return None
    return abs(extent - TARGET) <= bar(fps_text)


def contained(extent):
    """Temporal containment: the first-excluded endpoint reaches the target."""
    if extent is None:
        return None
    return extent >= TARGET


def as_text(value, places: int = 12) -> str:
    """Render an exact rational at `places` decimals for the eye only.

    The `_exact` numerator/denominator columns stay authoritative; this render
    is round-half-even so it never reads as a discrepancy against an archived
    six-decimal value that was rounded the same way.
    """
    return rounded_text(value, places)


def rounded_text(value, places: int = 6) -> str:
    """Render an exact rational with the archived six-decimal rounding rule."""
    if value is None:
        return ""
    scaled = round(value * 10 ** places)
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled)).rjust(places + 1, "0")
    return "%s%s.%s" % (sign, digits[:-places], digits[-places:])


def exact_text(value) -> str:
    """Render the exact `numerator/denominator` form."""
    return "" if value is None else "%d/%d" % (value.numerator, value.denominator)


def anomalies(pts: list) -> list:
    """Classify duplicate, backwards, missing and off-grid integer steps."""
    rows: list = []
    steps: dict = {}
    for index in range(1, len(pts)):
        left, right = pts[index - 1], pts[index]
        if left is None or right is None:
            rows.append({"frame_index": index, "kind": "missing_pts", "step": ""})
            continue
        step = right - left
        steps[step] = steps.get(step, 0) + 1
        if step == 0:
            rows.append({"frame_index": index, "kind": "duplicate_pts", "step": step})
        elif step < 0:
            rows.append({"frame_index": index, "kind": "backwards_pts", "step": step})
    if steps:
        modal = modal_step(pts)
        for index in range(1, len(pts)):
            left, right = pts[index - 1], pts[index]
            if left is None or right is None:
                continue
            step = right - left
            # One time-base unit of jitter is the exact quantization of a
            # non-integer frame rate, not an anomaly; anything larger is.
            if step > 0 and abs(step - modal) > 1:
                rows.append({"frame_index": index, "kind": "off_grid_step",
                             "step": step})
    return sorted(rows, key=lambda row: (row["frame_index"], row["kind"]))


def modal_step(pts: list) -> int:
    """Return the most common positive integer PTS step in a stream."""
    steps: dict = {}
    for index in range(1, len(pts)):
        left, right = pts[index - 1], pts[index]
        if left is None or right is None:
            continue
        steps[right - left] = steps.get(right - left, 0) + 1
    return max(steps.items(), key=lambda item: item[1])[0] if steps else 0


CONSTRUCT_KINDS = ("at_deadline", "one_unit_below", "one_unit_above", "duplicate",
                   "missing", "backwards", "dropped_deadline_neighbor",
                   "skipped_by_stride")


def construct_cases(base: str, unit_per_frame: int) -> list:
    """Enumerate sealed boundary constructs for one time-base/rate pair.

    Expectations are declared from the contract text, then compared with the
    replay result, so a wrong implementation fails instead of defining truth.
    """
    tick = RAT.time_base(base)
    at = int(TARGET / tick)
    step = unit_per_frame
    plans = {
        "at_deadline": ([0, step, at], "DEADLINE", 2),
        "one_unit_below": ([0, step, at - 1], "EOF_SHORT", None),
        "one_unit_above": ([0, step, at + 1], "DEADLINE", 2),
        "duplicate": ([0, step, step, at], "DEADLINE", 3),
        "missing": ([0, step, None, at], "UNKNOWN", None),
        "backwards": ([0, step, step - 1, at], "UNKNOWN", None),
        "dropped_deadline_neighbor": ([0, step, at + step], "DEADLINE", 2),
        "skipped_by_stride": ([0, step, at], "DEADLINE", 2),
    }
    rows = []
    for kind in CONSTRUCT_KINDS:
        schedule, declared, declared_index = plans[kind]
        stride = 2 if kind == "skipped_by_stride" else 1
        receipt = RAT.replay_integer_pts(schedule, base, stride=stride)
        observed_index = receipt.first_excluded_index
        rows.append({
            "time_base": base, "unit_per_frame": unit_per_frame, "case": kind,
            "schedule": " ".join("NA" if item is None else str(item)
                                 for item in schedule),
            "declared_reason": declared, "observed_reason": receipt.reason,
            "declared_first_excluded_index": "" if declared_index is None
            else declared_index,
            "observed_first_excluded_index": "" if observed_index is None
            else observed_index,
            "matches_declared": bool(
                receipt.reason == declared
                and (declared_index is None or observed_index == declared_index))})
    return rows
