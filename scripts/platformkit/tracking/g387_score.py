"""G387 control and real-frame localization scoring with fixed all-frame denominators."""
from __future__ import annotations

import hashlib
import json
import math

CONTROL_TOLERANCE = 3.0
PAIR_TOLERANCE = 6.0
AUDIT_TOLERANCE = 3.0


def _point(row: dict[str, str], prefix: str) -> tuple[float, float]:
    return float(row[prefix + "x"]), float(row[prefix + "y"])


def _xy(row: dict[str, str], x: str, y: str) -> tuple[float, float]:
    return float(row[x]), float(row[y])


def _distance(left: tuple[float, float], right: tuple[float, float]) -> float:
    return math.hypot(left[0] - right[0], left[1] - right[1])


def _line_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return float("inf")
    return abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / length


def control_success(point: dict[str, str], ratings: list[dict[str, str]]) -> bool:
    """Require both raters to meet the sealed endpoint and centreline tolerances."""
    if len(ratings) != 2 or any(row["state"] != "VISIBLE" for row in ratings):
        return False
    expected_a = _xy(point, "x1", "y1")
    expected_b = _xy(point, "x2", "y2")
    for row in ratings:
        a, b, mid = _point(row, ""), _xy(row, "x2", "y2"), _xy(row, "mid_x", "mid_y")
        direct = max(_distance(a, expected_a), _distance(b, expected_b))
        reverse = max(_distance(a, expected_b), _distance(b, expected_a))
        if min(direct, reverse) > CONTROL_TOLERANCE or _line_distance(mid, expected_a, expected_b) > CONTROL_TOLERANCE:
            return False
    return True


def real_frame(opaque_id: str, terra: list[dict[str, str]], sol: list[dict[str, str]], audit: dict[str, int], visibility: str) -> dict[str, object]:
    """Score one real context once; UNKNOWN remains in the returned denominator row."""
    pairs = 0
    for left in terra:
        for right in sol:
            if left["state"] != "VISIBLE" or right["state"] != "VISIBLE" or left["physical_id"] != right["physical_id"]:
                continue
            la, lb = _point(left, ""), _xy(left, "x2", "y2")
            ra, rb = _point(right, ""), _xy(right, "x2", "y2")
            endpoints = min(max(_distance(la, ra), _distance(lb, rb)), max(_distance(la, rb), _distance(lb, ra)))
            lm, rm = _xy(left, "mid_x", "mid_y"), _xy(right, "mid_x", "mid_y")
            midpoint_ok = (_line_distance(lm, ra, rb) <= AUDIT_TOLERANCE and _line_distance(rm, la, lb) <= AUDIT_TOLERANCE)
            if endpoints <= PAIR_TOLERANCE and midpoint_ok and audit.get("terra", 0) >= 8 and audit.get("sol", 0) >= 8:
                pairs += 1
    return {"opaque_id": opaque_id, "visibility": visibility, "localized": int(pairs > 0), "paired_ids": pairs}


def summary(control_rows: list[bool], real_rows: list[dict[str, object]]) -> dict[str, int]:
    """Report separate fixed denominators; controls never enter real-frame n."""
    return {"controls_success": sum(control_rows), "controls_denominator": len(control_rows),
            "real_localized": sum(int(row["localized"]) for row in real_rows), "real_denominator": len(real_rows),
            "real_unknown": sum(row["visibility"] == "UNKNOWN" for row in real_rows)}


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
