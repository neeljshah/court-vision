"""Local-only forced-control probes for G228; production modules stay unchanged."""

from __future__ import annotations

import contextlib
import io
import json
from collections import deque
from typing import Any, Callable

import numpy as np


def _pipeline_module() -> Any:
    """Import the production module with the local NumPy compatibility shim."""
    if "bool8" not in np.__dict__:
        np.bool8 = np.bool_  # type: ignore[attr-defined]
    from src.pipeline import unified_pipeline

    return unified_pipeline


def _capture(call: Callable[[], Any]) -> dict[str, Any]:
    """Return a call result plus only its direct Python stream signals."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        value = call()
    return {"value": value, "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def m1_sanity_observation(*, force_sanity_failure: bool) -> dict[str, Any]:
    """Exercise M1 recovery with a clean or forced sanity-transform outcome."""
    pipeline = _pipeline_module()
    candidate = np.eye(3, dtype=np.float64)
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    subject = type("M1Subject", (), {})()
    subject._M1_stale_frames = 30
    subject._last_good_M1 = None
    subject._M1_failed_attempts = 0
    subject._recover_frame_buf = deque([frame] * 5, maxlen=5)
    subject._M_ema = np.eye(3, dtype=np.float64)
    subject._M1_raw_clip = None
    subject.M1 = np.full((3, 3), -1.0, dtype=np.float64)

    original_detect = pipeline.detect_court_homography
    original_transform = pipeline.cv2.perspectiveTransform

    def detect(_: list[np.ndarray]) -> np.ndarray:
        return candidate.copy()

    def fail_transform(*_: Any, **__: Any) -> np.ndarray:
        raise RuntimeError("G228 forced M1 sanity transform failure")

    pipeline.detect_court_homography = detect
    if force_sanity_failure:
        pipeline.cv2.perspectiveTransform = fail_transform
    try:
        capture = _capture(
            lambda: pipeline.UnifiedPipeline._try_recover_court_M1(subject, frame)
        )
    finally:
        pipeline.detect_court_homography = original_detect
        pipeline.cv2.perspectiveTransform = original_transform
    return {
        "force_sanity_failure": force_sanity_failure,
        "caller_return": capture["value"],
        "python_stdout": capture["stdout"],
        "python_stderr": capture["stderr"],
        "installed_candidate": bool(np.array_equal(subject.M1, candidate)),
        "raw_clip_candidate": bool(np.array_equal(subject._M1_raw_clip, candidate)),
        "last_good_candidate": bool(np.array_equal(subject._last_good_M1, candidate)),
        "failed_attempts": subject._M1_failed_attempts,
        "stale_frames": subject._M1_stale_frames,
    }


class _Results:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def numpy(self) -> np.ndarray:
        return np.asarray(self._rows, dtype=np.float64)


class _Model:
    def __init__(self, rows: list[list[float]] | None, *, fail: bool = False) -> None:
        self._rows = rows
        self._fail = fail

    def predict(self, _: np.ndarray) -> _Results:
        if self._fail:
            raise RuntimeError("G228 forced detector inference failure")
        return _Results(self._rows or [])


def detector_observation(mode: str) -> dict[str, Any]:
    """Exercise detector success, clean-empty, or forced-error behavior."""
    if mode not in {"detection", "clean_empty", "forced_failure"}:
        raise ValueError("mode must be detection, clean_empty, or forced_failure")
    pipeline = _pipeline_module()
    detector = pipeline.YoloDetector()
    row = [[10.0, 20.0, 30.0, 40.0, 0.9, 3.0]]
    detector.model = _Model(
        row if mode == "detection" else [], fail=mode == "forced_failure"
    )
    capture = _capture(lambda: detector.predict(np.zeros((16, 16, 3), dtype=np.uint8)))
    result = capture["value"]
    return {
        "mode": mode,
        "caller_return": result,
        "returned_detection_count": len(result),
        "python_stdout": capture["stdout"],
        "python_stderr": capture["stderr"],
        "available_before_call": detector.available,
    }


def unavailable_detector_observation() -> dict[str, Any]:
    """Record the ordinary no-weight early return without entering inference."""
    pipeline = _pipeline_module()
    detector = pipeline.YoloDetector()
    capture = _capture(lambda: detector.predict(np.zeros((16, 16, 3), dtype=np.uint8)))
    result = capture["value"]
    return {
        "available_before_call": detector.available,
        "caller_return": result,
        "returned_detection_count": len(result),
        "python_stdout": capture["stdout"],
        "python_stderr": capture["stderr"],
    }


def run_forced_controls() -> dict[str, Any]:
    """Run each G228 forced failure beside its clean control in one process."""
    return {
        "m1_clean_control": m1_sanity_observation(force_sanity_failure=False),
        "m1_forced_failure": m1_sanity_observation(force_sanity_failure=True),
        "detector_clean_detection": detector_observation("detection"),
        "detector_clean_empty_control": detector_observation("clean_empty"),
        "detector_forced_failure": detector_observation("forced_failure"),
        "detector_no_weight_configuration": unavailable_detector_observation(),
    }


def main() -> None:
    """Print JSON evidence for the two in-process forced-control pairs."""
    print(json.dumps(run_forced_controls(), sort_keys=True))


if __name__ == "__main__":
    main()
