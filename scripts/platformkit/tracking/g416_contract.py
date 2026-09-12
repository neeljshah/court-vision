"""Pure, additive court-point shadow proposal mechanics for G416."""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite
from typing import Mapping, Sequence

TOPCUT = 60
PAD = 15
DETECTOR_GUARD = 250
PIPELINE_GUARD = 350
SHADOW_FIELDS = (
    "shadow_court_x", "shadow_court_y", "shadow_status", "matrix_receipt",
    "source_receipt", "call_receipt", "would_violate_existing_guard",
)


@dataclass(frozen=True)
class ShadowPoint:
    """An additive proposed court point or an explicitly unknown outcome."""

    x: int | None
    y: int | None
    status: str
    would_violate_existing_guard: str


def cropped_box_foot(stored_xyxy: Sequence[float], width: int,
                     height: int) -> tuple[int, int] | None:
    """Rebuild archived clipped, unpadded box foot from a padded stored tuple."""
    if len(stored_xyxy) != 4 or width <= 0 or height <= 0:
        return None
    try:
        x1, y1, x2, y2 = (int(float(value)) for value in stored_xyxy)
    except (TypeError, ValueError, OverflowError):
        return None
    x1, y1, x2, y2 = x1 + PAD, y1 + PAD, x2 - PAD, y2 - PAD
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(width, x2), min(height, y2)
    if x2c <= x1c or y2c <= y1c:
        return None
    return ((x1c + x2c) // 2, y2c)


def native_then_cropped_foot(stored_xyxy: Sequence[float], width: int,
                             height: int) -> tuple[int, int] | None:
    """Document the topcut inversion; the court input stays cropped-space."""
    foot = cropped_box_foot(stored_xyxy, width, height)
    if foot is None:
        return None
    native = (foot[0], foot[1] + TOPCUT)
    return native[0], native[1] - TOPCUT


def project_m_then_m1(m: Sequence[float], m1: Sequence[float],
                      point: tuple[int, int]) -> tuple[int, int] | None:
    """Match advanced_tracker.py:1426-1428: M1@(M@kpt), one divide, int32."""
    if len(m) != 9 or len(m1) != 9:
        return None
    try:
        values = tuple(float(value) for value in (*m, *m1))
    except (TypeError, ValueError):
        return None
    if not all(isfinite(value) for value in values):
        return None
    a, b, c, d, e, f, g, h, i, A, B, C, D, E, F, G, H, I = values
    x, y = point
    u, v, w = a*x + b*y + c, d*x + e*y + f, g*x + h*y + i
    q0, q1, q2 = A*u + B*v + C*w, D*u + E*v + F*w, G*u + H*v + I*w
    if not isfinite(q2) or q2 == 0.0:
        return None
    ox, oy = q0 / q2, q1 / q2
    limit = 2 ** 31
    if not (isfinite(ox) and isfinite(oy) and -limit <= ox < limit and -limit <= oy < limit):
        return None
    return int(ox), int(oy)


def shadow_point(old_xy: tuple[int, int] | None, stored_xyxy: Sequence[float] | None,
                 width: int, height: int, m: Sequence[float] | None,
                 m1: Sequence[float] | None, receipts_bound: bool,
                 route: str) -> ShadowPoint:
    """Produce an additive shadow result while preserving unknown/non-box routes."""
    if not receipts_bound:
        return ShadowPoint(None, None, "UNKNOWN_MISSING_RECEIPT", "UNKNOWN")
    if route != "BOX":
        return ShadowPoint(None, None, "UNKNOWN_NON_BOX_ROUTE", "UNKNOWN")
    if stored_xyxy is None or m is None or m1 is None:
        return ShadowPoint(None, None, "UNKNOWN_MISSING_INPUT", "UNKNOWN")
    foot = native_then_cropped_foot(stored_xyxy, width, height)
    proposed = None if foot is None else project_m_then_m1(m, m1, foot)
    if proposed is None:
        return ShadowPoint(None, None, "UNKNOWN_INVALID_PROJECTION", "UNKNOWN")
    if old_xy is None:
        guard = "UNKNOWN"
    else:
        distance = hypot(proposed[0] - old_xy[0], proposed[1] - old_xy[1])
        guard = "YES" if distance > DETECTOR_GUARD or distance > PIPELINE_GUARD else "NO"
    return ShadowPoint(proposed[0], proposed[1], "PROPOSED", guard)


def additive_row(original: Mapping[str, object], shadow: ShadowPoint,
                 matrix_receipt: str, source_receipt: str,
                 call_receipt: str) -> dict[str, object]:
    """Return original fields unchanged plus the complete additive shadow schema."""
    result = dict(original)
    result.update({
        "shadow_court_x": "" if shadow.x is None else shadow.x,
        "shadow_court_y": "" if shadow.y is None else shadow.y,
        "shadow_status": shadow.status,
        "matrix_receipt": matrix_receipt,
        "source_receipt": source_receipt,
        "call_receipt": call_receipt,
        "would_violate_existing_guard": shadow.would_violate_existing_guard,
    })
    return result
