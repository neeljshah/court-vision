"""Focused synthetic-H contract test for the SynthCal judge-trace emitter."""
from __future__ import annotations

import cv2
import numpy as np

from scripts.platformkit.synthcal.trace_emitter import COURT, SOLVE_LANDMARKS, record_from_observations


def test_record_has_exact_judge_contract_for_synthetic_h() -> None:
    court_to_image = np.array([[12.0, 0.4, 120.0], [0.2, 9.0, 75.0], [0.001, 0.0005, 1.0]])
    metric = np.float32(list(COURT.values())).reshape(1, -1, 2)
    pixels = cv2.perspectiveTransform(metric, court_to_image)[0]
    observed = {name: [float(point[0]), float(point[1])]
                for name, point in zip(COURT, pixels)}
    row = record_from_observations(37, observed)
    assert row is not None
    assert set(row) == {"frame", "image_to_court", "observed", "solve_landmarks"}
    assert row["frame"] == 37
    assert row["solve_landmarks"] == list(SOLVE_LANDMARKS)
    recovered = np.asarray(row["image_to_court"], dtype=float) @ court_to_image
    recovered /= recovered[2, 2]
    assert np.allclose(recovered, np.eye(3), atol=1e-4)
