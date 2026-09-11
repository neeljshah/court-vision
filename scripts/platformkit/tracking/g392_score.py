"""G392 per-rater control scoring, position-error distributions and eligibility.

Scores one control set against its archived truth. It never edits a bar, never
re-dispatches, and treats a missing response as a failure.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path

from scripts.platformkit.tracking import g387_tiles as tiles
from scripts.platformkit.tracking import g392_prepare as prepare
from scripts.platformkit.tracking import g392_protocol as protocol

KEYS = ("p1", "p2", "p3")


def _truth(row: dict[str, str]) -> protocol.Band:
    return protocol.Band((float(row["x1"]), float(row["y1"])), (float(row["x2"]), float(row["y2"])))


def _signed(point: tuple[float, float], band: protocol.Band) -> float:
    dx, dy = band.second[0] - band.first[0], band.second[1] - band.first[1]
    rx, ry = point[0] - band.first[0], point[1] - band.first[1]
    return (rx * dy - ry * dx) / math.hypot(dx, dy)


def _position(point: tuple[float, float], band: protocol.Band) -> float:
    dx, dy = band.second[0] - band.first[0], band.second[1] - band.first[1]
    rx, ry = point[0] - band.first[0], point[1] - band.first[1]
    return (rx * dx + ry * dy) / (dx * dx + dy * dy)


def read_response(directory: Path, control_id: str) -> dict[str, object] | None:
    path = directory / (control_id + ".json")
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def native_points(payload: dict[str, object], offset: tuple[int, int]):
    """Convert the rater tile points with the sealed integer offset, not its own."""
    points = payload.get("points")
    if not isinstance(points, dict):
        return None, False
    converted = []
    for key in KEYS:
        value = points.get(key)
        if not (isinstance(value, (list, tuple)) and len(value) == 2):
            return None, False
        converted.append(protocol.tile_to_native((float(value[0]), float(value[1])), offset))
    claimed = payload.get("native_points")
    ok = isinstance(claimed, dict) and all(
        isinstance(claimed.get(key), (list, tuple)) and len(claimed[key]) == 2
        and abs(float(claimed[key][0]) - converted[index][0]) <= 0.5
        and abs(float(claimed[key][1]) - converted[index][1]) <= 0.5
        for index, key in enumerate(KEYS))
    return tuple(converted), bool(ok)


def score_row(truth_row: dict[str, str], directory: Path, rater: str) -> dict[str, str]:
    """Score one control for one rater; an absent or malformed answer fails."""
    band = _truth(truth_row)
    offset = (int(truth_row["offset_x"]), int(truth_row["offset_y"]))
    row = {"control_id": truth_row["control_id"], "control_set": truth_row["control_set"],
           "rater": rater, "tile_index": truth_row["tile_index"],
           "angle_degrees": truth_row["angle_degrees"], "state": "MISSING", "answered": "0",
           "conversion_ok": "0", "span_px": "", "perp_p1": "", "perp_p2": "", "perp_p3": "",
           "signed_p1": "", "signed_p2": "", "signed_p3": "", "pos_p1": "", "pos_p2": "",
           "pos_p3": "", "angle_error_deg": "", "passed": "0", "fail_reason": "NO_RESPONSE"}
    payload = read_response(directory, truth_row["control_id"])
    if payload is None:
        return row
    row["state"] = str(payload.get("state", "UNKNOWN"))
    points, conversion_ok = native_points(payload, offset)
    row["conversion_ok"] = "1" if conversion_ok else "0"
    if points is None:
        row["fail_reason"] = "NO_POINTS"
        return row
    row["answered"] = "1"
    signed = [_signed(point, band) for point in points]
    positions = [_position(point, band) for point in points]
    for index, key in enumerate(KEYS):
        row["perp_" + key] = "%.3f" % abs(signed[index])
        row["signed_" + key] = "%.3f" % signed[index]
        row["pos_" + key] = "%.4f" % positions[index]
    row["span_px"] = "%.3f" % math.dist(points[0], points[1])
    truth_angle = math.atan2(band.second[1] - band.first[1], band.second[0] - band.first[0])
    seen = math.atan2(points[1][1] - points[0][1], points[1][0] - points[0][0])
    row["angle_error_deg"] = "%.3f" % abs(math.degrees(math.atan2(
        math.sin(seen - truth_angle), math.cos(seen - truth_angle))))
    passed = protocol.control_passes(band, points)
    row["passed"] = "1" if passed else "0"
    if passed:
        row["fail_reason"] = ""
    elif math.dist(points[0], points[1]) < protocol.MIN_SPAN:
        row["fail_reason"] = "SPAN"
    elif max(abs(value) for value in signed) > protocol.POINT_TOLERANCE:
        row["fail_reason"] = "PERPENDICULAR"
    elif not 0.0 < positions[2] < 1.0:
        row["fail_reason"] = "THIRD_POINT_NOT_INTERIOR"
    else:
        row["fail_reason"] = "OUTSIDE_FINITE_BAND"
    return row


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    return {"n": len(ordered), "p50": round(statistics.median(ordered), 3),
            "p90": round(ordered[min(len(ordered) - 1, int(math.ceil(0.9 * len(ordered)) - 1))], 3),
            "max": round(ordered[-1], 3)}


def summarise(rows: list[dict[str, str]]) -> dict[str, object]:
    """Report each rater's total, distributions and the joint context count."""
    raters = sorted({row["rater"] for row in rows})
    per_rater: dict[str, object] = {}
    for rater in raters:
        mine = [row for row in rows if row["rater"] == rater]
        perp = [abs(float(row["perp_" + key])) for row in mine for key in KEYS if row["perp_" + key]]
        angles = [float(row["angle_error_deg"]) for row in mine if row["angle_error_deg"]]
        per_rater[rater] = {
            "controls": len(mine), "answered": sum(row["answered"] == "1" for row in mine),
            "passed": sum(row["passed"] == "1" for row in mine),
            "conversion_ok": sum(row["conversion_ok"] == "1" for row in mine),
            "perpendicular_px": _quantiles(perp), "angle_error_deg": _quantiles(angles),
            "fail_reasons": {reason: sum(row["fail_reason"] == reason for row in mine)
                             for reason in sorted({row["fail_reason"] for row in mine} - {""})}}
    by_control: dict[str, list[bool]] = {}
    for row in rows:
        by_control.setdefault(row["control_id"], []).append(row["passed"] == "1")
    joint = sum(all(values) and len(values) == len(raters) for values in by_control.values())
    qualified = all(per_rater[rater]["passed"] >= protocol.CONTROL_BAR for rater in raters)
    return {"bar": protocol.CONTROL_BAR, "controls": len(by_control), "per_rater": per_rater,
            "joint": joint, "raters": raters,
            "qualified": bool(qualified and joint >= protocol.CONTROL_BAR and len(raters) == 2),
            "excluded": [rater for rater in raters
                         if per_rater[rater]["passed"] < protocol.CONTROL_BAR]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--out-root", type=Path, required=True)
    parser.add_argument("--set", dest="control_set", required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    truth_rows = tiles.read_csv(args.truth)
    rows = []
    for rater in prepare.RATERS:
        directory = args.out_root / ("%s_%s" % (args.control_set, rater))
        rows.extend(score_row(row, directory, rater) for row in truth_rows)
    tiles.write_csv(args.scores, rows)
    summary = summarise(rows)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
