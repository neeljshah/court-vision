"""Focused tests for the G258 sealed-ladder helpers."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking import g258_synthetic_truth_validity as subject


def test_displaced_map_moves_each_projected_court_point_by_declared_pixels() -> None:
    h = subject.seed_matrix(); court = np.array([[[17.0, 0.0], [33.0, 19.0]]], dtype=np.float32)
    import cv2
    original = cv2.perspectiveTransform(court, np.linalg.inv(h))[0]
    shifted = cv2.perspectiveTransform(court, np.linalg.inv(subject.displaced_image_to_court(h, 5.0)))[0]
    assert np.allclose(shifted - original, [[5.0, 0.0], [5.0, 0.0]], atol=1e-6)


def test_analysis_never_counts_a_censored_offset_as_detected() -> None:
    records = []
    for repeat in range(subject.REPEATS):
        conditions = []
        for rung in subject.RUNGS:
            value = 10.0 if rung == 0 else 24.0
            conditions.append({"rung_px": rung, "offset": {"p90": value}, "image_signals": {"edge_response_contrast": float(rung), "marking_contrast": float(rung), "line_detector_agreement": float(rung), "coverage": float(rung)}, "quad": {"projected_area_ratio_to_seed": float(rung), "bbox_aspect_ratio": float(rung), "outside_corner_fraction": float(rung)}})
        records.append({"repeat": repeat, "conditions": conditions})
    assert subject.analyze({"records": records})["signals"]["offset_p90_px"]["smallest_detected_px"] is None
