"""Row builders for the G411 endpoint tables and timeline cards.

Split out of `g411_run` so every helper file stays inside the 300-line rail.
"""
from __future__ import annotations

from fractions import Fraction

from scripts.platformkit.tracking import g411_measure as M
from scripts.platformkit.tracking import g411_rational as RAT


def tally(premise: dict, past: dict, flt: dict, fps_text: str) -> None:
    """Reproduce the G408 arm-C counts from the archived decimal values."""
    premise["arm_c_n"] += 1
    extent = flt["first_boundary_extent"]
    last = flt["last_admitted_extent"]
    if M.contained(extent):
        premise["float_contained_n"] += 1
    if M.within_bar(extent, fps_text):
        premise["float_first_excluded_pass_n"] += 1
    if M.within_bar(last, fps_text):
        premise["float_last_admitted_pass_n"] += 1
    else:
        premise["marginal_excess_s"].append(
            {"source_name": past["source_name"],
             "excess_s": M.as_text(abs(last - M.TARGET) - M.bar(fps_text), 12)})
    if M.rounded_text(extent) == "%.6f" % float(past["first_boundary_extent_s"]):
        premise["float_row_matches_g408_n"] += 1


def stop_row(name: str, arm: str, past: dict, rat: dict, fps_text: str,
              native: dict, read_frames: int, draw_j: str) -> dict:
    """One rational stop row, parent schema plus explicit `_units` aliases."""
    extent = rat["first_boundary_extent"]
    last = rat["last_admitted_extent"]
    deadline = rat["deadline"]
    parent_boundary = (extent if rat["first_excluded_index"] is not None
                       else None)
    parent_contained = (deadline is None or rat["last_admitted_pts"] is None
                        or rat["last_admitted_pts"] < deadline)
    boundary_read = 1 if rat["first_excluded_index"] is not None else 0
    return {"source_name": name, "arm": arm, "rule": past["rule"],
            "frame_cap": past["frame_cap"],
            "read_frames": (rat["admitted_frames"] or 0) + boundary_read,
            "retained_stream_frames": read_frames,
            "admitted_frames": rat["admitted_frames"],
            "first_admitted_index": rat["first_admitted_index"],
            "last_admitted_index": rat["last_admitted_index"],
            "last_admitted_pts_units": units_of(rat["last_admitted_pts"],
                                              native["time_base"]),
            "first_excluded_index": rat["first_excluded_index"],
            "first_excluded_pts_units": units_of(rat["first_excluded_pts"],
                                               native["time_base"]),
            "time_base": native["time_base"], "validated_fps": fps_text,
            "deadline_s": M.as_text(deadline), "deadline_from_origin_s": "100",
            "first_boundary_extent_exact":
            M.exact_text(extent), "first_boundary_extent_s": M.as_text(parent_boundary),
            "last_admitted_extent_exact": M.exact_text(last),
            "last_admitted_extent_s": M.as_text(last),
            "inherited_bar_exact": M.exact_text(M.bar(fps_text)),
            "first_excluded_within_bar": M.within_bar(extent, fps_text),
            "last_admitted_within_bar": M.within_bar(last, fps_text),
            "contained": parent_contained,
            "boundary_reached": M.contained(extent),
            "termination_reason": rat["termination_reason"],
            "unknown_reason": rat["unknown_reason"],
            "unknown_reason_g411": rat["unknown_reason_g411"], "draw_j": draw_j,
            # fix 1b (B2): G408 parent columns as same-semantics seconds
            # aliases of the exact rational values (parent: float seconds)
            "last_admitted_pts": M.as_text(rat["last_admitted_pts"]),
            "first_excluded_pts": M.as_text(rat["first_excluded_pts"]),
            "span_s": M.as_text(last),
            "endpoint_gap_s": M.as_text(None if last is None else M.TARGET - last),
            "last_admitted_gap_s": M.as_text(None if last is None else M.TARGET - last),
            "overshoot_s": M.as_text(None if parent_boundary is None
                                      else parent_boundary - M.TARGET),
            "native_frame_interval_s": M.exact_text(M.bar(fps_text))}


