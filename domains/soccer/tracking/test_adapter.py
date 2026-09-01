"""Synthetic tests for the soccer broadcast tracking adapter.

Run: python -m pytest domains/soccer/tracking/test_adapter.py -q
"""
from __future__ import annotations

import cv2
import numpy as np
import pandas as pd
import pytest

from domains.soccer.tracking.adapter import (
    PITCH_ACCEPT,
    BallTrackingUnavailableError,
    SoccerAdapter,
)
from scripts.platformkit.calibration.keypoint_calib import (
    CANONICAL_LANDMARKS,
    solve_homography,
)
from scripts.platformkit.tracking_harness import SPORTS, evaluate


# Six landmarks exactly consistent with one ground-truth view.  The two penalty
# box corners are deliberately NOT center_circle: (52.5, 34) is the exact
# midpoint of both pitch diagonals, so every corner-holdout subset containing it
# has three collinear points and cannot determine a homography at all.
_FIXTURE = ("pitch_bl", "pitch_br", "pitch_tr", "pitch_tl",
            "left_box_br", "left_box_tr")


def _consistent_detections(shift: float = 0.0) -> dict:
    """Landmark pixels generated from one exact ground-truth homography."""
    quad = np.float32(((60, 650), (1220, 650), (850, 200), (430, 200))) + shift
    canonical = np.float32([CANONICAL_LANDMARKS["soccer"][n] for n in _FIXTURE[:4]])
    inverse = np.linalg.inv(cv2.getPerspectiveTransform(quad, canonical))
    pixels = cv2.perspectiveTransform(
        np.float32([[CANONICAL_LANDMARKS["soccer"][n] for n in _FIXTURE]]), inverse,
    )[0]
    return {n: (float(p[0]), float(p[1]), 1.0) for n, p in zip(_FIXTURE, pixels)}


PITCH = np.float32(((100, 650), (1180, 650), (100, 100), (1180, 100)))


def _pitch_image() -> np.ndarray:
    image = np.full((720, 1280, 3), (40, 140, 40), dtype=np.uint8)
    cv2.line(image, tuple(PITCH[0].astype(int)), tuple(PITCH[1].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[0].astype(int)), tuple(PITCH[2].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[1].astype(int)), tuple(PITCH[3].astype(int)), (255, 255, 255), 5)
    cv2.line(image, tuple(PITCH[2].astype(int)), tuple(PITCH[3].astype(int)), (255, 255, 255), 5)
    cv2.line(image, (640, 100), (640, 650), (255, 255, 255), 5)
    cv2.circle(image, (640, 375), 85, (255, 255, 255), 5)
    return image


def _degraded_broadcast_like_pitch() -> np.ndarray:
    height, width = 720, 1280
    illumination = np.linspace(0.55, 1.2, width, dtype=np.float32)[None, :]
    image = np.empty((height, width, 3), dtype=np.uint8)
    image[:, :, 0] = np.clip(28 * illumination, 0, 255)
    image[:, :, 1] = np.clip(145 * illumination, 0, 255)
    image[:, :, 2] = np.clip(30 * illumination, 0, 255)
    segments = (
        ((100, 650), (480, 650)), ((590, 650), (1180, 650)),
        ((100, 100), (500, 100)), ((620, 100), (1180, 100)),
        ((100, 170), (100, 650)), ((1180, 100), (1180, 570)),
        ((640, 130), (640, 340)), ((640, 430), (640, 620)),
    )
    for start, end in segments:
        cv2.line(image, start, end, (255, 255, 255), 5)
    noise = np.random.default_rng(22).normal(0, 9, image.shape).astype(np.int16)
    return np.clip(image.astype(np.int16) + noise, 0, 255).astype(np.uint8)


def test_synthetic_markings_and_homography() -> None:
    image = _pitch_image()
    adapter = SoccerAdapter(detector=lambda frame: [])
    markings = adapter.detect_pitch_markings(image)
    assert markings["halfway_x"] is not None
    assert abs(markings["halfway_x"] - 640) < 5.0
    assert markings["center_circle"] is not None
    corners = adapter.detect_pitch_corners(image)
    assert corners is not None
    homography = adapter.homography_from_corners(corners)
    mapped = cv2.perspectiveTransform(PITCH.reshape(1, -1, 2), homography)[0]
    assert np.max(np.abs(mapped - np.float32(((0, 0), (105, 0), (0, 68), (105, 68))))) < 1.0


