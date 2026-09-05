"""Focused tests for G287 sealed-artifact accounting."""

from scripts.platformkit.tracking.g287_unconditioned_footpoint_content import (
    summarize,
    validate_blinded_rows,
)


def _rows() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    order = [
        {"order": str(index), "blind_filename": f"blind_{index:03d}.jpg"}
        for index in range(1, 73)
    ]
    categories = ["A", "B", "C", "D", "E", "F", "G"] + ["C"] * 65
    verdicts = [
        {
            "order": str(index),
            "blind_filename": f"blind_{index:03d}.jpg",
            "category": categories[index - 1],
            "detail": "camera" if categories[index - 1] == "F" else "",
        }
        for index in range(1, 73)
    ]
    return order, verdicts


def test_g287_summary_keeps_all_categories_and_all_rows() -> None:
    order, verdicts = _rows()
    g273 = [
        {
            "blind_filename": f"blind_{index:03d}.jpg",
            "verdict": "PLAYER" if index <= 43 else "NOT A PERSON",
        }
        for index in range(1, 73)
    ]
    summary = summarize(order, verdicts, g273)
    assert summary["n_detector_box_observations"] == 72
    assert summary["counts"] == {"A": 1, "B": 1, "C": 66, "D": 1, "E": 1, "F": 1, "G": 1}
    assert sum(summary["g273_by_g287"]["PLAYER"].values()) == 43


def test_g287_requires_something_else_detail() -> None:
    order, verdicts = _rows()
    verdicts[5]["detail"] = ""
    try:
        validate_blinded_rows(order, verdicts)
    except ValueError as error:
        assert "free-text detail" in str(error)
    else:
        raise AssertionError("SOMETHING_ELSE detail was accepted")
