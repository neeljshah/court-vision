"""Measure prefetch-cache frame identity without changing production modules."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, deque
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Mapping, Sequence

SOURCE_FRAMES = (474, 1377)
_SURVIVOR_COLUMNS = ("player_id", "team", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2")


def _csv_hash(path: Path) -> str:
    """Return the SHA-256 digest of one emitted CSV."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _survivors(rows: Sequence[Mapping[str, str]], frame: int) -> list[list[str]]:
    """Return source-frame rows in a stable, complete display order."""
    values = [
        [row[column] for column in _SURVIVOR_COLUMNS]
        for row in rows
        if row["frame"] == str(frame)
    ]
    return sorted(values, key=lambda item: (int(item[0]), item[1], *item[2:]))


def measure_directory(data_dir: Path) -> dict[str, Any]:
    """Recount full route outputs using G195's fixed, unfiltered record shape."""
    with (data_dir / "tracking_data.csv").open(newline="", encoding="utf-8") as handle:
        player_rows = list(csv.DictReader(handle))
    with (data_dir / "ball_tracking.csv").open(newline="", encoding="utf-8") as handle:
        ball_rows = list(csv.DictReader(handle))
    return {
        "data_dir": str(data_dir),
        "player_rows": len(player_rows),
        "distinct_player_row_frames": len({row["frame"] for row in player_rows}),
        "eligible_denominator_attempted_gameplay_frames": len(
            {row["frame"] for row in ball_rows}
        ),
        "survivors": {str(frame): _survivors(player_rows, frame) for frame in SOURCE_FRAMES},
        "tracking_data_csv_sha256": _csv_hash(data_dir / "tracking_data.csv"),
        "ball_tracking_csv_sha256": _csv_hash(data_dir / "ball_tracking.csv"),
    }


def histogram(values: Sequence[int]) -> dict[str, int]:
    """Return a JSON-stable whole-run histogram."""
    return {str(key): count for key, count in sorted(Counter(values).items())}


def summarize_observation(
    per_frame: Sequence[Mapping[str, Any]], peek_return_counts: Sequence[int]
) -> dict[str, Any]:
    """Summarize every observed consumer call without filtering any frame."""
    cache_rows = [row for row in per_frame if row["inference_mode"] == "cache"]
    self_rows = [row for row in per_frame if row["inference_mode"] == "self_inferred"]
    offsets = [int(row["served_frame_idx"]) - int(row["processed_frame_idx"])
               for row in cache_rows if row["served_frame_idx"] is not None]
    return {
        "get_players_pos_calls": len(per_frame),
        "cache_served_frames": len(cache_rows),
        "self_inferred_frames": len(self_rows),
        "cache_source_unmatched_frames": sum(
            row["served_frame_idx"] is None for row in cache_rows
        ),
        "offset_histogram_served_minus_processed": histogram(offsets),
        "peek_return_count_histogram": histogram(list(peek_return_counts)),
    }