def test_degraded_partial_broadcast_lines_recover_homography() -> None:
    adapter = SoccerAdapter(detector=lambda frame: [])
    detections = adapter._landmark_detections(_degraded_broadcast_like_pitch())
    assert len(detections) >= 4
    homography = solve_homography(detections, "soccer")
    assert homography is not None
    recovered = cv2.perspectiveTransform(PITCH.reshape(1, -1, 2), homography)[0]
    error = np.linalg.norm(recovered - np.float32(((0, 0), (105, 0), (0, 68), (105, 68))), axis=1)
    assert float(np.max(error)) < 2.0


def test_mock_detector_projects_players_and_tracks_ids() -> None:
    image = _pitch_image()
    base = SoccerAdapter(detector=lambda frame: [])
    homography = base.homography_from_corners(PITCH)
    inverse = np.linalg.inv(homography)

    def box_for(x: float, y: float) -> list[float]:
        pixel = cv2.perspectiveTransform(np.float32([[[x, y]]]), inverse)[0, 0]
        return [pixel[0] - 15, pixel[1] - 60, pixel[0] + 15, pixel[1]]

    adapter = SoccerAdapter(detector=lambda frame: [box_for(20, 12), box_for(80, 52)])
    players = adapter.detect_players(image, homography)
    assert [track_id for track_id, _ in players] == [1, 2]
    points = {track_id: point for track_id, point in players}
    assert np.allclose(points[1], (20, 12), atol=0.5)
    assert np.allclose(points[2], (80, 52), atol=0.5)


def test_four_exact_correspondences_are_not_accepted_as_validated() -> None:
    """Regression: a 4-point fit is exactly determined, so it evidences nothing.

    The old gate scored the fit on the same four points that produced it, so its
    error was identically 0 and it could never reject anything.
    """
    adapter = SoccerAdapter(detector=lambda frame: [])
    detections = {
        name: (float(point[0]), float(point[1]), 1.0)
        for name, point in zip(("pitch_bl", "pitch_br", "pitch_tl", "pitch_tr"), PITCH)
    }
    assert adapter._validated_homography(detections) is None
    for _ in range(30):
        assert adapter._stable_homography(PITCH) is None


def test_held_out_landmark_rejects_an_inconsistent_fit() -> None:
    adapter = SoccerAdapter(detector=lambda frame: [])
    detections = _consistent_detections()
    assert adapter._validated_homography(detections) is not None
    x, y, conf = detections["left_box_tr"]
    detections["left_box_tr"] = (x + 90.0, y + 60.0, conf)
    assert adapter._validated_homography(detections) is None


def test_rejected_candidate_never_returns_the_stale_homography() -> None:
    """Regression: emitting rows under a transform the calibrator just rejected."""
    adapter = SoccerAdapter(detector=lambda frame: [])
    for _ in range(12):
        adapter._stable_homography(_consistent_detections())
    assert adapter._homography is not None
    locked = adapter._homography.copy()
    assert adapter._stable_homography(_consistent_detections(shift=180.0)) is None
    assert np.array_equal(adapter._homography, locked)


def test_accept_window_is_strictly_wider_than_the_harness_bound() -> None:
    """Regression: an accept window equal to the harness bound makes oob_pct 0.0."""
    low_x, high_x, low_y, high_y = SPORTS["soccer"]["bounds"]
    assert PITCH_ACCEPT[0] < low_x and PITCH_ACCEPT[1] > high_x
    assert PITCH_ACCEPT[2] < low_y and PITCH_ACCEPT[3] > high_y


def test_process_video_requires_explicit_player_only_opt_in(tmp_path) -> None:
    path = tmp_path / "ball.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    writer.write(np.zeros((72, 128, 3), dtype=np.uint8))
    writer.release()
    adapter = SoccerAdapter(detector=lambda frame: [])
    try:
        adapter.process_video(path)
    except BallTrackingUnavailableError:
        return
    raise AssertionError("soccer has no ball detector and must fail closed")


