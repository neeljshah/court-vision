"""Measure tennis cut, calibration, and both-player failure modes on a clip.

This is diagnostic only. It follows ``TennisAdapter.process_video``'s cut and
sampled-frame order, but neither writes tracking CSVs nor changes the adapter.

Run: python -m scripts.platformkit.tennis_wave7_falsifiers VIDEO [max_frames]
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from typing import Any

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.segmenter import detect_cut, small_gray
from scripts.platformkit.tracking_timebase import sampling_plan


def _axis_summary(points: list[np.ndarray]) -> dict[str, Any]:
    """Return per-axis changes between consecutive accepted observations."""
    if len(points) < 2:
        return {"n_steps": 0, "sd_x_ft": None, "sd_y_ft": None,
                "p95_distance_ft": None}
    delta = np.diff(np.asarray(points), axis=0)
    return {"n_steps": len(delta), "sd_x_ft": round(float(delta[:, 0].std()), 4),
            "sd_y_ft": round(float(delta[:, 1].std()), 4),
            "p95_distance_ft": round(float(np.quantile(np.linalg.norm(delta, axis=1), 0.95)), 4)}


def probe(path: str, max_frames: int = 1800) -> dict[str, Any]:
    """Run all three Wave 7 falsifiers on at most ``max_frames`` decoded frames."""
    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        raise FileNotFoundError(path)
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    plan = sampling_plan(fps)
    adapter = TennisAdapter()
    previous_gray = None
    source = cuts = samples = accepts = both = 0
    waiting_first = True
    first_accepts: list[dict[str, Any]] = []
    regular_accepts: list[dict[str, Any]] = []
    calibration_points: list[np.ndarray] = []
    observed_steps: dict[int, list[np.ndarray]] = {1: [], 2: []}
    previous_player: dict[int, np.ndarray] = {}
    counts: Counter[str] = Counter()
    try:
        while source < max_frames:
            ok, frame = capture.read()
            if not ok:
                break
            gray = small_gray(frame)
            if previous_gray is not None and detect_cut(previous_gray, gray):
                adapter._reset_temporal_calibration()
                cuts += 1
                waiting_first = True
                previous_player = {}
            previous_gray = gray
            if source % plan.stride:
                source += 1
                continue
            samples += 1
            homography = adapter._stable_homography(frame)
            if homography is None:
                counts["no_solve"] += 1
                source += 1
                continue
            accepts += 1
            height, width = frame.shape[:2]
            # A constant pixel location makes this a homography-only jitter
            # signal; it is not an anchor and does not have zero residual by
            # construction.
            calibration_points.append(adapter._project((width / 2.0, height / 2.0), homography))
            players = adapter.detect_players(frame, homography)
            record = {"frame": source, "both": len(players) == 2,
                      "oob": any(not (-21 <= point[0] <= 99 and -12 <= point[1] <= 48)
                                 for _, point in players)}
            (first_accepts if waiting_first else regular_accepts).append(record)
            waiting_first = False
            if len(players) != 2:
                counts["not_both"] += 1
            else:
                both += 1
                for track_id, point in players:
                    if track_id in previous_player:
                        observed_steps[track_id].append(point - previous_player[track_id])
                    previous_player[track_id] = point
            source += 1
    finally:
        capture.release()
    def rate(rows: list[dict[str, Any]], field: str) -> float | None:
        return round(sum(row[field] for row in rows) / len(rows), 4) if rows else None
    return {
        "video": path, "source_fps": fps, "sample_stride": plan.stride,
        "decoded_frames": source, "sampled_frames": samples, "cuts": cuts,
        "accepted_solves": accepts, "accept_rate": round(accepts / samples, 4) if samples else 0.0,
        "both_player_frames": both,
        "both_player_rate_given_solve": round(both / accepts, 4) if accepts else 0.0,
        "homography_center_jitter": _axis_summary(calibration_points),
        "observed_player_step": {str(track): _axis_summary(points)
                                 for track, points in observed_steps.items()},
        "first_solve_after_cut": {"n": len(first_accepts), "both_rate": rate(first_accepts, "both"),
                                   "oob_rate": rate(first_accepts, "oob")},
        "later_solve": {"n": len(regular_accepts), "both_rate": rate(regular_accepts, "both"),
                        "oob_rate": rate(regular_accepts, "oob")},
        "loss_counts": dict(counts),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: tennis_wave7_falsifiers.py VIDEO [max_frames]")
        return 2
    result = probe(argv[1], int(argv[2]) if len(argv) > 2 else 1800)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
