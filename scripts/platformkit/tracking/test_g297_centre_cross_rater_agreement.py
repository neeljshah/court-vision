"""Focused mathematical checks for the G297 agreement harness."""

from scripts.platformkit.tracking.g297_centre_cross_rater_agreement import (
    CATEGORIES,
    agreement,
)


def test_kappa_identical_vectors_is_one() -> None:
    result = agreement(list(CATEGORIES) * 3, list(CATEGORIES) * 3)
    assert result["kappa"] == 1.0


def test_kappa_is_zero_at_chance() -> None:
    reference = [left for left in CATEGORIES for _ in CATEGORIES]
    fresh = list(CATEGORIES) * len(CATEGORIES)
    result = agreement(reference, fresh)
    assert result["raw_agreement"] == 1 / 7
    assert result["chance_agreement"] == 1 / 7
    assert result["kappa"] == 0.0


def test_zero_count_category_is_retained_in_matrix() -> None:
    reference = list(CATEGORIES)
    fresh = list(CATEGORIES[:-1]) + ["A"]
    result = agreement(reference, fresh)
    assert len(result["matrix"]) == 7
    assert all(len(row) == 7 for row in result["matrix"])
    assert result["reference_marginal"] == [1] * 7
    assert result["fresh_marginal"] == [2, 1, 1, 1, 1, 1, 0]
    assert result["per_category"][6]["fresh_n"] == 0
