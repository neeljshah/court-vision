"""Local-only runtime evidence helpers for G221; production modules stay unchanged."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import warnings
from pathlib import Path
from typing import Any

import cv2
import numpy as np


FRAME_STRIDE_THRESHOLD = 3000
BASE_STRIDE = 3


def file_size_estimate(path: Path) -> int:
    """Return the production file-size fallback estimate."""
    return int(path.stat().st_size / 250_000)


def implied_stride(frame_count: int, base_stride: int = BASE_STRIDE) -> int:
    """Apply the unchanged production frame-count threshold rule."""
    return base_stride if frame_count > FRAME_STRIDE_THRESHOLD else 1


def selected_count_source(cv2_count: int, pyav_count: int | None) -> str:
    """Return the production's first usable count source name."""
    if cv2_count:
        return "cv2"
    if pyav_count:
        return "pyav"
    return "file_size"


def _rate(value: str) -> float:
    numerator, denominator = value.split("/", 1)
    return float(numerator) / float(denominator)


def approximate_truth(path: Path) -> dict[str, Any]:
    """Use ffprobe duration times average frame rate without decoding frames."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,duration",
        "-show_entries", "format=duration", "-of", "json", str(path),
    ]
    completed = subprocess.run(command, capture_output=True, check=True, text=True)
    payload = json.loads(completed.stdout)
    stream = payload["streams"][0]
    duration = float(stream.get("duration") or payload["format"]["duration"])
    fps = _rate(stream["avg_frame_rate"])
    return {
        "method": "ffprobe_metadata_duration_x_avg_fps_approximate_no_frame_decode",
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "duration_seconds": duration,
        "avg_fps": fps,
        "approximate_frame_count": int(round(duration * fps)),
    }


def pyav_frame_count(path: Path) -> tuple[int | None, str | None]:
    """Read PyAV's stream frame metadata, preserving an unavailable-runtime error."""
    try:
        import av  # type: ignore

        container = av.open(str(path))
        try:
            return int(container.streams.video[0].frames or 0), None
        finally:
            container.close()
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def count_sources(path: Path) -> dict[str, Any]:
    """Census production count sources and the exact branch selection rule."""
    capture = cv2.VideoCapture(str(path))
    try:
        cv2_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        capture.release()
    pyav_count, pyav_error = pyav_frame_count(path)
    size_count = file_size_estimate(path)
    source = selected_count_source(cv2_count, pyav_count)
    selected_count = {
        "cv2": cv2_count,
        "pyav": pyav_count,
        "file_size": size_count,
    }[source]
    assert isinstance(selected_count, int)
    return {
        "path": str(path.resolve()),
        "bytes": path.stat().st_size,
        "cv2_frame_count": cv2_count,
        "pyav_stream_frames": pyav_count,
        "pyav_error": pyav_error,
        "file_size_estimate": size_count,
        "ground_truth": approximate_truth(path),
        "production_selected_source": source,
        "production_selected_count": selected_count,
        "production_selected_stride": implied_stride(selected_count),
        "cv2_implied_stride": implied_stride(cv2_count),
        "pyav_implied_stride": implied_stride(pyav_count) if pyav_count is not None else None,
        "file_size_implied_stride": implied_stride(size_count),
    }


def prefetch_observation(path: Path, max_source_frames: int) -> dict[str, Any]:
    """Consume one bounded production prefetcher until its sentinel is observed."""
    if max_source_frames < 1:
        raise ValueError("max_source_frames must be positive")
    if "bool8" not in np.__dict__:
        np.bool8 = np.bool_  # type: ignore[attr-defined]
    from src.pipeline.unified_pipeline import _FramePrefetcher

    stdout, stderr = io.StringIO(), io.StringIO()
    caught: str | None = None
    emitted: list[int] = []
    sentinel: tuple[bool, bool, int] | None = None
    caught_warnings: list[str] = []
    with warnings.catch_warnings(record=True) as observed_warnings:
        warnings.simplefilter("always")
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                prefetcher = _FramePrefetcher(
                    str(path), queue_size=4, max_source_frames=max_source_frames
                )
                while True:
                    ok, frame, frame_index = prefetcher.read()
                    if not ok:
                        sentinel = (bool(ok), frame is None, int(frame_index))
                        break
                    emitted.append(int(frame_index))
                    del frame
        except Exception as exc:
            caught = f"{type(exc).__name__}: {exc}"
        caught_warnings = [str(item.message) for item in observed_warnings]
    return {
        "path": str(path.resolve()),
        "max_source_frames": max_source_frames,
        "frames_emitted": len(emitted),
        "first_frame_index": emitted[0] if emitted else None,
        "last_frame_index": emitted[-1] if emitted else None,
        "sentinel": sentinel,
        "exception_surfaced_to_consumer": caught,
        "python_stdout": stdout.getvalue(),
        "python_stderr": stderr.getvalue(),
        "python_warnings": caught_warnings,
    }


def main() -> None:
    """Run exactly one census or one bounded production-prefetcher observation."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("census", "prefetch"), required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--max-source-frames", type=int, default=1200)
    args = parser.parse_args()
    result = (
        count_sources(args.video)
        if args.mode == "census"
        else prefetch_observation(args.video, args.max_source_frames)
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
