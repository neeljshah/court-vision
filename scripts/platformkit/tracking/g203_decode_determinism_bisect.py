"""Measure G203 decoder byte identity without modifying production modules."""

from __future__ import annotations

import hashlib
import inspect
import json
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout
from itertools import zip_longest
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


HANDLER_NAMES = (
    "decord_dlpack",
    "decord_sequential",
    "decord_outer",
    "decode_loop",
)


def compare_runs(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare three ordered per-frame hash records against the first run."""
    if len(records) != 3:
        raise ValueError("G203 requires exactly three runs")
    baseline = list(records[0]["frames"])
    comparisons = []
    for record in records:
        candidate = list(record["frames"])
        differences = []
        for left, right in zip_longest(baseline, candidate):
            if left == right:
                continue
            index = (left or right)["frame_index"]
            differences.append(int(index))
        comparisons.append({
            "frames_hashed": len(candidate),
            "hashes_differ_from_run_1": len(differences),
            "first_differing_frame_index": differences[0] if differences else None,
        })
    return {
        "run_count": len(records),
        "per_frame_hash_sequences_identical_across_three_runs": all(
            item["hashes_differ_from_run_1"] == 0 for item in comparisons
        ),
        "per_run": comparisons,
    }


def decoder_summary(frames: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize served decoders in delivery order."""
    paths = [str(frame["decoder"]) for frame in frames]
    changes = sum(left != right for left, right in zip(paths, paths[1:]))
    return {
        "decoder_paths": sorted(set(paths)),
        "decoder_path_changed_mid_run": changes > 0,
        "decoder_path_change_count": changes,
    }


class DecodeObserver:
    """Observe frame bytes, decoder selection, and named silent handlers."""

    def __init__(self, pipeline: Any) -> None:
        self.frames: list[dict[str, Any]] = []
        self.frame_decoder: dict[int, str] = {}
        self.pyav_active = False
        self.handler_firings = {name: 0 for name in HANDLER_NAMES}
        self._source_file = Path(pipeline.__file__).resolve()
        self._source_filename = str(self._source_file)
        self._handler_lines = self._find_handler_lines(pipeline)

    @staticmethod
    def _find_handler_lines(pipeline: Any) -> dict[int, str]:
        source, start = inspect.getsourcelines(pipeline._decord_frame_iter)
        decode_source, decode_start = inspect.getsourcelines(
            pipeline._FramePrefetcher._decode_loop
        )

        def locate(lines: list[str], first_line: int, needle: str) -> int:
            matches = [first_line + index for index, line in enumerate(lines) if needle in line]
            if len(matches) != 1:
                raise RuntimeError(f"cannot uniquely locate G203 handler: {needle}")
            return matches[0]

        return {
            locate(source, start, "pass  # DLPack not supported"): "decord_dlpack",
            locate(source, start, "pass  # decord unavailable or GPU context failed"): "decord_outer",
        }

    def install_trace(self, pipeline: Any) -> None:
        """Trace exact silent-handler body lines in main and new worker threads."""
        source, start = inspect.getsourcelines(pipeline._decord_frame_iter)
        sequential = next(
            start + index + 1
            for index, line in enumerate(source)
            if line.strip() == "except Exception:"
            and index + 1 < len(source)
            and source[index + 1].strip() == "continue"
        )
        decode_source, decode_start = inspect.getsourcelines(
            pipeline._FramePrefetcher._decode_loop
        )
        decode_loop_pass = next(
            decode_start + index
            for index, line in enumerate(decode_source)
            if line.strip() == "pass"
        )
        self._handler_lines[sequential] = "decord_sequential"
        self._handler_lines[decode_loop_pass] = "decode_loop"

        def trace(frame: Any, event: str, arg: Any) -> Any:
            if event == "call":
                if (
                    frame.f_code.co_filename == self._source_filename
                    and frame.f_code.co_name in {"_decord_frame_iter", "_decode_loop"}
                ):
                    return trace
                return None
            if event == "line":
                name = self._handler_lines.get(frame.f_lineno)
                if name is not None:
                    self.handler_firings[name] += 1
            return trace

        sys.settrace(trace)
        threading.settrace(trace)

    def record(self, frame_index: int, frame: Any) -> None:
        """Store one delivered frame's raw-byte digest and serving decoder."""
        self.frames.append({
            "frame_index": int(frame_index),
            "sha256": hashlib.sha256(frame.tobytes(order="C")).hexdigest(),
            "decoder": self.frame_decoder.get(int(frame_index), "decord"),
        })


def install_decode_wrappers(observer: DecodeObserver) -> Any:
    """Patch decoder symbols only in this one measurement process."""
    import src.pipeline.unified_pipeline as pipeline

    original_pyav = pipeline._pyav_frame_iter
    original_decord = pipeline._decord_frame_iter

    def wrapped_pyav(*args: Any, **kwargs: Any) -> Iterable[Any]:
        observer.pyav_active = True
        try:
            yield from original_pyav(*args, **kwargs)
        finally:
            observer.pyav_active = False

    def wrapped_decord(*args: Any, **kwargs: Any) -> Iterable[Any]:
        for frame_index, frame, fps, total in original_decord(*args, **kwargs):
            observer.frame_decoder[int(frame_index)] = (
                "pyav" if observer.pyav_active else "decord"
            )
            yield frame_index, frame, fps, total

    pipeline._pyav_frame_iter = wrapped_pyav
    pipeline._decord_frame_iter = wrapped_decord
    return pipeline


def _result(observer: DecodeObserver, part: str) -> dict[str, Any]:
    attempted = (
        sum(frame["frame_index"] % 3 == 0 for frame in observer.frames)
        if part == "isolation" else len(observer.frames)
    )
    return {
        "part": part,
        "frames": observer.frames,
        "frames_hashed": len(observer.frames),
        "eligible_denominator_attempted_gameplay_frames": attempted,
        "handler_firings": observer.handler_firings,
        "decoder": decoder_summary(observer.frames),
    }


def run_isolation(video: Path, source_frames: int) -> dict[str, Any]:
    """Hash all raw frames yielded by the production decode iterator."""
    import src.pipeline.unified_pipeline as pipeline

    observer = DecodeObserver(pipeline)
    observer.install_trace(pipeline)
    pipeline = install_decode_wrappers(observer)
    for frame_index, frame, _fps, _total in pipeline._decord_frame_iter(
        str(video), 0, max_source_frames=source_frames
    ):
        observer.record(frame_index, frame)
    return _result(observer, "isolation")


def run_route(video: Path, data_dir: Path, route_log: Path, frames: int) -> dict[str, Any]:
    """Hash frames at the production tracking loop's prefetch consumer point."""
    import runpy
    import src.pipeline.unified_pipeline as pipeline

    observer = DecodeObserver(pipeline)
    observer.install_trace(pipeline)
    pipeline = install_decode_wrappers(observer)
    original_read = pipeline._FramePrefetcher.read

    def wrapped_read(prefetcher: Any) -> Any:
        item = original_read(prefetcher)
        ok, frame, frame_index = item
        if ok:
            observer.record(frame_index, frame)
        return item

    pipeline._FramePrefetcher.read = wrapped_read
    saved_argv = sys.argv[:]
    data_dir.mkdir(parents=True, exist_ok=False)
    sys.argv = [
        "scripts/run_clip.py", "--video", str(video), "--frames", str(frames),
        "--no-show", "--skip-features", "--data-dir", str(data_dir),
    ]
    try:
        with route_log.open("w", encoding="utf-8") as handle:
            with redirect_stdout(handle), redirect_stderr(handle):
                runpy.run_path("scripts/run_clip.py", run_name="__main__")
    finally:
        sys.argv = saved_argv
    return _result(observer, "route")


def main() -> None:
    """Run one fresh-process G203 arm and persist its complete JSON record."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--part", choices=("isolation", "route"), required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--record-path", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--route-log", type=Path)
    parser.add_argument("--frames", type=int, default=1200)
    args = parser.parse_args()
    if args.part == "isolation":
        record = run_isolation(args.video, args.frames)
    else:
        if args.data_dir is None or args.route_log is None:
            parser.error("route requires --data-dir and --route-log")
        record = run_route(args.video, args.data_dir, args.route_log, args.frames)
    args.record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    print(json.dumps({"frames_hashed": record["frames_hashed"], "status": "ok"}))


if __name__ == "__main__":
    main()
