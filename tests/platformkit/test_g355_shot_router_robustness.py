"""Regression tests for G355 descriptor and first-frame robustness."""

from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from scripts.platformkit.tracking.floor_motion import estimate_floor_motion, propagate_frames
from scripts.platformkit.tracking.shot_router import RouteRecord, _static_inlier_fraction


ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs/evidence/tracking/g355_prereg_2026-09-08.md"


class _OneDescriptorORB:
    def __init__(self) -> None:
        self.calls = 0

    def detectAndCompute(self, image: np.ndarray, mask: np.ndarray | None):
        self.calls += 1
        count = 2 if self.calls == 1 else 1
        keys = [cv2.KeyPoint(float(index), float(index), 1.0) for index in range(count)]
        return keys, np.zeros((count, 32), dtype=np.uint8)


def test_one_descriptor_pair_is_unobservable_and_prereg_seal_is_valid(monkeypatch):
    text = PREREG.read_text(encoding="utf-8").replace("\r\n", "\n")
    prefix, seal = text.rsplit("\nSEAL sha256 ", 1)
    assert hashlib.sha256((prefix + "\n").encode("utf-8")).hexdigest() == seal.strip()
    monkeypatch.setattr(cv2, "ORB_create", lambda nfeatures=500: _OneDescriptorORB())
    first = np.zeros((180, 320, 3), dtype=np.uint8)
    second = np.ones((180, 320, 3), dtype=np.uint8)
    assert _static_inlier_fraction(first, second) == 0.0
    matrix, diagnostics = estimate_floor_motion(first, second)
    assert matrix is None and diagnostics[0] == "too_few_descriptors"


def test_one_frame_shot_emits_one_anchor_record():
    frame = np.zeros((180, 320, 3), dtype=np.uint8)
    route = RouteRecord(17, 4, "UNKNOWN", "UNKNOWN", 0.0, 1.0, 0, 0.0, None)
    records = propagate_frames([frame], [route])
    assert len(records) == 1
    assert records[0].frame_index == 17 and records[0].shot_id == 4
    assert records[0].state == "ANCHOR" and records[0].accepted
    assert records[0].reason == "anchor" and records[0].chain_length == 0
    assert records[0].inliers == records[0].n_fit == records[0].n_val == 0
    assert records[0].inlier_share == records[0].hull_share == records[0].p90_residual_px == 0.0
