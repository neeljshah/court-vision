"""Pure duration-cap mechanics for the G401 preparation path.

These helpers are proposal support only.  They do not open videos or invoke a
production route.
"""
from __future__ import annotations

import math
from typing import Iterable


LEGACY_FRAME_CAP = 3000
TARGET_DURATION_SECONDS = 100.0


def validated_frame_cap(fps: float | None, *, pts_valid: bool) -> tuple[int, str]:
    """Return the fixed duration cap or the safe legacy fallback."""
    if not pts_valid or fps is None or not math.isfinite(fps) or fps <= 0:
        return LEGACY_FRAME_CAP, "UNKNOWN"
    return int(math.ceil(TARGET_DURATION_SECONDS * fps)), "VALIDATED_FPS"


def pts_are_constant_rate(pts: Iterable[float], fps: float | None) -> bool:
    """Require monotonic PTS intervals within one thousandth of a frame."""
    values = list(pts)
    if fps is None or not math.isfinite(fps) or fps <= 0 or len(values) < 2:
        return False
    interval = 1.0 / fps
    tolerance = interval / 1000.0
    return all(math.isfinite(value) for value in values) and all(
        abs((right - left) - interval) <= tolerance
        for left, right in zip(values, values[1:])
    )


def capped_pts_receipt(pts: Iterable[float], *, start_index: int, frame_cap: int,
                       fps: float | None) -> dict[str, float | int | None | str]:
    """Describe admitted and excluded source PTS without decoding a source."""
    values = list(pts)
    if start_index < 0 or frame_cap <= 0 or start_index >= len(values):
        return {"status": "EOF", "admitted_count": 0, "first_excluded_index": None,
                "last_admitted_pts": None, "first_excluded_pts": None,
                "cap_limited_span_s": 0.0, "available_span_s": 0.0}
    admitted = min(frame_cap, len(values) - start_index)
    last_index = start_index + admitted - 1
    excluded = start_index + admitted if start_index + admitted < len(values) else None
    interval = 1.0 / fps if fps is not None and fps > 0 else 0.0
    first_pts = values[start_index]
    available = max(0.0, values[-1] - first_pts + interval)
    if excluded is None:
        capped = available
        status = "EOF"
        excluded_pts = None
    else:
        capped = max(0.0, values[excluded] - first_pts)
        status = "CAPPED"
        excluded_pts = values[excluded]
    return {"status": status, "admitted_count": admitted,
            "first_excluded_index": excluded, "last_admitted_pts": values[last_index],
            "first_excluded_pts": excluded_pts, "cap_limited_span_s": capped,
            "available_span_s": available}


def cap_loss(receipt: dict[str, float | int | None | str]) -> float:
    """Return the sealed loss against the fixed 100-second target."""
    available = float(receipt["available_span_s"] or 0.0)
    limited = float(receipt["cap_limited_span_s"] or 0.0)
    return max(0.0, min(TARGET_DURATION_SECONDS, available) - limited)


def policy_status(losses: Iterable[float | None]) -> str:
    """Apply the sealed UNKNOWN rule without computing a percentage."""
    values = list(losses)
    if any(value is None for value in values):
        return "PARTIAL_UNKNOWN"
    return "ZERO_LOSS" if not any(float(value) > 5.0 for value in values) else "POSITIVE_LOSS"
