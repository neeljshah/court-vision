"""Tests for the independent tennis homography evaluator."""
from __future__ import annotations

import numpy as np

from scripts.platformkit.tracking.tennis_calib_eval import COURT, evaluate_records


def _record(scale: float = 1.0, bad_pixel: bool = False) -> dict:
    court_to_image = np.array([[10.0 * scale, 0.0, 100.0], [0.0, 10.0 * scale, 50.0], [0.0, 0.0, 1.0]])
    observed = {}
    for name, point in COURT.items():
        pixel = court_to_image @ np.array([*point, 1.0])
        observed[name] = [float(pixel[0]), float(pixel[1])]
    if bad_pixel:
        observed["right_service_t"][0] += 12.0
    return {"frame": 0, "image_to_court": np.linalg.inv(court_to_image).tolist(), "observed": observed,
            "solve_landmarks": []}


def test_four_number_contract_passes_independent_perfect_geometry() -> None:
    report = evaluate_records([_record()])
    assert report["pixel_convention"] == {"n": 12, "median_px": 0.0, "pck_at_7px": 1.0}
    assert all(report["depth_band_ft_error"][band]["median_ft"] == 0.0 for band in ("near", "mid", "far"))
    assert report["scale_pass"]
    assert all(item["pass"] for item in report["independent_scale"].values())


def test_pixel_error_and_scale_reject_are_not_provider_claims() -> None:
    row = _record(bad_pixel=True)
    row["image_to_court"] = (np.array(row["image_to_court"]) @ np.diag([1.1, 1.0, 1.0])).tolist()
    report = evaluate_records([row])
    assert report["pixel_convention"]["median_px"] > 0.0
    assert report["pixel_convention"]["pck_at_7px"] < 1.0
    assert not report["scale_pass"]
    assert report["independent_scale"]["length_ft"]["max_abs_pct_error"] > 3.0
