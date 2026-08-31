"""Focused tests for conservative jersey OCR helpers.

Run: python -m pytest scripts/platformkit/jersey/test_pipeline.py -q
"""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.jersey.pipeline import TrackletVoter, legibility_score, torso_crop


def test_weighted_vote_selects_stronger_conflicting_number() -> None:
    voter = TrackletVoter()
    voter.add("player-1", "12", 0.95, 0.95)
    voter.add("player-1", "12", 0.90, 0.90)
    voter.add("player-1", "21", 0.80, 0.50)

    number, confidence = voter.number("player-1")

    assert number == "12"
    assert confidence > 0.75


def test_sparse_votes_remain_unknown() -> None:
    voter = TrackletVoter()
    voter.add("player-1", "12", 1.0, 1.0)
    voter.add("player-1", "12", 1.0, 1.0)

    assert voter.number("player-1") == (None, 0.0)


def test_sharp_crop_scores_above_blurred_crop() -> None:
    sharp = np.zeros((80, 80, 3), dtype=np.uint8)
    cv2.putText(sharp, "12", (8, 58), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (255, 255, 255), 3)
    blurred = cv2.GaussianBlur(sharp, (15, 15), 0)

    assert legibility_score(sharp) > legibility_score(blurred)


def test_pose_keypoints_rectify_torso_geometry() -> None:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[20:60, 30:70] = (10, 20, 30)
    keypoints = {
        "left_shoulder": (30, 20),
        "right_shoulder": (70, 20),
        "left_hip": (30, 60),
        "right_hip": (70, 60),
    }

    crop = torso_crop(frame, (20, 10, 80, 90), keypoints)

    assert crop.shape[:2] == (40, 40)
    assert np.all(crop[20, 20] == (10, 20, 30))
