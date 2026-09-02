# RETIRED: Replaced by domains.tennis.tracking.court_lines and scripts.platformkit.tennis_camera_lock_measure.
"""Sweep the bright-mask threshold and count how many frames reach five clusters.

domains/tennis/tracking/adapter.py masks court lines with
inRange(frame, (200,200,200), (255,255,255)). A comment in the same file records
that the far baseline "is only ~172 grey and does not survive the 200 bright
threshold" -- i.e. the threshold sits ABOVE the signal it is meant to pass.
A per-gate funnel then measured that 62% of frames find only 1-2 of the court's
five length-running lines.

This sweeps the threshold and reports, per value, how many frames reach the
five-cluster gate and how many produce a plausible cross ratio. Nothing here
changes the harness or any threshold in shipped code -- it measures a producer
parameter.

Run: python tennis_threshold_sweep.py <video> [frames]
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
    budget = int(argv[2]) if len(argv) > 2 else 200
    stride = 3
    thresholds = [120, 140, 160, 172, 185, 200]

    adapter = TennisAdapter()
    capture = cv2.VideoCapture(video)
    if not capture.isOpened():
        print("could not open %s" % video)
        return 2

    frames = []
    index = 0
    while len(frames) < budget:
        ok, frame = capture.read()
        if not ok:
            break
        if index % stride == 0:
            frames.append(frame)
        index += 1
    capture.release()
    if not frames:
        print("no frames")
        return 1

    print("video     %s" % video)
    print("frames    %d (stride %d)" % (len(frames), stride))
    print("CROSS_RATIO target %.4f tolerance 0.05" % CROSS_RATIO)
    print()
    print("%-7s %8s %8s %9s %10s" % ("thresh", "5clust", "xratio_ok", "1-2clust", "mask_share"))

    for threshold in thresholds:
        five = ratio_ok = under = 0
        shares = []
        counts = collections.Counter()
        for frame in frames:
            height, width = frame.shape[:2]
            bright = cv2.inRange(frame, np.array((threshold,) * 3),
                                 np.array((255, 255, 255)))
            shares.append(float(bright.mean()) / 255.0)
            lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                                    minLineLength=max(40, width // 12), maxLineGap=20)
            if lines is None:
                continue
            horizontal, vertical = [], []
            for raw in lines[:, 0, :]:
                line = raw.astype(float)
                dx, dy = abs(line[2] - line[0]), abs(line[3] - line[1])
                if dx >= 1.5 * dy:
                    horizontal.append(line)
                elif dy > dx:
                    vertical.append(line)
            if len(horizontal) < 2 or len(vertical) < 2:
                continue
            v_clusters = adapter._cluster_lines(vertical, False, (height, width))
            counts[len(v_clusters)] += 1
            if len(v_clusters) in (1, 2):
                under += 1
            if len(v_clusters) != 5:
                continue
            five += 1
            across = [adapter._line_position(adapter._fit_line(c), False, (height, width))
                      for c in v_clusters]
            denominator = (across[2] - across[1]) * (across[4] - across[0])
            if abs(denominator) < 1e-6:
                continue
            if abs((across[2] - across[0]) * (across[4] - across[1]) / denominator
                   - CROSS_RATIO) <= 0.05:
                ratio_ok += 1
        n = len(frames)
        print("%-7d %8s %8s %9s %10.4f"
              % (threshold, "%d (%.3f)" % (five, five / n),
                 "%d (%.3f)" % (ratio_ok, ratio_ok / n),
                 "%d (%.3f)" % (under, under / n),
                 float(np.median(shares))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
