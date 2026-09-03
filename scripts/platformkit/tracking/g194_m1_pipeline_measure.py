"""Read-only in-process recorder for G194's pipeline M1 branch measurement."""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np


def matrix_values(matrix: np.ndarray | None) -> list[list[float]] | None:
    """Return a JSON-safe matrix without changing its values."""
    return None if matrix is None else np.asarray(matrix, dtype=float).tolist()


def matrix_comparison(used: np.ndarray | None, static: np.ndarray) -> dict[str, Any]:
    """Compare a used M1 with the static resource element by element."""
    if used is None:
        return {"available": False, "equal_elementwise": False, "max_abs_delta": None}
    used_array = np.asarray(used)
    equal = bool(np.array_equal(used_array, static))
    return {
        "available": True,
        "equal_elementwise": equal,
        "max_abs_delta": float(np.max(np.abs(used_array - static))),
    }


def _state(pipeline: Any) -> dict[str, Any]:
    return {
        "M1": matrix_values(getattr(pipeline, "M1", None)),
        "last_good_M1": matrix_values(getattr(pipeline, "_last_good_M1", None)),
        "M1_raw_clip": matrix_values(getattr(pipeline, "_M1_raw_clip", None)),
        "M1_failed_attempts": int(getattr(pipeline, "_M1_failed_attempts", -1)),
        "M1_stale_frames": int(getattr(pipeline, "_M1_stale_frames", -1)),
    }


