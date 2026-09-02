"""Build blind soccer S1 frame packets without producing an adjudication verdict."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Iterable, Sequence

import cv2
import numpy as np

from domains.soccer.tracking.segmenter import is_pitch_view
from scripts.platformkit.detection.deterministic import build_soccer_packet_detector, read_packet_frame


def _safe_name(path: Path) -> str:
    return path.stem.replace("soccer__", "").replace(" ", "_")


def _frame_at(capture: cv2.VideoCapture, frame_index: int) -> np.ndarray:
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    if not ok:
        raise RuntimeError("could not read requested frame %d" % frame_index)
    return frame


def select_spread_indices(indices: Sequence[int], count: int) -> list[int]:
    """Choose unique source-frame indexes evenly across a sorted candidate list."""
    if count < 1:
        raise ValueError("count must be positive")
    if len(indices) < count:
        raise ValueError("only %d pitch-view frames available for %d samples" % (len(indices), count))
    positions = np.linspace(0, len(indices) - 1, count).round().astype(int)
    return [indices[int(position)] for position in positions]


def _pitch_indices(path: Path, scan_points: int = 120) -> list[int]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise FileNotFoundError("could not open video: %s" % path)
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total < 1:
            raise ValueError("video has no frames: %s" % path)
        scan = np.linspace(0, total - 1, min(total, scan_points)).round().astype(int)
        pitch_frames: list[int] = []
        for index in np.unique(scan):
            try:
                frame = _frame_at(capture, int(index))
            except RuntimeError:
                continue
            if is_pitch_view(frame):
                pitch_frames.append(int(index))
        return pitch_frames
    finally:
        capture.release()


def _valid_detection_count(raw_boxes: Iterable[Sequence[float]]) -> int:
    return sum(1 for box in raw_boxes if len(box) >= 4 and float(box[2]) > float(box[0]) and float(box[3]) > float(box[1]))


def _write_contact_sheet(image_paths: Sequence[Path], output_path: Path, columns: int = 3) -> None:
    tiles = []
    for path in image_paths:
        image = cv2.imread(str(path))
        if image is None:
            raise RuntimeError("could not read packet image: %s" % path)
        image = cv2.resize(image, (480, 270))
        canvas = np.full((300, 480, 3), 255, dtype=np.uint8)
        canvas[:270] = image
        cv2.putText(canvas, path.stem, (10, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(canvas)
    rows = math.ceil(len(tiles) / columns)
    blank = np.full_like(tiles[0], 255)
    tiles.extend([blank] * (rows * columns - len(tiles)))
    sheet = np.vstack([np.hstack(tiles[start:start + columns]) for start in range(0, len(tiles), columns)])
    if not cv2.imwrite(str(output_path), sheet):
        raise RuntimeError("could not write contact sheet: %s" % output_path)


def render_content_gate(videos: Sequence[Path], output_dir: Path) -> None:
    """Render two unlabeled, timeline-spread frames per candidate video for visual gating."""
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[Path] = []
    for video in videos:
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise FileNotFoundError("could not open video: %s" % video)
        try:
            total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            for ordinal, fraction in enumerate((0.2, 0.7), start=1):
                frame = _frame_at(capture, min(total - 1, round((total - 1) * fraction)))
                image_path = output_dir / ("%s_gate_%d.jpg" % (_safe_name(video), ordinal))
                if not cv2.imwrite(str(image_path), frame):
                    raise RuntimeError("could not write content-gate image: %s" % image_path)
                rendered.append(image_path)
        finally:
            capture.release()
    _write_contact_sheet(rendered, output_dir / "content_gate_sheet.jpg", columns=2)


def build_packet(videos: Sequence[Path], output_dir: Path, frames_per_clip: int) -> None:
    """Write blind sheets, a blank label CSV, and a separately held detector-count CSV."""
    if len(videos) < 3:
        raise ValueError("at least three genuine soccer videos are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    detector = build_soccer_packet_detector()
    labels: list[dict[str, str]] = []
    detector_counts: list[dict[str, str]] = []
    next_id = 1
    for video in videos:
        clip = _safe_name(video)
        selected = select_spread_indices(_pitch_indices(video), frames_per_clip)
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise FileNotFoundError("could not open video: %s" % video)
        image_paths: list[Path] = []
        try:
            for source_frame in selected:
                frame_id = "S1_%04d" % next_id
                next_id += 1
                image_path = frames_dir / (frame_id + ".jpg")
                frame = _frame_at(capture, source_frame)
                if not cv2.imwrite(str(image_path), frame):
                    raise RuntimeError("could not write packet image: %s" % image_path)
                labels.append({"frame_id": frame_id, "clip": clip, "manual_player_count": ""})
                detector_counts.append({"frame_id": frame_id, "clip": clip,
                                        "detector_observed_distinct_player_count": str(_valid_detection_count(detector(read_packet_frame(image_path))))})
                image_paths.append(image_path)
        finally:
            capture.release()
        _write_contact_sheet(image_paths, output_dir / ("contact_sheet_%s.jpg" % clip))
    with (output_dir / "blind_label_template.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_id", "clip", "manual_player_count"])
        writer.writeheader()
        writer.writerows(labels)
    with (output_dir / "detector_counts_separate.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_id", "clip", "detector_observed_distinct_player_count"])
        writer.writeheader()
        writer.writerows(detector_counts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("content-gate", "packet"), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frames-per-clip", type=int, default=12)
    parser.add_argument("videos", nargs="+", type=Path)
    args = parser.parse_args()
    if args.mode == "content-gate":
        render_content_gate(args.videos, args.output_dir)
    else:
        build_packet(args.videos, args.output_dir, args.frames_per_clip)


if __name__ == "__main__":
    main()
