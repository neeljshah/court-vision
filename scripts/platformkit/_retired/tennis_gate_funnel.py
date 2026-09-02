# RETIRED: Replaced by scripts.platformkit.tennis_camera_lock_measure on the current court_lines and camera_lock path.
"""Per-gate failure funnel for tennis court registration.

detect_court_corners is a chain of gates and it returns None from any of them,
so "court not found" carries no information about WHY. This re-runs the same
gates in the same order and counts where each frame dies. The histogram names
the fix.

Run: python -m scripts.platformkit.tennis_gate_funnel <video> [frames]
"""
from __future__ import annotations

import collections
import sys

import cv2
import numpy as np


def main(argv: list) -> int:
    sys.path.insert(0, ".")
    from domains.tennis.tracking.adapter import CROSS_RATIO, TennisAdapter

    video = argv[1]
    budget = int(argv[2]) if len(argv) > 2 else 300
    stride = 3

    adapter = TennisAdapter()
    capture = cv2.VideoCapture(video)
    if not capture.isOpened():
        print("could not open %s" % video)
        return 2

    died = collections.Counter()
    vertical_counts = collections.Counter()
    cross_ratios = []
    bright_share = []
    processed = 0
    frame_index = 0
    try:
        while processed < budget:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride == 0:
                processed += 1
                height, width = frame.shape[:2]
                bright = cv2.inRange(frame, np.array((200, 200, 200)),
                                     np.array((255, 255, 255)))
                bright_share.append(float(bright.mean()) / 255.0)
                lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                                        minLineLength=max(40, width // 12),
                                        maxLineGap=20)
                if lines is None:
                    died["1_no_hough_lines"] += 1
                    frame_index += 1
                    continue
                horizontal, vertical = [], []
                for raw in lines.reshape(-1, lines.shape[-1]):
                    line = raw.astype(float)
                    dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
                    if dx >= 1.5 * dy:
                        horizontal.append(line)
                    elif dy > dx:
                        vertical.append(line)
                if len(horizontal) < 2 or len(vertical) < 2:
                    died["2_too_few_h_or_v_lines"] += 1
                    frame_index += 1
                    continue
                h_clusters = adapter._cluster_lines(horizontal, True, (height, width))
                v_clusters = adapter._cluster_lines(vertical, False, (height, width))
                vertical_counts[len(v_clusters)] += 1
                if not h_clusters:
                    died["3_no_horizontal_cluster"] += 1
                    frame_index += 1
                    continue
                if len(v_clusters) != 5:
                    died["4_vertical_clusters_not_exactly_5"] += 1
                    frame_index += 1
                    continue
                across = [adapter._line_position(adapter._fit_line(c), False,
                                                 (height, width)) for c in v_clusters]
                denominator = (across[2] - across[1]) * (across[4] - across[0])
                if abs(denominator) < 1e-6:
                    died["5_degenerate_cross_ratio"] += 1
                    frame_index += 1
                    continue
                ratio = (across[2] - across[0]) * (across[4] - across[1]) / denominator
                cross_ratios.append(ratio)
                if abs(ratio - CROSS_RATIO) > 0.05:
                    died["6_cross_ratio_mismatch"] += 1
                    frame_index += 1
                    continue
                died["7_reached_depth_order_or_later"] += 1
            frame_index += 1
    finally:
        capture.release()

    print("video     %s" % video)
    print("processed %d frames (stride %d)" % (processed, stride))
    print("CROSS_RATIO target %.4f, tolerance 0.05" % CROSS_RATIO)
    if bright_share:
        share = np.array(bright_share)
        print("bright-mask share of frame: p50 %.4f  p90 %.4f" %
              (float(np.percentile(share, 50)), float(np.percentile(share, 90))))
    print()
    print("WHERE FRAMES DIE")
    for name, count in sorted(died.items()):
        print("  %-34s %5d  (%.3f)" % (name, count, count / max(1, processed)))
    print()
    print("VERTICAL CLUSTER COUNT DISTRIBUTION (gate wants exactly 5)")
    for n, count in sorted(vertical_counts.items()):
        print("  %2d clusters  %5d  (%.3f)" % (n, count, count / max(1, processed)))
    if cross_ratios:
        arr = np.array(cross_ratios)
        print()
        print("observed cross ratio when 5 clusters were found: n=%d p50 %.4f min %.4f max %.4f"
              % (len(arr), float(np.percentile(arr, 50)), float(arr.min()), float(arr.max())))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
