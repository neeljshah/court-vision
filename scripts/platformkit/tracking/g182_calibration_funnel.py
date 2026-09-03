"""Read-only G182 tennis calibration funnel measurement harness."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from domains.tennis.tracking.adapter import TennisAdapter
from scripts.platformkit.calibration.keypoint_calib import TemporalCalibrator

STAGES = (
    "decoded",
    "corner_detection",
    "enough_corners",
    "candidate_homography",
    "homography",
    "lock_drift_pass",
    "emitted",
)
PRIMARY_STAGES = (
    "decoded",
    "corner_detection",
    "enough_corners",
    "candidate_homography",
    "homography",
    "lock_drift_pass",
    "emitted",
)


@dataclass
class FrameRecord:
    """One decoded frame's read-only stage observations."""

    frame: int
    corner_detection: bool = False
    enough_corners: bool = False
    candidate_homography: bool = False
    homography: bool = False
    lock_drift_pass: bool = False
    emitted: bool = False


class FunnelRecorder:
    """Collect stage membership without altering adapter decisions."""

    def __init__(self) -> None:
        self.records: dict[int, FrameRecord] = {}
        self.current_frame: int | None = None

    def begin_frame(self, frame: int) -> None:
        self.current_frame = frame
        self.records[frame] = FrameRecord(frame=frame)

    def current(self) -> FrameRecord:
        if self.current_frame is None:
            raise RuntimeError("measurement event occurred before decode")
        return self.records[self.current_frame]

    def count(self, stage: str) -> int:
        if stage == "decoded":
            return len(self.records)
        return sum(bool(getattr(record, stage)) for record in self.records.values())

    def stage_frames(self, stage: str) -> list[int]:
        if stage == "decoded":
            return sorted(self.records)
        return [frame for frame, record in sorted(self.records.items())
                if bool(getattr(record, stage))]


class IndexedCapture:
    """Attach the source index to each successful production capture read."""

    def __init__(self, path: str, recorder: FunnelRecorder,
                 factory: Callable[[str], Any]) -> None:
        self._capture = factory(path)
        self._recorder = recorder
        self._index = 0

    def isOpened(self) -> bool:
        return bool(self._capture.isOpened())

    def read(self) -> tuple[bool, np.ndarray | None]:
        ok, frame = self._capture.read()
        if ok:
            self._recorder.begin_frame(self._index)
            self._index += 1
        return ok, frame

    def release(self) -> None:
        self._capture.release()


def _stage_summary(recorder: FunnelRecorder) -> tuple[dict[str, dict[str, float | int]], str, list[int]]:
    """Return every-stage denominators plus the unique largest adjacent loss."""
    counts = {stage: recorder.count(stage) for stage in STAGES}
    eligible_stage = {
        "decoded": "decoded",
        "corner_detection": "decoded",
        "enough_corners": "corner_detection",
        "candidate_homography": "enough_corners",
        "homography": "candidate_homography",
        # CameraLock resolves every decoded frame.  It can validly reuse an
        # earlier lock on a frame lacking fresh corners, so its denominator is
        # not the fresh-homography branch.
        "lock_drift_pass": "decoded",
        "emitted": "lock_drift_pass",
    }
    summary: dict[str, dict[str, float | int]] = {}
    for stage in STAGES:
        eligible = counts[eligible_stage[stage]]
        summary[stage] = {
            "count": counts[stage],
            "eligible_denominator": eligible,
            "share_of_eligible_pct": round(100.0 * counts[stage] / eligible, 6) if eligible else 0.0,
            "share_of_decoded_pct": round(100.0 * counts[stage] / counts["decoded"], 6) if counts["decoded"] else 0.0,
        }
    losses = []
    direct_transitions = tuple(zip(PRIMARY_STAGES[:4], PRIMARY_STAGES[1:5]))
    for previous, stage in direct_transitions:
        previous_frames = set(recorder.stage_frames(previous))
        stage_frames = set(recorder.stage_frames(stage))
        lost_frames = sorted(previous_frames - stage_frames)
        losses.append((len(lost_frames), stage, lost_frames))
    loss_count, loss_stage, loss_frames = max(losses, key=lambda item: item[0])
    if loss_count < 5:
        raise RuntimeError("largest-loss decision set has fewer than five frames")
    return summary, loss_stage, loss_frames


def evenly_spaced_frames(frames: list[int], count: int = 5) -> list[int]:
    """Select exact inclusive endpoints and evenly distributed interior frames."""
    if count != 5:
        raise ValueError("G182 requires exactly five renders")
    if len(frames) < count:
        raise ValueError("not enough decision-set frames for five unique renders")
    positions = np.linspace(0, len(frames) - 1, num=count, dtype=int).tolist()
    selected = [frames[position] for position in positions]
    if len(set(selected)) != count:
        raise RuntimeError("even spacing did not select five unique frames")
    return selected


