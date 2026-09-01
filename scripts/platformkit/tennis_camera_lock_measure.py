"""Measure current-master tennis camera locks without changing tracking code.

Examples:
  python -m scripts.platformkit.tennis_camera_lock_measure video.mp4 out --linspace 0 48047 600
  python -m scripts.platformkit.tennis_camera_lock_measure video.mp4 out --range 3816 4565 --orientation-json dead.json

The manifest, not emitted tracking rows, supplies the decoded-frame denominator.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np
import pandas as pd

from domains.tennis.tracking.adapter import TennisAdapter
from domains.tennis.tracking.court_diagnostics import rejection_gate


_VIDEO_CAPTURE = cv2.VideoCapture


class IndexedCapture:
    """Present selected source frames to the unmodified adapter as one stream."""

    def __init__(self, path: Path, indices: Sequence[int]) -> None:
        self._path, self._indices, self._offset = str(path), list(indices), 0
        self._capture = _VIDEO_CAPTURE(self._path)

    def isOpened(self) -> bool:
        return self._capture.isOpened()

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self._offset >= len(self._indices):
            return False, None
        self._capture.set(cv2.CAP_PROP_POS_FRAMES, self._indices[self._offset])
        self._offset += 1
        return self._capture.read()

    def release(self) -> None:
        self._capture.release()


def frame_indices(args: argparse.Namespace) -> list[int]:
    """Return exactly the requested source-frame sample plan."""
    if args.linspace:
        start, stop, count = args.linspace
        if count < 1 or stop < start:
            raise ValueError("linspace needs start <= stop and count >= 1")
        return np.linspace(start, stop, count, dtype=int).tolist()
    start, stop = args.range
    if stop < start:
        raise ValueError("range needs start <= stop")
    return list(range(start, stop + 1))


def _run_adapter(video: Path, indices: Sequence[int], output_dir: Path,
                 no_detector: bool) -> dict[str, object]:
    """Run the production adapter against source frames without re-encoding them."""
    output_dir.mkdir(parents=True, exist_ok=True)
    adapter = TennisAdapter(detector=(lambda _: ()) if no_detector else None)
    raw_accepts = 0
    locks_formed = 0
    original_corners = adapter.detect_court_corners
    original_add = adapter._camera_lock.add_fresh_solve

    def count_raw(frame: np.ndarray) -> np.ndarray | None:
        nonlocal raw_accepts
        corners = original_corners(frame)
        raw_accepts += int(corners is not None)
        return corners

    def count_locks(homography: np.ndarray) -> None:
        nonlocal locks_formed
        was_ready = adapter._camera_lock.ready
        original_add(homography)
        locks_formed += int(not was_ready and adapter._camera_lock.ready)

    adapter.detect_court_corners = count_raw  # type: ignore[method-assign]
    adapter._camera_lock.add_fresh_solve = count_locks  # type: ignore[method-assign]
    import domains.tennis.tracking.adapter as adapter_module
    original_capture = adapter_module.cv2.VideoCapture
    adapter_module.cv2.VideoCapture = lambda _: IndexedCapture(video, indices)  # type: ignore[assignment]
    try:
        rows = adapter.process_video("selected_source_frames.mp4", max_frames=len(indices))
    finally:
        adapter_module.cv2.VideoCapture = original_capture  # type: ignore[assignment]
    tracking_path = output_dir / "tracking.csv"
    adapter.write_csv(tracking_path, rows)
    manifest_path = output_dir / "frame_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    decoded = int(len(manifest))
    fresh = int((manifest["calibration_provenance"] == "solved").sum())
    reuse = int((manifest["calibration_provenance"] == "camera_lock_drift_checked").sum())
    drift_rejects = int((manifest["status"] == "unsolved_drift").sum())
    solved = fresh + reuse
    return {
        "requested_source_frames": len(indices),
        "decoded": decoded,
        "raw_accepts": raw_accepts,
        "fresh_solves": fresh,
        "locks_formed": locks_formed,
        "drift_checked_reuses": reuse,
        "drift_rejects": drift_rejects,
        "solved_frames": solved,
        "solved_frame_coverage": solved / decoded if decoded else None,
        "tracking_csv": str(tracking_path),
        "frame_manifest_csv": str(manifest_path),
    }


def orientation_rejections(video: Path, start: int, stop: int, limit: int = 10) -> list[dict[str, object]]:
    """Record the production orientation-gate counts plus their immutable bounds."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    result: list[dict[str, object]] = []
    try:
        for source_frame in range(start, stop + 1):
            capture.set(cv2.CAP_PROP_POS_FRAMES, source_frame)
            ok, frame = capture.read()
            if not ok:
                continue
            if rejection_gate(frame) != "insufficient_oriented_lines":
                continue
            height, width = frame.shape[:2]
            bright = cv2.inRange(frame, np.array((200, 200, 200)), np.array((255, 255, 255)))
            lines = cv2.HoughLinesP(bright, 1, np.pi / 180.0, threshold=45,
                                    minLineLength=max(40, width // 12), maxLineGap=20)
            horizontal = vertical = unclassified = 0
            ratios: list[float] = []
            for raw in lines[:, 0, :] if lines is not None else ():
                dx, dy = abs(float(raw[2] - raw[0])), abs(float(raw[3] - raw[1]))
                ratios.append(dx / dy if dy else float("inf"))
                if dx >= 1.5 * dy:
                    horizontal += 1
                elif dy > dx:
                    vertical += 1
                else:
                    unclassified += 1
            result.append({
                "source_frame": source_frame,
                "horizontal_lines": horizontal,
                "horizontal_bound": ">= 2 (each requires abs(dx) / abs(dy) >= 1.5)",
                "vertical_lines": vertical,
                "vertical_bound": ">= 2 (each requires abs(dy) > abs(dx))",
                "unclassified_lines": unclassified,
                "segment_dx_over_dy_min": min(ratios) if ratios else None,
                "segment_dx_over_dy_max": (
                    max(ratios) if ratios and np.isfinite(max(ratios)) else "inf"
                ) if ratios else None,
            })
            if len(result) == limit:
                break
    finally:
        capture.release()
    return result


def scan_raw_accepts(video: Path, start: int, stop: int) -> list[int]:
    """Sequentially locate raw production-corner accepts without tracking rows."""
    capture = _VIDEO_CAPTURE(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    capture.set(cv2.CAP_PROP_POS_FRAMES, start)
    adapter = TennisAdapter(detector=lambda _: ())
    accepted: list[int] = []
    try:
        for source_frame in range(start, stop + 1):
            ok, frame = capture.read()
            if not ok:
                break
            if adapter.detect_court_corners(frame) is not None:
                accepted.append(source_frame)
    finally:
        capture.release()
    return accepted


def main() -> int:
    """Write funnel JSON, manifest/tracking CSV, and optional immutable harness output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("output_dir", type=Path)
    plan = parser.add_mutually_exclusive_group()
    plan.add_argument("--linspace", nargs=3, type=int, metavar=("START", "STOP", "COUNT"))
    plan.add_argument("--range", nargs=2, type=int, metavar=("START", "STOP"))
    plan.add_argument("--scan-accepts", nargs=2, type=int, metavar=("START", "STOP"),
                      help="discovery only: sequential raw-corner scan, no adapter output")
    parser.add_argument("--orientation-json", type=Path)
    parser.add_argument("--no-detector", action="store_true", help="discovery only; do not use for harness evidence")
    args = parser.parse_args()
    if args.scan_accepts:
        start, stop = args.scan_accepts
        accepted = scan_raw_accepts(args.video, start, stop)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        scan_path = args.output_dir / "raw_accept_frames.json"
        scan_path.write_text(json.dumps(accepted, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"scan_start": start, "scan_stop": stop,
                          "raw_accepts": len(accepted), "accepted_frames": accepted}))
        return 0
    if not args.linspace and not args.range:
        parser.error("one of --linspace, --range, or --scan-accepts is required")
    indices = frame_indices(args)
    summary = _run_adapter(args.video, indices, args.output_dir, args.no_detector)
    summary["source_frame_plan"] = {"first": indices[0], "last": indices[-1], "count": len(indices)}
    harness_path = args.output_dir / "frozen_harness.txt"
    if summary["locks_formed"] and not args.no_detector:
        command = [sys.executable, "-m", "scripts.platformkit.tracking_harness", summary["tracking_csv"], "tennis"]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        harness_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
        summary["frozen_harness_exit_code"] = completed.returncode
        summary["frozen_harness_output"] = str(harness_path)
    if args.orientation_json:
        args.orientation_json.parent.mkdir(parents=True, exist_ok=True)
        orientation = orientation_rejections(args.video, indices[0], indices[-1])
        args.orientation_json.write_text(json.dumps(orientation, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        summary["orientation_rejection_samples"] = str(args.orientation_json)
        summary["orientation_rejection_sample_count"] = len(orientation)
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
