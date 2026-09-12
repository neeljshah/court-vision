"""Independent homogeneous arithmetic oracle for G416 controls."""
from __future__ import annotations

from math import isfinite
from typing import Sequence


def independent_corner_oracle(m: Sequence[float], m1: Sequence[float],
                              stored_xyxy: Sequence[float], width: int,
                              height: int) -> tuple[int, int] | None:
    """Independently reconstruct corners then explicitly multiply both 3x3 maps."""
    if len(m) != 9 or len(m1) != 9 or len(stored_xyxy) != 4:
        return None
    try:
        sx1, sy1, sx2, sy2 = (int(float(value)) for value in stored_xyxy)
        p = tuple(float(value) for value in m)
        q = tuple(float(value) for value in m1)
    except (TypeError, ValueError, OverflowError):
        return None
    if width <= 0 or height <= 0 or not all(isfinite(value) for value in p + q):
        return None
    left, top = max(0, sx1 + 15), max(0, sy1 + 15)
    right, bottom = min(width, sx2 - 15), min(height, sy2 - 15)
    if right <= left or bottom <= top:
        return None
    x, y = (left + right) // 2, bottom
    r0, r1, r2 = p[0]*x + p[1]*y + p[2], p[3]*x + p[4]*y + p[5], p[6]*x + p[7]*y + p[8]
    s0 = q[0]*r0 + q[1]*r1 + q[2]*r2
    s1 = q[3]*r0 + q[4]*r1 + q[5]*r2
    s2 = q[6]*r0 + q[7]*r1 + q[8]*r2
    if not isfinite(s2) or s2 == 0.0:
        return None
    ox, oy = s0 / s2, s1 / s2
    limit = 2 ** 31
    if not (isfinite(ox) and isfinite(oy) and -limit <= ox < limit and -limit <= oy < limit):
        return None
    return int(ox), int(oy)
