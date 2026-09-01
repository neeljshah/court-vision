"""Measure the tennis tracking funnel frame-by-frame (diagnostic only).

Run: python scripts/platformkit/tennis_coverage_probe.py <video> [max_processed] [stride]

Prints where each processed frame is lost: no homography, no player in a half,
or emitted. Coverage in tracking_harness only counts frames that emitted a row,
so this separates the three causes the report cannot distinguish.
"""
from __future__ import annotations

import collections
import json
import sys

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.ball import MotionDiffDetector
from domains.tennis.tracking.segmenter import detect_cut, small_gray


def probe(path: str, max_processed: int = 3000, stride: int = 3) -> dict:
    adapter = TennisAdapter()
    ball_detector = MotionDiffDetector()
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise FileNotFoundError(path)
    counts: collections.Counter = collections.Counter()
    per_frame: list[dict] = []
    source = processed = 0
    previous = None
    try:
        while processed < max_processed:
            ok, frame = capture.read()
            if not ok:
                break
            current = small_gray(frame)
            if previous is not None and detect_cut(previous, current):
                adapter._reset_temporal_calibration()
                counts["cuts"] += 1
            previous = current
            if source % stride:
                source += 1
                continue
            corners = adapter.detect_court_corners(frame)
            has_corners = corners is not None
            counts["corners_found"] += has_corners
            homography = adapter._stable_homography(frame)
            provenance = adapter._calibration_provenance
            if homography is None:
                counts["no_homography"] += 1
                per_frame.append({"f": source, "state": "no_homography"})
            else:
                counts["homography_" + provenance] += 1
                stats = _detection_stats(adapter, frame, homography)
                halves = stats["halves"]
                key = "emitted" if halves == {0, 1} else (
                    "half_missing_" + ("both" if not halves else str(sorted(halves)[0])))
                counts[key] += 1
                counts["raw_dets"] += stats["raw"]
                counts["on_court_dets"] += stats["on_court"]
                ball = ball_detector.detect(frame) is not None
                counts["ball_seen"] += ball
                if halves != {0, 1} and ball:
                    counts["ball_only_row"] += 1
                per_frame.append({"f": source, "state": key, "raw": stats["raw"],
                                  "on_court": stats["on_court"], "ball": ball,
                                  "prov": provenance, "corners": has_corners,
                                  "near_miss": stats["near_miss"],
                                  "rejected": stats["rejected"],
                                  "feet": stats["feet"]})
            processed += 1
            source += 1
    finally:
        capture.release()
    counts["processed"] = processed
    return {"counts": dict(counts), "per_frame": per_frame}


def _detection_stats(adapter: TennisAdapter, frame: np.ndarray,
                     homography: np.ndarray) -> dict:
    """Replay detect_players' filters, recording how many boxes survive each."""
    raw = on_court = near_miss = 0
    halves: set[int] = set()
    rejected: list[tuple[float, float]] = []
    feet: list[tuple[float, float]] = []
    for box in adapter.detector(frame):
        x1, y1, x2, y2 = map(float, box[:4])
        if len(box) >= 5 and float(box[4]) < adapter.tracker_conf:
            continue
        if x2 <= x1 or y2 <= y1:
            continue
        raw += 1
        foot = adapter._project(((x1 + x2) / 2.0, y2), homography)
        if not (-5 <= foot[0] <= 83 and -5 <= foot[1] <= 41):
            if -20 <= foot[0] <= 98 and -20 <= foot[1] <= 56:
                near_miss += 1
                rejected.append((round(float(foot[0]), 1), round(float(foot[1]), 1)))
            continue
        on_court += 1
        feet.append((round(float(foot[0]), 1), round(float(foot[1]), 1)))
        halves.add(0 if foot[1] < 18.0 else 1)
    return {"raw": raw, "on_court": on_court, "halves": halves,
            "near_miss": near_miss, "rejected": rejected, "feet": feet}


def _runs(frames: list[int], stride: int) -> list[int]:
    if not frames:
        return []
    lengths, run = [], 1
    for a, b in zip(frames, frames[1:]):
        if b - a == stride:
            run += 1
        else:
            lengths.append(run)
            run = 1
    lengths.append(run)
    return lengths


def main() -> None:
    path = sys.argv[1]
    max_processed = int(sys.argv[2]) if len(sys.argv) > 2 else 3000
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    result = probe(path, max_processed, stride)
    counts, rows = result["counts"], result["per_frame"]
    dump = sys.argv[4] if len(sys.argv) > 4 else None
    if dump:
        with open(dump, "w") as handle:
            json.dump(result, handle)
    emitted = [r for r in rows if r["state"] != "no_homography"]
    both = [r for r in emitted if r["state"] == "emitted"]
    ball_only = [r for r in emitted if r["state"] != "emitted" and r["ball"]]
    print(json.dumps(counts, indent=2, sort_keys=True))
    denom = len(both) + len(ball_only)
    print("harness_denominator(frames with any row) = %d" % denom)
    print("harness_coverage = %.4f" % (len(both) / denom if denom else 0.0))
    lengths = _runs([r["f"] for r in ball_only], stride)
    if lengths:
        arr = np.array(lengths)
        print("ball_only runs=%d  <=3frames=%.1f%%  >=10frames=%.1f%%  max=%d"
              % (len(arr), 100 * arr[arr <= 3].sum() / arr.sum(),
                 100 * arr[arr >= 10].sum() / arr.sum(), arr.max()))
    misses = collections.Counter(r["state"] for r in emitted if r["state"] != "emitted")
    print("miss_states", dict(misses))
    missed = [r for r in emitted if r["state"] != "emitted"]
    print("on_court_dets_on_missed_frames",
          dict(sorted(collections.Counter(r["on_court"] for r in missed).items())))
    xtab = collections.Counter(
        (r["corners"], r["state"], min(r["on_court"], 3)) for r in missed)
    print("missed  (corners_seen, state, on_court_capped3) -> n")
    for key, n in sorted(xtab.items(), key=lambda kv: -kv[1]):
        print("   %-38s %d" % (str(key), n))
    print("EMITTED frames with corners seen: %d / %d"
          % (sum(r["corners"] for r in both), len(both)))
    print("MISSED frames with corners seen: %d / %d"
          % (sum(r["corners"] for r in missed), len(missed)))
    print("MISSED+ball_only with corners seen: %d / %d"
          % (sum(r["corners"] for r in ball_only), len(ball_only)))
    print("near_miss(off-court-window dets) on missed frames: %d"
          % sum(r["near_miss"] for r in missed))
    _bound_report(missed)


def _bound_report(missed: list[dict]) -> None:
    """Which of the four acceptance bounds rejects the near-miss detections."""
    tally: collections.Counter = collections.Counter()
    recoverable = 0
    for row in missed:
        halves = set(row["feet"] and [0 if f[1] < 18.0 else 1 for f in row["feet"]])
        gained = set()
        for fx, fy in row["rejected"]:
            if fx < -5:
                tally["x_below_-5 (wide of left sideline)"] += 1
            elif fx > 83:
                tally["x_above_83 (wide of right sideline)"] += 1
            if fy < -5:
                tally["y_below_-5 (behind near baseline)"] += 1
            elif fy > 41:
                tally["y_above_41 (behind far baseline)"] += 1
            gained.add(0 if fy < 18.0 else 1)
        if halves | gained == {0, 1}:
            recoverable += 1
    print("rejected-detection bound tally:", dict(tally.most_common()))
    print("missed frames recoverable if the window were widened: %d / %d"
          % (recoverable, len(missed)))


if __name__ == "__main__":
    main()