def units_of(value, base_text: str):
    """Return an exact rational second value back in native integer units."""
    if value is None:
        return None
    base = RAT.time_base(base_text)
    exact = value / base
    return exact.numerator if exact.denominator == 1 else M.exact_text(exact)


def compare(name: str, arm: str, draw_j: str, flt: dict, rat: dict,
             fps_text: str) -> list:
    """Float-versus-rational outcome rows for both endpoint definitions."""
    rows = []
    for label, key in (("first_excluded", "first_boundary_extent"),
                       ("last_admitted", "last_admitted_extent")):
        left, right = flt[key], rat[key]
        left_ok, right_ok = M.within_bar(left, fps_text), M.within_bar(right, fps_text)
        changed = left_ok is not None and right_ok is not None and left_ok != right_ok
        rows.append({
            "source_name": name, "arm": arm, "draw_j": draw_j,
            "endpoint_definition": label, "float_extent_s": M.as_text(left),
            "rational_extent_s": M.as_text(right),
            "rational_extent_exact": M.exact_text(right),
            "extent_delta_s": "" if left is None or right is None
            else M.as_text(right - left),
            "float_within_bar": left_ok, "rational_within_bar": right_ok,
            "bar_outcome_changed": changed,
            "serialization_explains_change": bool(
                changed and left is not None and right is not None
                and abs(right - left) < M.bar(fps_text) / 1000),
            "float_reason": flt["termination_reason"],
            "rational_reason": rat["termination_reason"]})
    return rows


def join(name: str, units: list, floats: list, base: Fraction) -> list:
    """Bind rational frames to the archived decimal stream by frame index."""
    rows = []
    mismatch = 0
    for index, value in enumerate(units):
        if index >= len(floats):
            break
        exact = None if value is None else value * base
        shown = "" if exact is None else M.rounded_text(exact)
        if shown != "%.6f" % floats[index] and mismatch < 5:
            mismatch += 1
            rows.append({"source_name": name, "frame_index": index,
                         "integer_pts": value, "rational_s": shown,
                         "archived_decimal_s": "%.6f" % floats[index],
                         "serialization_matches": False})
    rows.insert(0, {"source_name": name, "frame_index": -1,
                    "integer_pts": len(units),
                    "rational_s": str(len(floats)), "archived_decimal_s": "",
                    "serialization_matches": mismatch == 0})
    return rows


def card(name: str, draw_j: str, units: list, floats: list, base: Fraction,
          fps_text: str, past: dict) -> dict:
    """One even timeline card showing both computations around the endpoint."""
    excluded = int(past["first_excluded_index"])
    lines = ["G411 timeline card draw_j=%s" % draw_j, "source %s" % name,
             "time_base 1/%d  validated_fps %s  bar_exact %s"
             % ((Fraction(1, 1) / base).numerator, fps_text,
                M.exact_text(M.bar(fps_text))),
             "idx  integer_pts  rational_s          archived_decimal_s"]
    for index in range(max(0, excluded - 3), min(len(units), excluded + 3)):
        exact = units[index] * base
        lines.append("%5d %11d  %-18s  %s" % (
            index, units[index], M.as_text(exact, 9),
            "%.6f" % floats[index] if index < len(floats) else "NA"))
    origin = units[0] * base
    extent = units[excluded] * base - origin
    last = units[excluded - 1] * base - origin
    lines += ["first_excluded idx=%d extent_exact=%s extent_s=%s within_bar=%s"
              % (excluded, M.exact_text(extent), M.as_text(extent),
                 M.within_bar(extent, fps_text)),
              "last_admitted  idx=%d extent_exact=%s extent_s=%s within_bar=%s"
              % (excluded - 1, M.exact_text(last), M.as_text(last),
                 M.within_bar(last, fps_text)),
              "archived float first_boundary_extent_s=%s last_admitted_pts=%s"
              % (past["first_boundary_extent_s"], past["last_admitted_pts"])]
    return {"source_name": name, "draw_j": draw_j, "text": "\n".join(lines) + "\n",
            "first_excluded_index": excluded}