def control_comparison(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compare exactly three control runs on the requested cache-count metrics."""
    if len(records) != 3:
        raise ValueError("G198 compares exactly three runs per arm")
    observations = [record["observation"] for record in records]
    for key in ("cache_served_frames", "self_inferred_frames"):
        if any(key not in observation for observation in observations):
            raise ValueError(f"missing observation metric: {key}")
    return {
        "run_count": len(records),
        "cache_served_counts_identical_across_three_runs": len({
            observation["cache_served_frames"] for observation in observations
        }) == 1,
        "self_inferred_counts_identical_across_three_runs": len({
            observation["self_inferred_frames"] for observation in observations
        }) == 1,
        "peek_return_histograms_identical_across_three_runs": len({
            json.dumps(observation["peek_return_count_histogram"], sort_keys=True)
            for observation in observations
        }) == 1,
        "offset_histograms_identical_across_three_runs": len({
            json.dumps(observation["offset_histogram_served_minus_processed"], sort_keys=True)
            for observation in observations
        }) == 1,
    }


def arm_comparison(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply G195's complete-route-output identity rule to three G198 runs."""
    if len(records) != 3:
        raise ValueError("G198 compares exactly three runs per arm")
    route_keys = (
        "player_rows",
        "distinct_player_row_frames",
        "eligible_denominator_attempted_gameplay_frames",
        "survivors",
        "tracking_data_csv_sha256",
        "ball_tracking_csv_sha256",
    )
    comparable = [{key: record[key] for key in route_keys} for record in records]
    encoded = [json.dumps(record, sort_keys=True, separators=(",", ":")) for record in comparable]
    return {
        "run_count": len(records),
        "identical_across_three_runs": len(set(encoded)) == 1,
        "comparison_includes_complete_csv_hashes": True,
    }


class PrefetchObserver:
    """Parallel-only source-index bookkeeping for one monkey-patched route run."""

    def __init__(self) -> None:
        self.peek_return_counts: list[int] = []
        self.peek_index_batches: deque[list[int]] = deque()
        self.cached_source_indices: deque[int] = deque()
        self.per_frame: list[dict[str, Any]] = []
        self.prefetch_batches: list[dict[str, Any]] = []

    def record_peek(self, indices: list[int], returned_count: int) -> None:
        """Record one non-blocking peek and its source-index snapshot."""
        self.peek_return_counts.append(returned_count)
        if returned_count:
            self.peek_index_batches.append(indices[:returned_count])

    def begin_prefetch(self, frame_count: int) -> None:
        """Pair the next prefetch with the preceding peek without altering its deque."""
        indices = self.peek_index_batches.popleft() if self.peek_index_batches else []
        selected = indices[:frame_count]
        self.cached_source_indices.extend(selected)
        self.prefetch_batches.append({
            "requested_frame_count": frame_count,
            "source_frame_indices": selected,
            "source_index_count_matches_requested": len(selected) == frame_count,
        })

    def record_consumer(self, processed_frame_idx: int, cache_available: bool) -> None:
        """Record the exact source identity that the original consumer will use."""
        source = self.cached_source_indices.popleft() if cache_available and self.cached_source_indices else None
        self.per_frame.append({
            "processed_frame_idx": processed_frame_idx,
            "inference_mode": "cache" if cache_available else "self_inferred",
            "served_frame_idx": source if cache_available else processed_frame_idx,
            "served_source_index_matched": source is not None if cache_available else True,
        })


def install_measurement_wrappers(*, bypass_prefetch: bool) -> PrefetchObserver:
    """Patch classes only in the current Python process and return its observer."""
    from src.pipeline.unified_pipeline import _FramePrefetcher
    from src.tracking.advanced_tracker import AdvancedFeetDetector

    observer = PrefetchObserver()
    original_peek = _FramePrefetcher.peek
    original_prefetch = AdvancedFeetDetector.prefetch_yolo
    original_get_players_pos = AdvancedFeetDetector.get_players_pos

    def wrapped_peek(prefetcher: Any, n: int = 7) -> list[Any]:
        with prefetcher._q.mutex:
            indices = [
                frame_idx for ok, frame, frame_idx in list(prefetcher._q.queue)[:n]
                if ok and frame is not None
            ]
        frames = original_peek(prefetcher, n)
        observer.record_peek(indices, len(frames))
        return frames

    def wrapped_prefetch(tracker: Any, frames: Sequence[Any], *args: Any, **kwargs: Any) -> None:
        observer.begin_prefetch(len(frames))
        if bypass_prefetch:
            return None
        return original_prefetch(tracker, frames, *args, **kwargs)

    def wrapped_get_players_pos(tracker: Any, *args: Any, **kwargs: Any) -> Any:
        thread = tracker._prefetch_thread
        if thread is not None and thread.is_alive():
            thread.join()
        with tracker._prefetch_lock:
            cache_available = bool(tracker._yolo_result_buf)
        processed_frame_idx = int(args[3])
        observer.record_consumer(processed_frame_idx, cache_available)
        return original_get_players_pos(tracker, *args, **kwargs)

    _FramePrefetcher.peek = wrapped_peek
    AdvancedFeetDetector.prefetch_yolo = wrapped_prefetch
    AdvancedFeetDetector.get_players_pos = wrapped_get_players_pos
    return observer


def run_route(
    *, arm: str, video: Path, data_dir: Path, frames: int, route_log: Path
) -> dict[str, Any]:
    """Run the fixed route once with process-local wrappers and return all records."""
    if arm not in {"control", "bypass"}:
        raise ValueError(f"unknown G198 arm: {arm}")
    import runpy
    import sys

    from src.pipeline.unified_pipeline import UnifiedPipeline

    observer = install_measurement_wrappers(bypass_prefetch=arm == "bypass")
    if arm == "bypass":
        original_init = UnifiedPipeline.__init__

        def init_with_tuner_off(instance: Any, *args: Any, **kwargs: Any) -> None:
            original_init(instance, *args, **kwargs)
            import torch
            torch.backends.cudnn.benchmark = False

        UnifiedPipeline.__init__ = init_with_tuner_off

    saved_argv = sys.argv[:]
    data_dir.mkdir(parents=True, exist_ok=False)
    sys.argv = [
        "scripts/run_clip.py",
        "--video", str(video),
        "--frames", str(frames),
        "--no-show",
        "--skip-features",
        "--data-dir", str(data_dir),
    ]
    try:
        with route_log.open("w", encoding="utf-8") as handle:
            with redirect_stdout(handle), redirect_stderr(handle):
                runpy.run_path("scripts/run_clip.py", run_name="__main__")
    finally:
        sys.argv = saved_argv

    record = measure_directory(data_dir)
    record.update({
        "arm": arm,
        "observation": summarize_observation(observer.per_frame, observer.peek_return_counts),
        "per_frame": observer.per_frame,
        "prefetch_batches": observer.prefetch_batches,
    })
    return record


def main() -> None:
    """Execute one G198 process-local measurement and write its JSON record."""
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=("control", "bypass"), required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--record-path", type=Path, required=True)
    parser.add_argument("--route-log", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1200)
    args = parser.parse_args()
    record = run_route(
        arm=args.arm,
        video=args.video,
        data_dir=args.data_dir,
        frames=args.frames,
        route_log=args.route_log,
    )
    args.record_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    print(json.dumps({"record_path": str(args.record_path), "status": "ok"}, sort_keys=True))


if __name__ == "__main__":
    main()
