"""Per-stage row funnel for the baseball tracking adapter (diagnostic, read-only).

Replays BaseballAdapter.process_video's exact gate order against a real clip and
counts how many frames survive each stage, so a thin run can be attributed to a
specific gate instead of guessed at.

Run: python -m scripts.platformkit.baseball_funnel_probe <video> [max_frames] [stride]
"""
from __future__ import annotations

import sys
from collections import Counter

import cv2
import numpy as np

from domains.baseball.tracking.adapter import (
    MOUND_TO_PLATE_FEET,
    BaseballAdapter,
)
from domains.baseball.tracking.segmenter import detect_cut, small_gray
from domains.baseball.tracking.scale_anchor import anchor_calibrations


def probe_geometry(adapter, frame, counts):
    """adapter.detect_pitch_geometry re-run with a counter at every early return."""
    roi, x_offset, y_offset = adapter._center_crop(frame)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array((35, 35, 25)), np.array((95, 255, 255)))
    counts["green_frac_sum"] += float(np.count_nonzero(green)) / green.size
    if not adapter._dominant_green(roi):
        counts["stop_green"] += 1
        return None
    counts["pass_green"] += 1
    height, width = frame.shape[:2]
    blobs = [
        (area, center + np.array((x_offset, y_offset), dtype=np.float32))
        for area, center in adapter._dirt_blobs(roi, exclude_regions=())
    ]
    counts["blobs_sum"] += len(blobs)
    mound = [
        center for _, center in blobs
        if 0.30 * width <= center[0] <= 0.70 * width
        and 0.25 * height <= center[1] <= 0.68 * height
    ]
    plate = [
        center for _, center in blobs
        if 0.35 * width <= center[0] <= 0.65 * width
        and 0.60 * height <= center[1] <= 0.95 * height
    ]
    counts["has_mound_blob"] += 1 if mound else 0
    counts["has_plate_blob"] += 1 if plate else 0
    if not mound or not plate:
        counts["stop_no_anchor"] += 1
        return None
    counts["pass_anchors"] += 1
    center_x = width / 2.0
    mound_point = min(mound, key=lambda p: abs(p[0] - center_x) + abs(p[1] - height * 0.50))
    plate_point = min(plate, key=lambda p: abs(p[0] - center_x) + abs(p[1] - height * 0.78))
    distance = float(np.linalg.norm(mound_point - plate_point))
    if plate_point[1] <= mound_point[1] or distance < 0.18 * height:
        counts["stop_geometry_order"] += 1
        return None
    counts["pass_geometry"] += 1
    from domains.baseball.tracking.adapter import PitchGeometry

    return PitchGeometry(mound_point, plate_point, distance / MOUND_TO_PLATE_FEET)


def probe_players(adapter, frame, geometry, counts):
    """adapter.detect_players re-run with per-stage counters."""
    boxes = list(adapter.detector(frame))
    counts["det_boxes_sum"] += len(boxes)
    counts["frames_with_det"] += 1 if boxes else 0
    span = float(np.linalg.norm(geometry.mound - geometry.plate))
    top, bottom = geometry.mound[1] - 0.6 * span, geometry.plate[1] + 0.4 * span
    candidates = []
    for box in boxes:
        x1, y1, x2, y2 = map(float, box[:4])
        if x2 <= x1 or y2 <= y1:
            continue
        foot = np.array(((x1 + x2) / 2.0, y2), dtype=np.float32)
        if top <= foot[1] <= bottom and abs(foot[0] - geometry.plate[0]) <= 1.5 * span:
            candidates.append((foot, adapter._project(foot, geometry)))
        else:
            counts["cand_out_of_window"] += 1
            if foot[1] > bottom:
                counts["cand_below_plate_y"] += 1
            elif foot[1] < top:
                counts["cand_beyond_mound_y"] += 1
            else:
                counts["cand_wide_x"] += 1
    counts["cand_sum"] += len(candidates)
    counts["frames_cand_ge1"] += 1 if len(candidates) >= 1 else 0
    if not candidates:
        counts["stop_lt2_candidates"] += 1
        return []
    counts["pass_2_candidates"] += 1

    def nearest(anchor, excluded=None):
        choices = [i for i in range(len(candidates)) if i != excluded]
        return min(choices, key=lambda i: np.linalg.norm(candidates[i][0] - anchor)) if choices else None

    pitcher = nearest(geometry.mound)
    batter = nearest(geometry.plate, pitcher)
    tracked = [(1, candidates[pitcher][1])]
    if batter is not None:
        tracked.append((2, candidates[batter][1]))
    return tracked