def _draw_court_model(frame: np.ndarray, frame_to_court: np.ndarray) -> np.ndarray:
    """Project a small 940x500 court-line model back onto a video frame."""
    overlay = frame.copy()
    try:
        court_to_frame = np.linalg.inv(frame_to_court)
        lines = (
            [(0, 0), (940, 0), (940, 500), (0, 500), (0, 0)],
            [(470, 0), (470, 500)],
            [(0, 190), (160, 190), (160, 310), (0, 310)],
            [(940, 190), (780, 190), (780, 310), (940, 310)],
        )
        for line in lines:
            points = np.asarray(line, dtype=np.float32).reshape(-1, 1, 2)
            projected = cv2.perspectiveTransform(points, court_to_frame)
            cv2.polylines(overlay, [np.int32(projected)], False, (0, 0, 255), 3, cv2.LINE_AA)
    except np.linalg.LinAlgError:
        cv2.putText(overlay, "G194: non-invertible frame-to-court matrix", (15, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
    return overlay


class M1Recorder:
    """Wrap production call sites in-process and retain only observations."""

    def __init__(self, pipeline_module: Any, detector_module: Any, project: Path) -> None:
        self.pipeline_module = pipeline_module
        self.detector_module = detector_module
        self.project = project
        self.build_calls: list[dict[str, Any]] = []
        self.detector_calls: list[dict[str, Any]] = []
        self.recovery_calls: list[dict[str, Any]] = []
        self.projectable_count = 0
        self.projectable_samples: list[dict[str, Any]] = []
        self.pipeline: Any | None = None
        self.static_m1 = np.load(Path(pipeline_module._RESOURCES) / "Rectify1.npy")

    def install(self) -> dict[str, Any]:
        cls = self.pipeline_module.UnifiedPipeline
        originals = {
            "build": cls._build_court,
            "recover": cls._try_recover_court_M1,
            "get_h": cls._get_homography,
            "run": cls.run,
            "pipeline_detect": self.pipeline_module.detect_court_homography,
            "detector_detect": self.detector_module.detect_court_homography,
        }

        def detect(frames: list[np.ndarray]) -> np.ndarray | None:
            result = originals["detector_detect"](frames)
            self.detector_calls.append({
                "invocation": len(self.detector_calls) + 1,
                "branch": "recovery_fresh_solve",
                "input_frame_count": len(frames),
                "input_shapes": [list(frame.shape) for frame in frames],
                "returned_matrix": result is not None,
                "matrix": matrix_values(result),
            })
            return result

        def build(instance: Any, pano: Any, startup_frames: list | None = None) -> Any:
            before = _state(instance)
            result = originals["build"](instance, pano, startup_frames=startup_frames)
            m1 = result[1]
            branch = "recovery_last_good" if before["last_good_M1"] is not None else "Rectify1.npy_fallback"
            self.build_calls.append({
                "invocation": len(self.build_calls) + 1,
                "startup_frame_count": 0 if startup_frames is None else len(startup_frames),
                "branch": branch,
                "returned_matrix": m1 is not None,
                "returned_M1": matrix_values(m1),
                "equals_Rectify1": matrix_comparison(m1, self.static_m1),
                "before": before,
                "after": _state(instance),
            })
            return result

        def recover(instance: Any, frame: np.ndarray) -> None:
            before_detector_count = len(self.detector_calls)
            before = _state(instance)
            result = originals["recover"](instance, frame)
            calls = self.detector_calls[before_detector_count:]
            if not calls:
                branch = "no_recovery_attempt"
            elif any(call["returned_matrix"] for call in calls):
                branch = "recovery_success"
            else:
                branch = "recovery_failed_kept_existing_M1"
            self.recovery_calls.append({
                "invocation": len(self.recovery_calls) + 1,
                "branch": branch,
                "detector_invocations": [call["invocation"] for call in calls],
                "before": before,
                "after": _state(instance),
            })
            return result

        def get_h(instance: Any, frame: np.ndarray) -> np.ndarray | None:
            result = originals["get_h"](instance, frame)
            if result is not None:
                self.projectable_count += 1
                sample = {
                    "sequence": self.projectable_count,
                    "frame": frame.copy(),
                    "frame_to_court": np.asarray(instance.M1 @ result).copy(),
                    "M1": np.asarray(instance.M1).copy(),
                }
                if not self.projectable_samples:
                    self.projectable_samples.append(sample)
                elif len(self.projectable_samples) == 1:
                    self.projectable_samples.append(sample)
                else:
                    self.projectable_samples[-1] = sample
            return result

        def run(instance: Any) -> dict[str, Any]:
            self.pipeline = instance
            return originals["run"](instance)

        self.pipeline_module.detect_court_homography = detect
        self.detector_module.detect_court_homography = detect
        cls._build_court = build
        cls._try_recover_court_M1 = recover
        cls._get_homography = get_h
        cls.run = run
        return originals

    def restore(self, originals: dict[str, Any]) -> None:
        cls = self.pipeline_module.UnifiedPipeline
        cls._build_court = originals["build"]
        cls._try_recover_court_M1 = originals["recover"]
        cls._get_homography = originals["get_h"]
        cls.run = originals["run"]
        self.pipeline_module.detect_court_homography = originals["pipeline_detect"]
        self.detector_module.detect_court_homography = originals["detector_detect"]

    def write_renders(self, output: Path) -> list[dict[str, Any]]:
        renders: list[dict[str, Any]] = []
        if not self.projectable_samples:
            return renders
        for index, sample in enumerate(self.projectable_samples):
            rendered = _draw_court_model(sample["frame"], sample["frame_to_court"])
            filename = "court_projection_%d_of_%d.jpg" % (sample["sequence"], self.projectable_count)
            if not cv2.imwrite(str(output / filename), rendered):
                raise RuntimeError("could not write render: %s" % filename)
            renders.append({
                "selection": "first" if index == 0 else "last",
                "projectable_sequence": sample["sequence"],
                "total_projectable_samples": self.projectable_count,
                "path": filename,
                "M1": matrix_values(sample["M1"]),
                "frame_to_court": matrix_values(sample["frame_to_court"]),
            })
        return renders


def _hashes(project: Path) -> dict[str, str]:
    paths = ("src/pipeline/unified_pipeline.py", "src/tracking/court_detector.py",
             "src/tracking/advanced_tracker.py")
    return {path: hashlib.sha256((project / path).read_bytes()).hexdigest() for path in paths}


def measure(project: Path, output: Path, clip_args: list[str]) -> dict[str, Any]:
    """Run scripts/run_clip.py unchanged except for temporary observation wrappers."""
    sys.path.insert(0, str(project))
    from src.pipeline import unified_pipeline as pipeline_module
    from src.tracking import court_detector as detector_module

    output.mkdir(parents=True, exist_ok=True)
    recorder = M1Recorder(pipeline_module, detector_module, project)
    originals = recorder.install()
    exit_code = 0
    try:
        sys.argv = [str(project / "scripts/run_clip.py"), *clip_args]
        runpy.run_path(str(project / "scripts/run_clip.py"), run_name="__main__")
    except SystemExit as exc:
        exit_code = int(exc.code or 0)
    finally:
        recorder.restore(originals)
    final = _state(recorder.pipeline) if recorder.pipeline is not None else None
    report = {
        "measurement": "G194 read-only in-process wrappers",
        "project": str(project),
        "clip_args": clip_args,
        "run_clip_exit_code": exit_code,
        "source_sha256": _hashes(project),
        "Rectify1": matrix_values(recorder.static_m1),
        "build_court_invocations": recorder.build_calls,
        "detect_court_homography_invocations": recorder.detector_calls,
        "recovery_invocations": recorder.recovery_calls,
        "final_pipeline_state": final,
        "final_M1_vs_Rectify1": matrix_comparison(
            None if final is None else np.asarray(recorder.pipeline.M1), recorder.static_m1),
        "renders": recorder.write_renders(output),
    }
    (output / "g194_m1_measurement.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("clip_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    clip_args = args.clip_args[1:] if args.clip_args[:1] == ["--"] else args.clip_args
    if not clip_args:
        parser.error("pass the unchanged run_clip arguments after --")
    report = measure(args.project.resolve(), args.output_dir.resolve(), clip_args)
    print(json.dumps({
        "build_calls": len(report["build_court_invocations"]),
        "detector_calls": len(report["detect_court_homography_invocations"]),
        "exit_code": report["run_clip_exit_code"],
        "final_equals_Rectify1": report["final_M1_vs_Rectify1"]["equal_elementwise"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
