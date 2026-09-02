"""Sample court-view tennis sequences and record frozen harness verdicts."""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np
import pandas as pd

from scripts.platformkit.tracking.source_timebase import (
    frames_to_seconds, probe_source, seconds_to_frames,
)


CaptureFactory = Callable[[str], object]
Gate = Callable[[np.ndarray], str]
_VIDEO_CAPTURE = cv2.VideoCapture


class IndexedCapture:
    """Present selected source frames to the unchanged adapter as one stream."""

    def __init__(self, path: Path, indices: Sequence[int]) -> None:
        self._indices, self._offset = list(indices), 0
        self._capture = _VIDEO_CAPTURE(str(path))

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


def select_ranges(video: Path, count: int, frames: int, seed: int = 20260901,
                  capture_factory: CaptureFactory = cv2.VideoCapture,
                  gate: Gate | None = None) -> list[tuple[int, int]]:
    """Choose deterministic contiguous ranges centered on existing court accepts."""
    if count < 1 or frames < 1:
        raise ValueError("ranges and frames must be positive")
    if gate is None:
        from domains.tennis.tracking.court_diagnostics import rejection_gate
        gate = rejection_gate
    capture = capture_factory(str(video))
    if not capture.isOpened():
        raise FileNotFoundError(video)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    step = max(1, frames // 20)
    starts: set[int] = set()
    index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step == 0 and gate(frame) == "accepted":
                starts.add(max(0, min(index - frames // 2, max(0, total - frames))))
            index += 1
    finally:
        capture.release()
    candidates = sorted(starts)
    if not candidates:
        return []
    chooser = random.Random(seed)
    chosen = chooser.sample(candidates, min(count, len(candidates)))
    return sorted((start, min(start + frames - 1, total - 1)) for start in chosen)


def run_range(video: Path, start: int, stop: int,
              source_fps: float | None = None) -> dict[str, object]:
    """Run the production adapter/camera lock and unchanged frozen harness."""
    from domains.tennis.tracking.adapter import TennisAdapter
    from scripts.platformkit.tracking_harness import evaluate

    indices = list(range(start, stop + 1))
    adapter = TennisAdapter()
    import domains.tennis.tracking.adapter as adapter_module
    original_capture = adapter_module.cv2.VideoCapture
    adapter_module.cv2.VideoCapture = lambda _: IndexedCapture(video, indices)
    try:
        rows = adapter.process_video("selected_source_frames.mp4", max_frames=len(indices))
    finally:
        adapter_module.cv2.VideoCapture = original_capture
    manifest = adapter.last_frame_manifest
    decoded = int(len(manifest))
    reuse = int((manifest["calibration_provenance"] == "camera_lock_drift_checked").sum())
    fresh = int((manifest["calibration_provenance"] == "solved").sum())
    report = evaluate(rows, "tennis")
    metrics = {name: getattr(report, name) for name in (
        "coverage_pct", "median_track_len", "ball_valid_pct", "jump_p95", "oob_pct"
    )}
    result: dict[str, object] = {
        "source_frame_range": {"start": start, "stop": stop, "count": len(indices)},
        "decoded_frames": decoded,
        "fresh_solves": fresh,
        "drift_checked_reuses": reuse,
        "solved_frame_coverage": (fresh + reuse) / decoded if decoded else None,
        "harness_verdict": "PASS" if report.passed else "FAIL",
        "harness_failures": report.failures,
        "harness_metrics": metrics,
    }
    if source_fps:
        seconds = frames_to_seconds(start, stop, source_fps)
        result["source_seconds_range"] = {"start": seconds[0], "stop": seconds[1]}
    return result


def build_report(video: Path, ranges: int = 5, frames: int = 300,
                 seed: int = 20260901,
                 selected: list[tuple[int, int]] | None = None) -> dict[str, object]:
    """Build the one-video evidence report without altering selection gates."""
    source = probe_source(video)
    selected = selected if selected is not None else select_ranges(video, ranges, frames, seed)
    source_fps = source["source_fps"]
    results = [run_range(video, start, stop, source_fps if isinstance(source_fps, float) else None)
               for start, stop in selected]
    passed = sum(item["harness_verdict"] == "PASS" for item in results)
    return {
        "video": str(video),
        "source": source,
        "selection": {
            "requested_ranges": ranges,
            "frames_per_range": frames,
            "seed": seed,
            "court_view_gate": "court_diagnostics.rejection_gate(frame) == accepted",
            "selection_note": "Ranges are centered on accepted samples; no new gate was added.",
        },
        "ranges": results,
        "summary": {
            "selected_ranges": len(results),
            "passing_ranges": passed,
            "pass_fraction": passed / len(results) if results else None,
            "selection_shortfall": len(results) < ranges,
        },
    }


def main() -> int:
    """Write one deterministic sequential-plan JSON report for one video."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ranges", type=int, default=5)
    parser.add_argument("--frames", type=int, default=300)
    explicit = parser.add_mutually_exclusive_group()
    explicit.add_argument("--range", nargs=2, type=int, metavar=("START", "STOP"))
    explicit.add_argument("--range-seconds", nargs=2, type=float, metavar=("START", "STOP"))
    args = parser.parse_args()
    source = probe_source(args.video)
    selected = None
    fps = source["source_fps"]
    if args.range_seconds:
        if not isinstance(fps, float):
            parser.error("--range-seconds requires a readable source fps")
        selected = [seconds_to_frames(*args.range_seconds, fps)]
        print("range seconds %.3f-%.3f equals frames %d-%d at %.3f fps" % (
            *args.range_seconds, *selected[0], fps))
    elif args.range:
        selected = [tuple(args.range)]
        if isinstance(fps, float):
            seconds = frames_to_seconds(*selected[0], fps)
            print("range frames %d-%d equals seconds %.3f-%.3f at %.3f fps" % (
                *selected[0], *seconds, fps))
    report = build_report(args.video, args.ranges, args.frames, selected=selected)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "sequential_plan.json"
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("wrote", path, "ranges", report["summary"]["selected_ranges"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
