"""G91 regression: the pre-measurement provider has one named output path."""
import cv2
import numpy as np

from domains.soccer.tracking.keypoints import SoccerKeypointProvider


def test_detect_emits_only_the_named_center_circle(monkeypatch) -> None:
    """Lock the measured one-key capacity without using a positional corner."""
    provider = SoccerKeypointProvider()
    monkeypatch.setattr(provider, "_markings", lambda frame: np.zeros(frame.shape[:2], np.uint8))
    monkeypatch.setattr(
        cv2,
        "HoughCircles",
        lambda *args, **kwargs: np.array([[[640.0, 360.0, 80.0]]], dtype=np.float32),
    )
    monkeypatch.setattr(provider, "_crossing_line", lambda *args, **kwargs: True)

    detections = provider.detect(np.zeros((720, 1280, 3), dtype=np.uint8))

    assert set(detections) == {"center_circle"}
    assert len(detections) == 1