def test_write_csv_uses_normalized_schema(tmp_path) -> None:
    adapter = SoccerAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame([[4, 1, "player", 20.0, 6.0]], columns=("frame", "track_id", "cls", "x", "y"))
    output = tmp_path / "tracking.csv"
    adapter.write_csv(output)
    assert list(pd.read_csv(output).columns) == ["frame", "track_id", "cls", "x", "y"]


def test_process_video_skips_non_pitch_frames(tmp_path) -> None:
    path = tmp_path / "views.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    pitch = np.full((72, 128, 3), (40, 140, 40), dtype=np.uint8)
    crowd = np.full((72, 128, 3), (50, 50, 120), dtype=np.uint8)
    for frame in (pitch, crowd, pitch):
        writer.write(frame)
    writer.release()
    adapter = SoccerAdapter(detector=lambda frame: [])
    calls: list[int] = []
    adapter._landmark_detections = lambda frame: calls.append(1) or {}
    adapter._stable_homography = lambda detections, shape: None
    adapter.process_video(path, player_only=True)
    assert len(calls) == 2


def test_process_video_pressing_metadata_preserves_row_schema(tmp_path) -> None:
    path = tmp_path / "pressing.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    for _ in range(2):
        writer.write(np.zeros((72, 128, 3), dtype=np.uint8))
    writer.release()
    adapter = SoccerAdapter(detector=lambda frame: [])
    adapter._landmark_detections = lambda frame: {}
    adapter._stable_homography = lambda detections, shape: np.eye(3, dtype=np.float32)
    adapter.detect_players = lambda frame, homography: [
        (1, np.array((50.0, 34.0))), (2, np.array((54.0, 34.0))),
    ]
    rows = adapter.process_video(path, skip_non_pitch=False, compute_pressing=True, player_only=True)
    assert list(rows.columns) == ["frame", "track_id", "cls", "x", "y"]
    assert "pressing_proxy" in adapter.last_metadata
    assert adapter.last_metadata["pressing_proxy"]["frame_ids"] == [0, 1]
    adapter.process_video(path, skip_non_pitch=False, compute_pressing=False, player_only=True)
    assert "pressing_proxy" not in adapter.last_metadata


def test_image_space_emits_every_detection_with_provenance_and_fails_closed(tmp_path) -> None:
    """Boxes far outside the pitch bounds survive: pixel space has no bound."""
    path = tmp_path / "image_space.avi"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25, (128, 72))
    for _ in range(2):
        writer.write(np.zeros((72, 128, 3), dtype=np.uint8))
    writer.release()
    adapter = SoccerAdapter(detector=lambda frame: [[10, 20, 30, 60], [900, 40, 940, 700]])
    adapter._landmark_detections = lambda frame: {}
    adapter._stable_homography = lambda detections, shape: None
    rows = adapter.process_video(path, skip_non_pitch=False, compute_pressing=True,
                                 player_only=True, image_space=True)
    assert len(rows) == 4
    assert rows["x"].tolist() == [20.0, 920.0, 20.0, 920.0]
    assert rows["y"].tolist() == [60.0, 700.0, 60.0, 700.0]
    assert set(rows["coordinate_space"]) == {"image_px"}
    assert set(rows["observation"]) == {"observed"}
    assert set(rows["calibration"]) == {"none"}
    assert adapter.last_metadata["roi"] == "full_frame"
    assert adapter.last_metadata["accepted_homography_frames"] == []
    assert "pressing_proxy" not in adapter.last_metadata
    report = evaluate(rows, "soccer")
    assert not report.passed
    assert [f.split(":")[0] for f in report.failures] == ["coordinate_contract"]


def test_write_csv_refuses_to_drop_half_the_provenance(tmp_path) -> None:
    adapter = SoccerAdapter(detector=lambda frame: [])
    adapter.last_output = pd.DataFrame(
        [[4, 1, "player", 20.0, 6.0, "image_px"]],
        columns=("frame", "track_id", "cls", "x", "y", "coordinate_space"),
    )
    with pytest.raises(ValueError, match="observation, calibration"):
        adapter.write_csv(tmp_path / "partial.csv")
