"""Measure occlusion-tolerant basketball line evidence on real footage.

This reports only observed LSD fragments and merged image-line candidates. It
reports all downstream stages as zero when no independent physical line
identity exists; it never infers correspondence from group ordinal position.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from domains.basketball.tracking.line_calibration import (
    candidate_line_groups, detect_lsd_segments,
)


def measure(video: Path, max_frames: int) -> dict[str, object]:
    """Return bounded, observed line-fragment coverage for one video."""
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise ValueError("could not open video: {}".format(video))
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = fragments = line_detection = clustering = 0
    group_counts: list[int] = []
    requested = min(max_frames, total) if total else max_frames
    # Some OpenCV/FFmpeg combinations seek successfully to the penultimate
    # frame but reject an exact final-frame seek. Keep the requested decoded
    # denominator intact by excluding only that unreliable endpoint.
    # The first decoded timestamp is also unreliable in this pod's FFmpeg
    # build, so distribute the samples across the stable [1, total - 2] range.
    sample_indices = np.linspace(min(1, max(0, total - 2)), max(0, total - 2),
                                 requested, dtype=int)
    for frame_index in sample_indices:
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = capture.read()
        if not ok:
            # FFmpeg can reject an isolated timestamp even when neighboring
            # decoded frames are valid. A single prior-frame retry preserves
            # the requested real-frame denominator without fabricating data.
            capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame_index) - 1))
            ok, frame = capture.read()
        if not ok:
            continue
        segments = detect_lsd_segments(frame, min_length=max(60.0, width / 20.0))
        groups = candidate_line_groups(segments)
        frames += 1
        fragments += len(segments)
        group_counts.append(len(groups))
        line_detection += int(bool(segments))
        clustering += int(len(groups) >= 4)
    capture.release()
    return {
        "video": video.name,
        "source_resolution": "{}x{}".format(width, height),
        "source_fps": fps,
        "source_frames": total,
        "sampling": "{} evenly-spaced seek positions".format(requested),
        "sampled_frames": frames,
        "mean_lsd_fragments": round(fragments / max(1, frames), 2),
        "median_merged_line_groups": float(np.median(group_counts)) if group_counts else 0.0,
        "funnel": {
            "decoded_frames": frames,
            "line_detection_survivors": line_detection,
            "clustering_survivors": clustering,
            "physical_correspondence_survivors": 0,
            "homography_solve_survivors": 0,
            "accepted_physical_solves": 0,
        },
        "frames_with_four_or_more_image_line_groups": clustering,
        "held_out_landmark_error_ft": "not_applicable_no_accepted_solves",
        "lane_16_by_19_ratio_check": "not_applicable_no_accepted_solves",
        "verdict": "stops at correspondence: image-line groups have no independently validated physical identity",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure basketball LSD line evidence.")
    parser.add_argument("video", type=Path)
    parser.add_argument("--max-frames", type=int, default=300)
    args = parser.parse_args()
    if args.max_frames < 1:
        raise ValueError("max-frames must be positive")
    print(json.dumps(measure(args.video, args.max_frames), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
