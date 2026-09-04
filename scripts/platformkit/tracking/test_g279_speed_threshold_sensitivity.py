"""Focused regression coverage for G279's local artifact arithmetic."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.platformkit.tracking import g279_speed_threshold_sensitivity as g279


ARTIFACT = Path("docs/evidence/tracking/g267_court_space_physical_plausibility_artifact/g267_measurement.json")


def test_g279_reproduces_published_strict_over_40_results() -> None:
    report = g279.measure(ARTIFACT)
    reproduction = report["analysis"]["reproduction"]
    assert reproduction["g267_all_steps_strictly_over_40_ft_per_s"] == {
        "numerator": 4090,
        "denominator": 29973,
        "fraction": 4090 / 29973,
    }
    assert reproduction["g270_both_endpoints_on_court_strictly_over_40_ft_per_s"] == {
        "numerator": 2507,
        "denominator": 23783,
        "fraction": 2507 / 23783,
    }


def test_g279_writes_requested_curve_and_denominator_accounting(tmp_path: Path) -> None:
    output = tmp_path / "g279_measurement.json"
    report = g279.measure(ARTIFACT)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="ascii")
    loaded = json.loads(output.read_text(encoding="ascii"))
    assert loaded["analysis"]["thresholds_ft_per_s"] == [20.0, 25.0, 26.5, 30.0, 35.0, 40.0, 45.0, 50.0, 60.0]
    assert loaded["analysis"]["contextual_references_ft_per_s"]["26.5"] == "NBA average top speed"
    assert loaded["analysis"]["contextual_references_ft_per_s"]["40.7"] == "Bolt peak"
    expected_all = {20.0: 7131, 25.0: 5941, 26.5: 5652, 30.0: 5128, 35.0: 4532, 40.0: 4090, 45.0: 3802, 50.0: 3570, 60.0: 3155}
    expected_on_court = {20.0: 4833, 25.0: 3913, 26.5: 3692, 30.0: 3295, 35.0: 2849, 40.0: 2507, 45.0: 2281, 50.0: 2113, 60.0: 1807}
    all_curve = loaded["analysis"]["all_finite_same_id_steps"]["curve"]
    on_court_curve = loaded["analysis"]["both_endpoints_on_court_same_id_steps"]["curve"]
    assert {float(key): value["strictly_above_threshold_steps"] for key, value in all_curve.items()} == expected_all
    assert {float(key): value["strictly_above_threshold_steps"] for key, value in on_court_curve.items()} == expected_on_court
    accounting = loaded["analysis"]["unmeasurable_or_conditionally_excluded_accounting"]
    assert accounting["nonfinite_detection_records"] == 0
    assert accounting["same_id_steps_eligible_after_finite_endpoint_requirement"] == 29973
    assert accounting["steps_excluded_by_both_endpoints_on_court_condition"] == 6190
