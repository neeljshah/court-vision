"""Focused tests for G260's sealed paired-difference analysis."""
from __future__ import annotations

from scripts.platformkit.tracking import g260_paired_displacement_sensitivity as subject


def _condition(rung: int, value: float, p90: float = 10.0) -> dict[str, object]:
    return {"rung_px": rung, "offset": {"p90": p90},
            "image_signals": {"edge_response_contrast": value, "line_detector_agreement": value,
                              "marking_contrast": value, "coverage": value},
            "quad": {"projected_area_ratio_to_seed": value, "bbox_aspect_ratio": value,
                     "outside_corner_fraction": value}}


def _report(censored: bool = False) -> dict[str, object]:
    rows = []
    for frame in range(35):
        jitter = (frame % 5 - 2) * 0.01
        conditions = [_condition(0, 10.0)]
        for rung in subject.RUNGS[1:]:
            p90 = 24.0 if censored and rung == 2 else 10.0 + rung * 0.1 + jitter
            conditions.append(_condition(rung, 10.0 + rung * 0.1 + jitter, p90))
        rows.append({"source_frame": frame, "conditions": conditions})
    return {"records": rows}


def test_paired_analysis_requires_spread_sign_and_full_ladder_monotonicity() -> None:
    analysis = subject.analyze(_report())
    edge = analysis["signals"]["edge_response_contrast"]
    assert edge["full_ladder_monotone"] is True
    assert edge["smallest_reliably_detected_px"] == 2
    rung = edge["rungs"][2]
    assert rung["n"] == 35
    assert rung["strict_sign_count"] == 35
    assert rung["scaled_mad"] > 0


def test_censored_offset_pairs_are_retained_as_named_exclusions() -> None:
    rung = subject.analyze(_report(censored=True))["signals"]["offset_p90_px"]["rungs"][2]
    assert rung["n"] == 0
    assert rung["exclusion_reasons"] == {"offset_p90_censored_at_24px": 35}
