"""Measure soccer S1 tracker churn on sequential ten-second video windows."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Callable, Sequence

import cv2
import numpy as np

from domains.soccer.tracking.adapter import SoccerAdapter

WINDOWS_PER_CLIP = 5
WINDOW_SECONDS = 10
SEED = 20260902
AdapterFactory = Callable[[object], SoccerAdapter]


def select_window_starts(total_frames: int, window_frames: int, count: int, seed: int) -> list[int]:
    """Choose one seeded start from each timeline stratum without overlap when possible."""
    if total_frames < window_frames:
        raise ValueError("clip has %d frames, shorter than one %d-frame window" % (total_frames, window_frames))
    if count < 1:
        raise ValueError("window count must be positive")
    last_start = total_frames - window_frames
    edges = np.linspace(0, last_start + 1, count + 1, dtype=int)
    rng = np.random.default_rng(seed)
    return [int(rng.integers(edges[i], max(edges[i] + 1, edges[i + 1]))) for i in range(count)]


def _detector() -> object:
    """Load the G22 fixed-seed detector when its merged helper is available."""
    try:
        from scripts.platformkit.detection.deterministic import build_soccer_packet_detector
    except ImportError:
        return SoccerAdapter().detector
    return build_soccer_packet_detector()


def _safe_name(path: Path) -> str:
    return path.stem.replace("soccer__", "").replace(" ", "_")


def _render(frame: np.ndarray, tracks: Sequence[tuple[int, np.ndarray]], path: Path) -> None:
    image = frame.copy()
    for track_id, point in tracks:
        x, y = (int(round(float(value))) for value in point)
        cv2.circle(image, (x, y), 4, (0, 255, 0), -1)
        cv2.putText(image, str(track_id), (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (0, 255, 0), 1, cv2.LINE_AA)
    if not cv2.imwrite(str(path), image):
        raise RuntimeError("could not write render: %s" % path)


def _lock(adapter: SoccerAdapter, frame: np.ndarray, ordinal: int) -> tuple[int, int]:
    """Return accepted and attempted calibration counts without changing adapter policy."""
    solve = getattr(adapter, "_stable_homography", None)
    landmarks = getattr(adapter, "_landmark_detections", None)
    stride = int(getattr(adapter, "calibration_stride", 1))
    if not callable(solve) or not callable(landmarks) or ordinal % stride:
        return 0, 0
    homography = solve(landmarks(frame), frame.shape[:2])
    if homography is not None:
        adapter._homography = homography
        return 1, 1
    return 0, 1


def measure_window(video: Path, start_frame: int, window_frames: int, detector: object,
                   renders_dir: Path, clip: str, ordinal: int,
                   adapter_factory: AdapterFactory = SoccerAdapter) -> dict[str, object]:
    """Run one adapter instance over sequential frames and return its window metrics."""
    adapter = adapter_factory(detector)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("could not open video: %s" % video)
    capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frame_counts: list[int] = []
    ids: set[int] = set()
    locks = attempts = 0
    try:
        for relative in range(window_frames):
            ok, frame = capture.read()
            if not ok:
                break
            tracks = adapter.detect_players_image_space(frame)
            frame_counts.append(len(tracks))
            ids.update(int(track_id) for track_id, _ in tracks)
            accepted, tried = _lock(adapter, frame, relative)
            locks += accepted
            attempts += tried
            if relative in (0, window_frames - 1):
                _render(frame, tracks, renders_dir / ("%s_w%02d_%s.jpg" %
                                                      (clip, ordinal, "first" if relative == 0 else "last")))
    finally:
        capture.release()
    decoded = len(frame_counts)
    mean_boxes = sum(frame_counts) / decoded if decoded else 0.0
    new_ids_per_frame = len(ids) / decoded if decoded else 0.0
    return {
        "clip": clip, "window": ordinal, "start_frame": start_frame,
        "frames_decoded": decoded, "mean_raw_person_boxes_per_frame": mean_boxes,
        "distinct_track_ids": len(ids), "new_ids_per_frame": new_ids_per_frame,
        "id_churn_ratio": new_ids_per_frame / mean_boxes if mean_boxes else 0.0,
        "fraction_frames_ge_14_boxes": (sum(count >= 14 for count in frame_counts) / decoded if decoded else 0.0),
        "homography_lock_rate": (locks / attempts if attempts else None),
        "homography_lock_attempts": attempts,
    }


def build_stream_packet(videos: Sequence[Path], output_dir: Path, seed: int = SEED,
                        windows: int = WINDOWS_PER_CLIP, seconds: int = WINDOW_SECONDS,
                        detector: object | None = None,
                        adapter_factory: AdapterFactory = SoccerAdapter) -> list[dict[str, object]]:
    """Measure fixed, spread stream windows for every supplied soccer S1 clip."""
    output_dir.mkdir(parents=True, exist_ok=True)
    renders_dir = output_dir / "renders"
    renders_dir.mkdir(exist_ok=True)
    shared_detector = _detector() if detector is None else detector
    rows: list[dict[str, object]] = []
    sources: list[dict[str, object]] = []
    for clip_number, video in enumerate(videos):
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise FileNotFoundError("could not open video: %s" % video)
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        capture.release()
        if fps <= 0:
            raise ValueError("video has no positive FPS: %s" % video)
        window_frames = max(1, round(fps * seconds))
        starts = select_window_starts(total, window_frames, windows, seed + clip_number)
        clip = _safe_name(video)
        sources.append({"clip": clip, "path": str(video), "fps": fps, "total_frames": total,
                        "window_frames": window_frames, "starts": starts})
        for ordinal, start in enumerate(starts, start=1):
            rows.append(measure_window(video, start, window_frames, shared_detector, renders_dir,
                                       clip, ordinal, adapter_factory))
    fields = list(rows[0]) if rows else []
    csv_path = output_dir / "soccer_s1_stream_windows.csv"
    with csv_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest = {"seed": seed, "window_seconds": seconds, "windows_per_clip": windows,
                "decode": "cv2.VideoCapture sequential frames", "detector": "G22 deterministic helper when available",
                "sources": sources, "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest()}
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="ascii")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("videos", nargs="+", type=Path)
    args = parser.parse_args()
    rows = build_stream_packet(args.videos, args.output_dir, seed=args.seed)
    print(json.dumps({"windows": len(rows), "output_dir": str(args.output_dir)}))


if __name__ == "__main__":
    main()
