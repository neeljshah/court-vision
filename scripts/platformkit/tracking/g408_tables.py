"""G408 three-arm stop tables over sealed presentation schedules.

Arm A is the landed 3000 source-frame cap, arm B is G401's
``ceil(100 * validated_fps)`` frame cap, arm C is the proposed elapsed-PTS
stop.  Every arm replays the SAME immutable schedule; nothing here decodes,
rates, or invokes a production route.
"""
from __future__ import annotations

import math

from scripts.platformkit.tracking.g408_stop import (DEFAULT_DURATION_SECONDS,
                                                    replay_frame_cap,
                                                    replay_pts_stop)

LEGACY_FRAME_CAP = 3000
ARMS = ("A_legacy_frame_cap_3000", "B_g401_fps_frame_cap", "C_proposed_pts_stop")

STOP_FIELDS = ["source_name", "arm", "rule", "frame_cap", "read_frames",
               "admitted_frames", "first_admitted_index", "last_admitted_index",
               "last_admitted_pts", "first_excluded_index", "first_excluded_pts",
               "span_s", "deadline_s", "endpoint_gap_s",
               "first_boundary_extent_s",
               "last_admitted_gap_s", "overshoot_s",
               "termination_reason", "unknown_reason", "contained",
               "native_frame_interval_s", "draw_j"]


def _interval(validated_fps: float) -> float:
    return 1.0 / validated_fps if validated_fps else 0.0


def arm_rows(source_name: str, draw_j: int, pts: list[float | None],
             validated_fps: float,
             duration_seconds: float = DEFAULT_DURATION_SECONDS) -> list[dict]:
    """Return one row per arm for a single sealed schedule."""
    fps_cap = int(math.ceil(duration_seconds * validated_fps))
    plans = ((ARMS[0], "frame_cap", LEGACY_FRAME_CAP),
             (ARMS[1], "frame_cap", fps_cap),
             (ARMS[2], "pts_stop", None))
    rows = []
    for arm, rule, cap in plans:
        if rule == "frame_cap":
            receipt = replay_frame_cap(pts, frame_cap=cap)
        else:
            receipt = replay_pts_stop(pts, duration_seconds=duration_seconds)
        rows.append(_row(source_name, draw_j, pts, validated_fps, arm, rule,
                         cap, receipt, duration_seconds))
    return rows


def _row(source_name, draw_j, pts, validated_fps, arm, rule, cap, receipt,
         duration_seconds) -> dict:
    admitted = receipt.admitted_indices
    first_pts = float(pts[admitted[0]]) if admitted else None
    deadline = receipt.deadline
    if deadline is None and first_pts is not None:
        deadline = first_pts + duration_seconds
    span = None
    if admitted and receipt.last_admitted_pts is not None and first_pts is not None:
        span = receipt.last_admitted_pts - first_pts
    # The historical G401 comparison evaluates an unrounded endpoint extent
    # against one native interval.  Its values are deliberately not formatted
    # before the comparison below.  The last-admitted gap is a separate,
    # descriptive containment diagnostic and must not replace that bar.
    first_boundary_extent = None
    if receipt.first_boundary_pts is not None and first_pts is not None:
        first_boundary_extent = receipt.first_boundary_pts - first_pts
    last_admitted_gap = None if span is None else duration_seconds - span
    overshoot = None
    if receipt.first_boundary_pts is not None and first_pts is not None:
        overshoot = (receipt.first_boundary_pts - first_pts) - duration_seconds
    contained = True
    if deadline is not None and receipt.last_admitted_pts is not None:
        contained = receipt.last_admitted_pts < deadline
    return {"source_name": source_name, "arm": arm, "rule": rule,
            "frame_cap": "" if cap is None else cap,
            "read_frames": len(admitted) + (1 if receipt.first_boundary_index
                                            is not None else 0),
            "admitted_frames": len(admitted),
            "first_admitted_index": admitted[0] if admitted else "",
            "last_admitted_index": admitted[-1] if admitted else "",
            "last_admitted_pts": _fmt(receipt.last_admitted_pts),
            "first_excluded_index": _fmt(receipt.first_boundary_index),
            "first_excluded_pts": _fmt(receipt.first_boundary_pts),
            "span_s": _fmt(span), "deadline_s": _fmt(deadline),
            "endpoint_gap_s": _fmt(last_admitted_gap),
            "first_boundary_extent_s": _exact(first_boundary_extent),
            "last_admitted_gap_s": _fmt(last_admitted_gap),
            "overshoot_s": _fmt(overshoot),
            "termination_reason": receipt.reason,
            "unknown_reason": receipt.unknown_reason or "",
            "contained": contained,
            "native_frame_interval_s": _exact(_interval(validated_fps)),
            "draw_j": draw_j}


def _fmt(value) -> object:
    if value is None:
        return ""
    if isinstance(value, float):
        return "%.6f" % value
    return value


def _exact(value) -> object:
    """Serialize an inherited-bar input without rounding it before comparison."""
    if value is None:
        return ""
    return "%.17g" % value


def arm_c_bar(rows: list[dict], interval_slack: float = 1.0) -> dict:
    """Return the inherited unrounded interval bar and descriptive gap count."""
    arm_c = [row for row in rows if row["arm"] == ARMS[2]]
    valid = [row for row in arm_c if row["termination_reason"] == "DEADLINE"]
    short = [row for row in arm_c if row["termination_reason"] == "EOF_SHORT"]
    unknown = [row for row in arm_c if row["termination_reason"] == "UNKNOWN"]
    contained = [row for row in arm_c if row["contained"]]
    within = [row for row in valid
              if abs(float(row["first_boundary_extent_s"]) -
                     DEFAULT_DURATION_SECONDS)
              <= interval_slack * float(row["native_frame_interval_s"])]
    return {"arm_c_n": len(arm_c), "arm_c_deadline_n": len(valid),
            "arm_c_eof_short_n": len(short), "arm_c_unknown_n": len(unknown),
            "arm_c_contained_n": len(contained),
            "arm_c_inherited_unrounded_extent_n": len(within),
            "arm_c_containment_pass": len(contained) == len(arm_c),
            "arm_c_endpoint_pass": len(within) == len(valid) and bool(valid)}
