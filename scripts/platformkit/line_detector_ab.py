"""Compare line detectors on tennis court registration, holding everything else fixed.

The tennis registration bottleneck is measured: 62% of 720p frames find only one
or two of the court's five length-running lines, and when five ARE found the
cross ratio is usually wrong (p50 1.478 against a target of 1.1667). Both facts
point at the LINE DETECTOR, which today is cv2.HoughLinesP on a brightness mask.

OpenCV ships two learned/analytic alternatives, both BSD and therefore
licence-clean for a sellable product: LSD (createLineSegmentDetector) and FLD
(ximgproc.createFastLineDetector). This runs all three through the SAME
clustering and the SAME cross-ratio test so the only variable is detection.

Run: python line_detector_ab.py <video> [frames]
"""
from __future__ import annotations

import collections
import sys

import cv2
import numpy as np


def _hough(gray_mask, width):
    lines = cv2.HoughLinesP(gray_mask, 1, np.pi / 180.0, threshold=45,
                            minLineLength=max(40, width // 12), maxLineGap=20)
    return [] if lines is None else [l.astype(float) for l in lines[:, 0, :]]


def _lsd(gray, width):
    detector = cv2.createLineSegmentDetector()
    found = detector.detect(gray)[0]
    if found is None:
        return []
    out = []
    for seg in found[:, 0, :]:
        if np.hypot(seg[2] - seg[0], seg[3] - seg[1]) >= max(40, width // 12):
            out.append(seg.astype(float))
    return out


def _fld(gray, width):
    detector = cv2.ximgproc.createFastLineDetector(
        length_threshold=max(40, width // 12))
    found = detector.detect(gray)
    if found is None:
        return []
    return [seg.astype(float) for seg in found[:, 0, :]]


def main(argv: list) -> int:
    sys.path.insert(0, ".")
    from domains.tennis.tracking.adapter import CROSS_RATIO, TennisAdapter

    video = argv[1]
    budget = int(argv[2]) if len(argv) > 2 else 200
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
        if index % 5 == 0:
            frames.append(frame)
        index += 1
    capture.release()
    if not frames:
        print("no frames")
        return 1

    print("video  %s" % video)
    print("frames %d" % len(frames))
    print("CROSS_RATIO target %.4f tolerance 0.05" % CROSS_RATIO)
    print()
    print("%-8s %11s %11s %12s" % ("detector", "5clust", "xratio_ok", "1-2clust"))

    for name in ("hough", "lsd", "fld"):
        five = ratio_ok = under = 0
        counts = collections.Counter()
        for frame in frames:
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            if name == "hough":
                mask = cv2.inRange(frame, np.array((200,) * 3),
                                   np.array((255, 255, 255)))
                segments = _hough(mask, width)
            elif name == "lsd":
                segments = _lsd(gray, width)
            else:
                segments = _fld(gray, width)
            horizontal, vertical = [], []
            for seg in segments:
                dx, dy = abs(seg[2] - seg[0]), abs(seg[3] - seg[1])
                if dx >= 1.5 * dy:
                    horizontal.append(seg)
                elif dy > dx:
                    vertical.append(seg)
            if len(horizontal) < 2 or len(vertical) < 2:
                continue
            v_clusters = adapter._cluster_lines(vertical, False, (height, width))
            counts[len(v_clusters)] += 1
            if len(v_clusters) in (1, 2):
                under += 1
            if len(v_clusters) != 5:
                continue
            five += 1
            across = [adapter._line_position(adapter._fit_line(c), False,
                                             (height, width)) for c in v_clusters]
            denominator = (across[2] - across[1]) * (across[4] - across[0])
            if abs(denominator) < 1e-6:
                continue
            if abs((across[2] - across[0]) * (across[4] - across[1]) / denominator
                   - CROSS_RATIO) <= 0.05:
                ratio_ok += 1
        n = len(frames)
        print("%-8s %11s %11s %12s"
              % (name, "%d (%.3f)" % (five, five / n),
                 "%d (%.3f)" % (ratio_ok, ratio_ok / n),
                 "%d (%.3f)" % (under, under / n)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
