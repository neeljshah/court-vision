"""Focused tests for G288's additive descriptive-refinement accounting."""

import pytest

from scripts.platformkit.tracking.g288_describe_graphic_and_floor_crops import (
    summarize,
    validate_refinement,
)


def _g287_rows() -> list[dict[str, str]]:
    rows = []
    for index in range(1, 73):
        category = "C" if index <= 17 else "D" if index <= 30 else "A"
        rows.append(
            {
                "order": str(index),
                "blind_filename": f"blind_{index:03d}.jpg",
                "category": category,
                "detail": "",
            }
        )
    return rows


def _refinement_rows() -> list[dict[str, str]]:
    rows = []
    for index in range(1, 31):
        category = "C" if index <= 17 else "D"
        rows.append(
            {
                "order": str(index),
                "blind_filename": f"blind_{index:03d}.jpg",
                "original_category": category,
                "refinement": "C1" if category == "C" else "D1",
                "detail": "short point description",
                "label_stability_observation": "",
            }
        )
    return rows


def test_g288_keeps_exactly_the_committed_c_and_d_selection() -> None:
    summary = summarize(_g287_rows(), _refinement_rows())
    assert summary["n_selected_detector_box_observations"] == 30
    assert summary["selected_g287_categories"] == {"C": 17, "D": 13}
    assert summary["c_breakdown"] == {"C1": 17, "C2": 0, "C3": 0, "C4": 0, "C5": 0}
    assert summary["d_breakdown"] == {"D1": 13, "D2": 0, "D3": 0, "D4": 0}


def test_g288_requires_detail_on_every_refinement_row() -> None:
    refinements = _refinement_rows()
    refinements[0]["detail"] = ""
    with pytest.raises(ValueError, match="free-text detail"):
        validate_refinement(_g287_rows(), refinements)
