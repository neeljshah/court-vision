"""Focused contracts for the G227 provider-to-label mapping."""
from scripts.platformkit.tracking.g205_zero_shot_corner_probe import score_frame
from scripts.platformkit.tracking.g227_keypoint_provider_probe import (
    ROLE_TO_PROVIDER,
    _provider_landmarks,
)


def test_provider_landmarks_preserve_the_declared_baseline_adjacent_mapping():
    detections = {
        "left_paint_bl": (10.0, 10.0, 0.5),
        "left_paint_tl": (10.0, 40.0, 0.5),
        "left_paint_tr": (70.0, 40.0, 0.5),
        "left_paint_br": (70.0, 10.0, 0.5),
    }
    landmarks = _provider_landmarks(detections)
    targets = [
        {"audit_id": "frame", "role": role, "x_px": str(point[0]), "y_px": str(point[1])}
        for role, point in ((role, detections[name]) for role, name in ROLE_TO_PROVIDER.items())
    ]

    _, _, all_four = score_frame(targets, [(point[0], point[1]) for point in landmarks.values()])

    assert list(landmarks) == list(ROLE_TO_PROVIDER)
    assert all_four is True
    assert _provider_landmarks({"left_paint_bl": detections["left_paint_bl"]}) == {}
