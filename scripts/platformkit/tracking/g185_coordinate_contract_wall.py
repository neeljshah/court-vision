"""Read-only, even-sample calibration observations for G185."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


SPORTS = ("baseball", "soccer", "football")


@dataclass(frozen=True)
class FrameRecord:
    """One adapter-evaluated source frame and calibration observations."""

    frame: int
    calibration_attempted: bool
    calibration_succeeded: bool
    candidate_succeeded: bool | None
    detail: str


def even_positions(frame_count: int, sample_size: int) -> list[int]:
    """Return inclusive, strictly unique, evenly spaced source-frame indices."""
    if frame_count < sample_size or sample_size < 1:
        raise ValueError("sample_size must be in 1..frame_count")
    positions = np.linspace(0, frame_count - 1, num=sample_size, dtype=int).tolist()
    if len(set(positions)) != sample_size:
        raise RuntimeError("even sampling did not produce unique positions")
    return positions


def failure_eye_positions(records: list[FrameRecord], count: int = 5) -> tuple[list[int], list[int]]:
    """Return positions and frame indices evenly selected from calibration failures."""
    failures = [record.frame for record in records if not record.calibration_succeeded]
    positions = even_positions(len(failures), count)
    return positions, [failures[position] for position in positions]


def _adapter(sport: str) -> Any:
    if sport == "baseball":
        from domains.baseball.tracking.adapter import BaseballAdapter
        return BaseballAdapter(detector=lambda _frame: [])
    if sport == "soccer":
        from domains.soccer.tracking.adapter import SoccerAdapter
        return SoccerAdapter(detector=lambda _frame: [], calibration_stride=1)
    if sport == "football":
        from domains.football.tracking.adapter import FootballAdapter
        return FootballAdapter(detector=lambda _frame: [])
    raise ValueError("unknown sport: %s" % sport)


def _observe(adapter: Any, sport: str, frame: np.ndarray) -> FrameRecord:
    if sport == "baseball":
        geometry = adapter.detect_pitch_geometry(frame)
        return FrameRecord(-1, True, geometry is not None, None,
                           "pitch_geometry" if geometry is not None else "no_pitch_geometry")
    if sport == "soccer":
        detections = adapter._landmark_detections(frame)
        candidate = adapter._validated_homography(detections)
        homography = adapter._stable_homography(detections, frame.shape[:2])
        return FrameRecord(-1, True, homography is not None, candidate is not None,
                           "stable_homography" if homography is not None else "no_stable_homography")
    original = adapter.homography_from_yard_lines
    candidate: list[bool] = []

    def watched(image: np.ndarray) -> Any:
        result = original(image)
        candidate.append(result is not None)
        return result

    adapter.homography_from_yard_lines = watched
    try:
        homography = adapter._stable_homography(frame)
    finally:
        adapter.homography_from_yard_lines = original
    return FrameRecord(-1, True, homography is not None,
                       candidate[0] if candidate else None,
                       "stable_homography" if homography is not None else "no_stable_homography")


def measure(video: Path, sport: str, sample_size: int = 120) -> dict[str, Any]:
    """Evaluate unmodified sport calibration paths at even source-frame positions."""
    if sport not in SPORTS:
        raise ValueError("sport must be one of: %s" % ", ".join(SPORTS))
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("could not open video: %s" % video)
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    positions = even_positions(total, sample_size)
    requested = set(positions)
    adapter = _adapter(sport)
    records: list[FrameRecord] = []
    index = 0
    try:
        while requested:
            ok, frame = capture.read()
            if not ok:
                break
            if index in requested:
                observed = _observe(adapter, sport, frame)
                records.append(FrameRecord(index, observed.calibration_attempted,
                                           observed.calibration_succeeded,
                                           observed.candidate_succeeded,
                                           observed.detail))
                requested.remove(index)
            index += 1
    finally:
        capture.release()
    if requested:
        raise RuntimeError("decoder did not reach positions: %s" % sorted(requested))
    succeeded = sum(record.calibration_succeeded for record in records)
    candidates = sum(record.candidate_succeeded is True for record in records)
    return {
        "sport": sport,
        "video": str(video),
        "decoded_frames_metadata": total,
        "eligible_denominator_kind": "adapter_evaluated_frames",
        "eligible_denominator": len(records),
        "sampling_positions": positions,
        "calibration_successes": succeeded,
        "candidate_successes": candidates,
        "frame_records": [asdict(record) for record in records],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--sport", required=True, choices=SPORTS)
    parser.add_argument("--sample-size", type=int, default=120)
    args = parser.parse_args()
    print(json.dumps(measure(args.video, args.sport, args.sample_size), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
