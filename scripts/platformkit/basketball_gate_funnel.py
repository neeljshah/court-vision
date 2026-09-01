"""Per-gate failure funnel for semantic basketball court landmarks.

The basketball provider deliberately fails closed.  This read-only diagnostic
replays its actual paint gates on real frames and counts the first one that
rejects each frame.  It also reports landmark co-occurrence, which answers
whether a partial paint can furnish a four-point solve.

Run: python -m scripts.platformkit.basketball_gate_funnel <video> [frames]
"""
from __future__ import annotations

import collections
import argparse
import sys
from dataclasses import dataclass
from typing import Counter, Dict, Iterable, Tuple

import cv2
import numpy as np

from domains.basketball.tracking.keypoints import BasketballKeypointProvider, _line_support


@dataclass(frozen=True)
class FrameGates:
    """Measured provider gate counts for one BGR frame."""

    outline_quads: int
    physical_quads: int
    supported_quads: int
    landmarks: Tuple[str, ...]
    candidate_areas: Tuple[float, ...]
    candidate_min_sides: Tuple[float, ...]

    @property
    def first_failure(self) -> str:
        """Return the first actual provider gate that failed."""
        if self.outline_quads == 0:
            return "1_no_four_corner_outline"
        if self.physical_quads == 0:
            return "2_no_physically_large_lane"
        if self.supported_quads == 0:
            return "3_edge_support_below_minimum"
        return "4_paint_named"


def inspect_frame(frame: np.ndarray, provider: BasketballKeypointProvider) -> FrameGates:
    """Replay paint gates without changing the provider or producing rows."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    outlines = list(provider._candidate_quads(gray))
    minimum_area = 0.006 * width * height
    physical = []
    areas = []
    min_sides = []
    for quad in outlines:
        area = abs(float(cv2.contourArea(quad.reshape(-1, 1, 2))))
        sides = np.linalg.norm(quad - np.roll(quad, -1, axis=0), axis=1)
        areas.append(area)
        min_sides.append(float(sides.min()))
        if area >= minimum_area and float(sides.min()) >= 0.15 * height:
            physical.append(quad)
    supported = [quad for quad in physical
                 if _line_support(gray, quad) >= provider.min_edge_support]
    landmarks = tuple(sorted(provider.detect(frame))) if supported else ()
    return FrameGates(len(outlines), len(physical), len(supported), landmarks,
                      tuple(areas), tuple(min_sides))


def _histogram(values: Iterable[int]) -> Counter[int]:
    return collections.Counter(values)


def _percentiles(values: list[float]) -> str:
    if not values:
        return "none"
    values_array = np.asarray(values, dtype=float)
    return "p50=%.1f p95=%.1f max=%.1f n=%d" % (
        np.percentile(values_array, 50), np.percentile(values_array, 95),
        values_array.max(), len(values_array),
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Measure basketball landmark gates.")
    parser.add_argument("video")
    parser.add_argument("frames", nargs="?", type=int, default=300)
    parser.add_argument("--interval-seconds", type=float, default=0.0,
                        help="sample at this wall-clock interval; zero reads every frame")
    args = parser.parse_args(argv[1:])
    if args.frames < 1 or args.interval_seconds < 0:
        print("frames must be positive and interval-seconds cannot be negative")
        return 2
    capture = cv2.VideoCapture(args.video)
    if not capture.isOpened():
        print("could not open %s" % args.video)
        return 2
    fps = capture.get(cv2.CAP_PROP_FPS)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    provider = BasketballKeypointProvider()
    died: Counter[str] = collections.Counter()
    outlines, physical, supported = [], [], []
    cooccurrence: Counter[Tuple[str, ...]] = collections.Counter()
    areas, min_sides = [], []
    processed = 0
    next_sample_ms = 0.0
    try:
        while processed < args.frames:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if args.interval_seconds and timestamp_ms + 0.1 < next_sample_ms:
                continue
            next_sample_ms += args.interval_seconds * 1000.0
            measured = inspect_frame(frame, provider)
            processed += 1
            died[measured.first_failure] += 1
            outlines.append(measured.outline_quads)
            physical.append(measured.physical_quads)
            supported.append(measured.supported_quads)
            areas.extend(measured.candidate_areas)
            min_sides.extend(measured.candidate_min_sides)
            if measured.landmarks:
                cooccurrence[measured.landmarks] += 1
    finally:
        capture.release()
    print("video     %s" % args.video)
    print("source    %dx%d at %.3f fps" % (width, height, fps))
    print("processed %d sampled frames; interval %.3f seconds" %
          (processed, args.interval_seconds))
    print()
    print("WHERE FRAMES DIE (actual provider gates)")
    for name in ("1_no_four_corner_outline", "2_no_physically_large_lane",
                 "3_edge_support_below_minimum", "4_paint_named"):
        count = died[name]
        print("  %-34s %5d  (%.3f)" % (name, count, count / max(1, processed)))
    print()
    print("CANDIDATE COUNT DISTRIBUTIONS")
    for label, values in (("four-corner outlines", outlines),
                          ("physically large lanes", physical),
                          ("edge-supported lanes", supported)):
        print("  %s" % label)
        for count, frames in sorted(_histogram(values).items()):
            print("    %2d candidates  %5d  (%.3f)" %
                  (count, frames, frames / max(1, processed)))
    print()
    print("PHYSICAL LANE-SIZE MEASUREMENT")
    print("  gate requires area >= %.1f px2 and shortest side >= %.1f px" %
          (0.006 * width * height, 0.15 * height))
    print("  candidate area: %s" % _percentiles(areas))
    print("  candidate shortest side: %s" % _percentiles(min_sides))
    print()
    print("NAMED LANDMARK CO-OCCURRENCE")
    if not cooccurrence:
        print("  no frame reached a named paint; circle detection is not reached")
    else:
        for names, count in sorted(cooccurrence.items(), key=lambda item: (-item[1], item[0])):
            print("  %-64s %5d  (%.3f)" % (",".join(names), count, count / processed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