def main(argv):
    if len(argv) < 2:
        print("usage: baseball_funnel_probe.py <video> [max_frames] [stride]")
        return 2
    path = argv[1]
    max_frames = int(argv[2]) if len(argv) > 2 else 30000
    stride = int(argv[3]) if len(argv) > 3 else 3
    adapter = BaseballAdapter()
    counts = Counter()
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        print("could not open %s" % path)
        return 1
    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)
    rows, calibrations = [], []
    segment_id = 0
    in_pitch_view = False
    source_frame = processed = 0
    previous_gray = None
    try:
        while processed < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            if source_frame % stride == 0:
                current_gray = small_gray(frame)
                cut = previous_gray is not None and detect_cut(previous_gray, current_gray)
                previous_gray = current_gray
                counts["cuts"] += 1 if cut else 0
                geometry = None if cut else probe_geometry(adapter, frame, counts)
                if geometry is not None:
                    if not in_pitch_view:
                        segment_id += 1
                        in_pitch_view = True
                    calibrations.append({
                        "frame": source_frame,
                        "segment_id": segment_id,
                        "pixels_per_foot": geometry.pixels_per_foot,
                        "plate_centerline": float(geometry.plate[0]),
                    })
                    for track_id, point in probe_players(adapter, frame, geometry, counts):
                        rows.append({"frame": source_frame, "track_id": track_id})
                else:
                    in_pitch_view = False
                processed += 1
            source_frame += 1
    finally:
        capture.release()
    stable = anchor_calibrations(calibrations, calibrations)[0] if calibrations else []
    stable_frames = {row["frame"] for row in stable}
    final_rows = [row for row in rows if row["frame"] in stable_frames]
    seg_lengths = Counter(row["segment_id"] for row in calibrations)
    print("video               %s" % path)
    print("total frames / fps  %d / %.2f" % (total_frames, fps))
    print("frames read         %d" % source_frame)
    print("frames sampled      %d  (stride=%d)" % (processed, stride))
    print("  cut-suppressed    %d" % counts["cuts"])
    print("  mean green frac   %.3f (gate needs >= 0.350)" % (counts["green_frac_sum"] / max(1, processed - counts["cuts"])))
    print("  pass green gate   %d   stop_green %d" % (counts["pass_green"], counts["stop_green"]))
    print("  has mound blob    %d   has plate blob %d" % (counts["has_mound_blob"], counts["has_plate_blob"]))
    print("  pass anchors      %d   stop_no_anchor %d" % (counts["pass_anchors"], counts["stop_no_anchor"]))
    print("  stop_geom_order   %d" % counts["stop_geometry_order"])
    print("CALIBRATED FRAMES   %d   segments %d" % (counts["pass_geometry"], segment_id))
    print("  seg len >=10      %d of %d" % (sum(1 for n in seg_lengths.values() if n >= 10), len(seg_lengths)))
    print("detector on those   boxes=%d  frames_with_det=%d" % (counts["det_boxes_sum"], counts["frames_with_det"]))
    print("  candidates kept   %d" % counts["cand_sum"])
    print("  rejected window   %d (below_plate_y %d, beyond_60ft %d, wide_x %d)"
          % (counts["cand_out_of_window"], counts["cand_below_plate_y"],
             counts["cand_beyond_mound_y"], counts["cand_wide_x"]))
    print("  frames >=1 cand   %d   frames >=2 cand %d   stop_lt2 %d"
          % (counts["frames_cand_ge1"], counts["pass_2_candidates"], counts["stop_lt2_candidates"]))
    print("RAW ROWS            %d" % len(rows))
    print("stabilizer kept     %d of %d calibrations" % (len(stable), len(calibrations)))
    print("FINAL ROWS          %d" % len(final_rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
