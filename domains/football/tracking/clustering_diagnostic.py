"""Trace football LSD yard-family clustering without invoking calibration.

Run: python -m domains.football.tracking.clustering_diagnostic VIDEO --output DIR
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from domains.football.tracking.adapter import FootballAdapter
from domains.football.tracking.field_gates import (CROSS_RATIO_TOLERANCE,
    FIELD_ROI_MIN_SEGMENT_SUPPORT, MIN_FIELD_VIEW_GREEN, YARD_PENCIL_CROSS_RATIO,
    field_roi_mask, field_view_fraction, pencil_is_uniform, pencil_positions,
    segment_field_support)

LINE_ANGLE_GROUP_DEGREES = 8.0


def _angle(segment: np.ndarray) -> float:
    return float(np.arctan2(segment[3] - segment[1], segment[2] - segment[0]) % np.pi)


def _angle_delta(first: float, second: float) -> float:
    return abs(((first - second + np.pi / 2) % np.pi) - np.pi / 2)


def _segments(frame: np.ndarray, use_field_roi: bool) -> list[np.ndarray]:
    grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    roi = field_roi_mask(frame) if use_field_roi else None
    source = cv2.bitwise_and(grayscale, grayscale, mask=roi) if roi is not None else grayscale
    found = cv2.createLineSegmentDetector().detect(source)[0]
    raw = ([] if found is None else
           [item.astype(float) for item in found.reshape(-1, found.shape[-1])])
    if roi is None:
        return raw
    return [item for item in raw
            if segment_field_support(item, roi) >= FIELD_ROI_MIN_SEGMENT_SUPPORT]


def trace_frame(frame: np.ndarray, adapter: FootballAdapter,
                use_field_roi: bool) -> tuple[dict, list[np.ndarray]]:
    """Return every geometry-filter denominator and the final candidate segments."""
    raw = _segments(frame, use_field_roi)
    minimum = max(30.0, frame.shape[1] / 12.0)
    length = [item for item in raw if np.hypot(item[2] - item[0], item[3] - item[1]) >= minimum]
    groups: list[list[np.ndarray]] = []
    for item in length:
        for group in groups:
            if _angle_delta(_angle(item), _angle(group[0])) < np.deg2rad(LINE_ANGLE_GROUP_DEGREES):
                group.append(item)
                break
        else:
            groups.append([item])
    winning = max(groups, key=len) if groups else []
    direction = float(np.mean([_angle(item) for item in winning])) if winning else None
    normal = np.array((-np.sin(direction), np.cos(direction))) if direction is not None else None
    offsets = sorted(float(np.dot((item[:2] + item[2:]) / 2.0, normal)) for item in winning) if normal is not None else []
    merge = 8.0
    clusters = adapter.family_from_segments(length)
    positions = pencil_positions(clusters, frame.shape)
    ratios = []
    for first, second, third, fourth in zip(positions, positions[1:], positions[2:], positions[3:]):
        denominator = (third - second) * (fourth - first)
        if abs(denominator) > 1e-9:
            ratios.append((third - first) * (fourth - second) / denominator)
    hist, edges = np.histogram(np.degrees([_angle(item) for item in length]), bins=np.arange(0, 190, 10))
    trace = {
        "shape": [int(frame.shape[1]), int(frame.shape[0])],
        "field_roi": use_field_roi,
        "lsd_raw": len(raw), "length_min_px": minimum, "after_length": len(length),
        "angle_window_deg": LINE_ANGLE_GROUP_DEGREES, "angle_groups": [len(group) for group in groups],
        "winning_group_segments": len(winning), "winning_angle_deg": None if direction is None else np.degrees(direction),
        "merge_distance_px": merge, "winning_offsets_px": offsets,
        "adjacent_offset_gaps_px": [b - a for a, b in zip(offsets, offsets[1:])],
        "merged_family_lines": len(clusters), "pencil_positions_px": positions,
        "cross_ratio_expected": YARD_PENCIL_CROSS_RATIO,
        "cross_ratio_tolerance": CROSS_RATIO_TOLERANCE * YARD_PENCIL_CROSS_RATIO,
        "cross_ratios": ratios, "pencil_uniform": pencil_is_uniform(clusters, frame.shape),
        "angle_histogram_10deg": {
            "%d-%d" % (int(lo), int(hi)): int(value) for lo, hi, value in zip(edges, edges[1:], hist)},
    }
    return trace, winning


def _overlay(frame: np.ndarray, segments: list[np.ndarray], trace: dict) -> np.ndarray:
    image = frame.copy()
    for item in segments:
        cv2.line(image, tuple(np.round(item[:2]).astype(int)), tuple(np.round(item[2:]).astype(int)), (0, 0, 255), 3)
    text = "surviving=%d merged=%d merge_px=%.1f" % (len(segments), trace["merged_family_lines"], trace["merge_distance_px"])
    cv2.putText(image, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 4)
    cv2.putText(image, text, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    return image


def measure(video: Path, output: Path, positions: int, trace_frames: int,
            use_field_roi: bool = True) -> dict:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open %s" % video)
    output.mkdir(parents=True, exist_ok=True)
    result, adapter = {"sampled": 0, "field_view": 0, "line_detection": 0,
                       "yard_line_family": 0,
                       "numerals": 0, "traces": []}, FootballAdapter()
    count = max(int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    try:
        for index in np.linspace(0, count - 1, num=positions, dtype=int):
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = capture.read()
            if not ok:
                continue
            result["sampled"] += 1
            if field_view_fraction(frame) < MIN_FIELD_VIEW_GREEN:
                continue
            result["field_view"] += 1
            trace, surviving = trace_frame(frame, adapter, use_field_roi)
            result["line_detection"] += int(bool(surviving))
            result["yard_line_family"] += int(trace["pencil_uniform"])
            from domains.football.tracking.scale_source_probe import _numeral_count
            result["numerals"] += _numeral_count(frame, adapter.family_from_segments(surviving))
            if len(result["traces"]) < trace_frames:
                trace["frame_index"] = int(index)
                result["traces"].append(trace)
                cv2.imwrite(str(output / ("surviving_%02d.jpg" % len(result["traces"]))), _overlay(frame, surviving, trace))
    finally:
        capture.release()
    (output / "clustering_trace.json").write_text(json.dumps(result, indent=2), encoding="ascii")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--positions", type=int, default=120)
    parser.add_argument("--trace-frames", type=int, default=10)
    parser.add_argument("--no-field-roi", action="store_true")
    args = parser.parse_args(argv[1:])
    result = measure(args.video, args.output, args.positions, args.trace_frames,
                     use_field_roi=not args.no_field_roi)
    print("sampled=%d field_view=%d line_detection=%d yard_line_family=%d numerals=%d traces=%d" %
          (result["sampled"], result["field_view"], result["line_detection"], result["yard_line_family"],
           result["numerals"], len(result["traces"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(__import__("sys").argv))
