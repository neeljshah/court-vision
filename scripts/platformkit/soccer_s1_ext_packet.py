"""Build the soccer S1 EXTENSION packet: 64 new frames on top of the sealed 36.

Reuses scripts.platformkit.soccer_s1_adjudication_packet (select_spread_indices,
_pitch_indices, _valid_detection_count) without modifying it. Adds the
distinct_track_ids column the original packet's caveat was missing, alongside
the original's raw_boxes column, so tracker churn becomes measurable.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from domains.soccer.tracking.adapter import SoccerAdapter
from scripts.platformkit.soccer_s1_adjudication_packet import (
    _frame_at,
    _pitch_indices,
    _safe_name,
    _valid_detection_count,
    select_spread_indices,
)

ORIGINAL_FRAMES_PER_CLIP = 12
EXT_SCAN_POINTS = 400  # denser than the original's 120 so enough NEW candidates exist
STABILIZE_CALLS = 12  # matches domains/soccer/tracking/test_adapter.py's own warm-up pattern


def split_counts(total: int, clips: int) -> list[int]:
    """Distribute `total` as evenly as possible, remainder to the earliest clips."""
    base, extra = divmod(total, clips)
    return [base + (1 if i < extra else 0) for i in range(clips)]


def new_pitch_indices(video: Path) -> list[int]:
    """Pitch-view source-frame indices not already used by the sealed 36."""
    original_candidates = _pitch_indices(video)  # default scan_points=120, same as original build
    excluded = set(select_spread_indices(original_candidates, ORIGINAL_FRAMES_PER_CLIP))
    dense_candidates = _pitch_indices(video, scan_points=EXT_SCAN_POINTS)
    return [index for index in dense_candidates if index not in excluded]


def build_ext_packet(videos: Sequence[Path], output_dir: Path, total_frames: int, start_id: int) -> dict:
    if len(videos) < 3:
        raise ValueError("at least three genuine soccer videos are required")
    output_dir.mkdir(parents=True, exist_ok=True)
    frames_dir = output_dir / "frames"
    crops_dir = output_dir / "crops_2x"
    frames_dir.mkdir(exist_ok=True)
    crops_dir.mkdir(exist_ok=True)
    counts = split_counts(total_frames, len(videos))
    detector = SoccerAdapter().detector
    labels: list[dict[str, str]] = []
    detector_rows: list[dict[str, str]] = []
    next_id = start_id
    for video, clip_count in zip(videos, counts):
        clip = _safe_name(video)
        selected = select_spread_indices(sorted(new_pitch_indices(video)), clip_count)
        capture = cv2.VideoCapture(str(video))
        if not capture.isOpened():
            raise FileNotFoundError("could not open video: %s" % video)
        try:
            for source_frame in selected:
                frame_id = "S1_%04d" % next_id
                next_id += 1
                frame = _frame_at(capture, source_frame)
                if not cv2.imwrite(str(frames_dir / (frame_id + ".jpg")), frame):
                    raise RuntimeError("could not write frame: %s" % frame_id)
                zoomed = cv2.resize(frame, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                if not cv2.imwrite(str(crops_dir / (frame_id + ".jpg")), zoomed):
                    raise RuntimeError("could not write 2x crop: %s" % frame_id)
                labels.append({"frame_id": frame_id, "clip": clip, "manual_player_count": ""})
                adapter = SoccerAdapter(detector=detector)
                landmarks = adapter._landmark_detections(frame)
                for _ in range(STABILIZE_CALLS):
                    adapter._stable_homography(landmarks, frame.shape[:2])
                track_count = (
                    str(len(adapter.detect_players(frame, adapter._homography)))
                    if adapter._homography is not None else ""
                )
                detector_rows.append({
                    "frame_id": frame_id, "clip": clip,
                    "raw_boxes": str(_valid_detection_count(detector(frame))),
                    "distinct_track_ids": track_count,
                })
        finally:
            capture.release()
    with (output_dir / "blind_label_template_ext.csv").open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_id", "clip", "manual_player_count"])
        writer.writeheader()
        writer.writerows(labels)
    sealed_path = output_dir / "detector_counts_separate_ext.csv"
    with sealed_path.open("w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=["frame_id", "clip", "raw_boxes", "distinct_track_ids"])
        writer.writeheader()
        writer.writerows(detector_rows)
    return {
        "frame_ids": [row["frame_id"] for row in labels],
        "clips": [_safe_name(video) for video in videos],
        "sealed_csv_sha256": hashlib.sha256(sealed_path.read_bytes()).hexdigest(),
    }


PROTOCOL_TEXT = """# Soccer S1 EXTENSION labeling protocol (verbatim from the sealed S1 packet)

Source: docs/evidence/tracking/soccer_s1_blind_verdict_2026-09-01.md, blinding
protocol step 2. Copied verbatim; nothing about the counting rule changed for
the n=100 extension.

Counting rule: distinct human players (outfield + goalkeepers, partial bodies
at the frame edge included when identifiable); referees, assistants, fourth
official, coaches, ball kids, photographers excluded.

Label from the frame JPEGs in `frames/`; use the matching image in `crops_2x/`
(a 2x cubic upscale of the same frame, no new information) only to resolve a
dense cluster. Do not open `detector_counts_separate_ext.csv` until every row
below is filled in and committed.

Columns (same as the original `blind_label_template.csv`):
frame_id,clip,manual_player_count
"""


def write_protocol(output_dir: Path) -> None:
    (output_dir / "labeling_protocol_ext.md").write_text(PROTOCOL_TEXT, encoding="ascii")


def write_manifest(output_dir: Path, seed: int, videos: Sequence[Path], result: dict) -> None:
    manifest = {
        "seed": seed,
        "seed_note": "selection is deterministic (evenly-spaced index sampling over the "
                      "post-exclusion candidate pool); seed recorded per task spec, not "
                      "consumed by any RNG",
        "clips": result["clips"],
        "source_urls": [str(video) for video in videos],
        "frame_ids": result["frame_ids"],
        "frame_id_count": len(result["frame_ids"]),
        "sealed_csv_sha256": result["sealed_csv_sha256"],
    }
    (output_dir / "manifest_ext_2026-09-01.json").write_text(json.dumps(manifest, indent=2), encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--total-frames", type=int, default=64)
    parser.add_argument("--start-id", type=int, default=37)
    parser.add_argument("--seed", type=int, default=20260901)
    parser.add_argument("videos", nargs="+", type=Path)
    args = parser.parse_args()
    result = build_ext_packet(args.videos, args.output_dir, args.total_frames, args.start_id)
    write_protocol(args.output_dir)
    write_manifest(args.output_dir, args.seed, args.videos, result)
    print(json.dumps({"sealed_csv_sha256": result["sealed_csv_sha256"], "frame_count": len(result["frame_ids"])}))


if __name__ == "__main__":
    main()