def _render_frames(video: Path, frames: list[int], destination: Path, loss_stage: str) -> list[str]:
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise FileNotFoundError("Could not open video: %s" % video)
    destination.mkdir(parents=True, exist_ok=True)
    wanted = set(frames)
    written: list[str] = []
    index = 0
    try:
        while wanted:
            ok, image = capture.read()
            if not ok:
                break
            if index in wanted:
                label = "G182 %s loss frame %d" % (loss_stage, index)
                cv2.putText(image, label, (16, 32), cv2.FONT_HERSHEY_SIMPLEX,
                            0.8, (0, 0, 255), 2, cv2.LINE_AA)
                path = destination / ("frame_%05d_%s.jpg" % (index, loss_stage))
                if not cv2.imwrite(str(path), image):
                    raise RuntimeError("Could not write render: %s" % path)
                written.append(path.name)
                wanted.remove(index)
            index += 1
    finally:
        capture.release()
    if wanted:
        raise RuntimeError("Could not decode requested frames: %s" % sorted(wanted))
    return written


def measure(video: Path, destination: Path) -> dict[str, Any]:
    """Run the unchanged adapter once with temporary observation wrappers."""
    recorder = FunnelRecorder()
    adapter = TennisAdapter()
    original_capture = cv2.VideoCapture
    original_detect = adapter.detect_court_corners
    original_stable = adapter._stable_homography
    original_resolve = adapter._camera_lock.resolve
    original_players = adapter.detect_players
    original_update = TemporalCalibrator.update

    def capture_factory(path: str) -> IndexedCapture:
        return IndexedCapture(path, recorder, original_capture)

    def detect(frame: np.ndarray) -> np.ndarray | None:
        record = recorder.current()
        record.corner_detection = True
        corners = original_detect(frame)
        record.enough_corners = corners is not None
        return corners

    def update(calibrator: TemporalCalibrator, detections: dict[str, Any]) -> Any:
        result = original_update(calibrator, detections)
        recorder.current().candidate_homography = result.homography is not None
        return result

    def stable(frame: np.ndarray) -> np.ndarray | None:
        homography = original_stable(frame)
        recorder.current().homography = homography is not None
        return homography

    def resolve(frame: np.ndarray, fresh: np.ndarray | None,
                corners: np.ndarray | None) -> tuple[Any, ...]:
        result = original_resolve(frame, fresh, corners)
        recorder.current().lock_drift_pass = result[0] is not None
        return result

    def players(frame: np.ndarray, homography: np.ndarray) -> list[tuple[int, np.ndarray]]:
        result = original_players(frame, homography)
        recorder.current().emitted = bool(result)
        return result

    cv2.VideoCapture = capture_factory
    adapter.detect_court_corners = detect
    adapter._stable_homography = stable
    adapter._camera_lock.resolve = resolve
    adapter.detect_players = players
    TemporalCalibrator.update = update
    try:
        adapter.process_video(video, stride=1)
    finally:
        cv2.VideoCapture = original_capture
        TemporalCalibrator.update = original_update
    decoded = recorder.count("decoded")
    manifest_count = len(adapter.last_frame_manifest)
    if decoded == 0 or decoded != manifest_count:
        raise RuntimeError("decoded/manifest mismatch: %d/%d" % (decoded, manifest_count))
    summary, loss_stage, loss_frames = _stage_summary(recorder)
    selected = evenly_spaced_frames(loss_frames)
    render_dir = destination / "renders"
    renders = _render_frames(video, selected, render_dir, loss_stage)
    destination.mkdir(parents=True, exist_ok=True)
    report = {
        "adapter_sha256": hashlib.sha256(Path(TennisAdapter.__module__.replace(".", "/") + ".py").read_bytes()).hexdigest(),
        "decoded_frames": decoded,
        "funnel": summary,
        "largest_loss": {
            "next_stage": loss_stage,
            "lost_count": len(loss_frames),
            "eligible_denominator": summary[PRIMARY_STAGES[PRIMARY_STAGES.index(loss_stage) - 1]]["count"],
            "lost_share_pct": round(100.0 * len(loss_frames) / summary[PRIMARY_STAGES[PRIMARY_STAGES.index(loss_stage) - 1]]["count"], 6),
            "decision_set_count": len(loss_frames),
            "evenly_spaced_frames": selected,
        },
        "frame_records": [asdict(recorder.records[frame]) for frame in sorted(recorder.records)],
        "renders": ["renders/" + name for name in renders],
    }
    (destination / "g182_funnel.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    report = measure(args.video, args.output_dir)
    print(json.dumps({"decoded_frames": report["decoded_frames"], "largest_loss": report["largest_loss"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
