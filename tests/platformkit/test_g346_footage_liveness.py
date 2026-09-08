import hashlib
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit import footage_content_gate
from scripts.platformkit.footage_content_gate import GateMetrics, decide, sample_clip, screen
from scripts.platformkit.footage_liveness import measure_liveness


class _SyntheticCapture:
    def __init__(self, frames: list[np.ndarray]):
        self.frames = frames
        self.position = 0

    def isOpened(self) -> bool:
        return True

    def get(self, property_id: int) -> float:
        if property_id == cv2.CAP_PROP_FRAME_COUNT:
            return float(len(self.frames))
        if property_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.frames[0].shape[1])
        if property_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.frames[0].shape[0])
        if property_id == cv2.CAP_PROP_FPS:
            return 30.0
        return 0.0

    def set(self, property_id: int, value: float) -> bool:
        if property_id == cv2.CAP_PROP_POS_FRAMES:
            self.position = int(value)
        if property_id == cv2.CAP_PROP_POS_MSEC:
            self.position = int(value * 0.03)
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.position >= len(self.frames):
            return False, None
        frame = self.frames[self.position].copy()
        self.position += 1
        return True, frame

    def release(self) -> None:
        pass


def _install_capture(monkeypatch, frames: list[np.ndarray]) -> Path:
    monkeypatch.setattr(cv2, "VideoCapture", lambda _: _SyntheticCapture(frames))
    return Path(__file__)


def test_identical_sixty_frame_clip_is_frozen(monkeypatch):
    frame = np.full((90, 160, 3), 96, dtype=np.uint8)
    metrics = measure_liveness(_install_capture(monkeypatch, [frame] * 60))

    assert metrics.valid_frames == 60
    assert metrics.near_identical_share == 1.0
    assert metrics.verdict == "FROZEN"


def test_moving_noise_sixty_frame_clip_is_live(monkeypatch):
    rng = np.random.default_rng(346)
    frames = [rng.integers(0, 256, (90, 160, 3), dtype=np.uint8)
              for _ in range(60)]
    metrics = measure_liveness(_install_capture(monkeypatch, frames))

    assert metrics.valid_frames == 60
    assert metrics.near_identical_share == 0.0
    assert metrics.verdict == "LIVE"


def test_frozen_rejection_is_opt_in_and_default_decision_is_unchanged(monkeypatch):
    frame = np.full((90, 160, 3), 96, dtype=np.uint8)
    video = _install_capture(monkeypatch, [frame] * 60)
    baseline = decide(sample_clip(video, "basketball"))
    reported = screen(video, "basketball")
    opted_in = screen(video, "basketball", reject_frozen=True)

    assert (reported.decision, reported.reason) == (baseline.decision, baseline.reason)
    assert reported.metrics.liveness and reported.metrics.liveness.verdict == "FROZEN"
    assert (opted_in.decision, opted_in.reason) == ("reject", "frozen_video_liveness")


def test_liveness_failure_does_not_change_the_existing_fail_open_decision(monkeypatch):
    baseline_metrics = GateMetrics([1.0, 2.0, 3.0], [0.20] * 3, [0.0] * 3, 0.0)
    monkeypatch.setattr(footage_content_gate, "sample_clip",
                        lambda video, sport: baseline_metrics)
    monkeypatch.setattr(footage_content_gate, "measure_liveness",
                        lambda video: (_ for _ in ()).throw(ValueError("unavailable")))

    reported = screen(Path(__file__), "basketball")

    assert reported == decide(baseline_metrics)


def test_preregistration_seal_normalizes_crlf_without_git_show():
    preregistration = Path("docs/evidence/tracking/g346_frozen_video_gate_2026-09-08"
                           "/preregistration.md")
    text = preregistration.read_text(encoding="utf-8").replace("\r\n", "\n")
    body, seal = text.rsplit("SEAL sha256 ", 1)

    assert seal.strip() == hashlib.sha256(body.encode("utf-8")).hexdigest()
