"""Focused mathematical and fixed-category checks for G295."""

import pytest

from scripts.platformkit.tracking.g295_centre_cross_rater_agreement import (
    CATEGORIES, agreement, paired_player,
)


def test_identical_vectors() -> None:
    result = agreement(list(CATEGORIES) * 3, list(CATEGORIES) * 3)
    assert result['kappa'] == 1.0
    assert result['kappa_se'] == 0.0


def test_chance_vectors() -> None:
    result = agreement([x for x in CATEGORIES for _ in CATEGORIES], list(CATEGORIES) * 7)
    assert result['kappa'] == pytest.approx(0.0, abs=1e-15)
    assert result['kappa_se'] == pytest.approx((1 / 294) ** 0.5)


def test_zero_count_column_and_row_retained() -> None:
    result = agreement(list(CATEGORIES), ['A'] * 7)
    assert len(result['matrix']) == 7
    assert all(len(row) == 7 for row in result['matrix'])
    assert result['reference_marginal'] == [1] * 7
    assert result['second_marginal'] == [7, 0, 0, 0, 0, 0, 0]
    assert all(row[6] == 0 for row in result['matrix'])
    assert result['per_category'][6]['positive_agreement'] == 0
    both_absent = agreement(['A', 'B'], ['A', 'B'])
    assert both_absent['matrix'][6] == [0] * 7
    assert both_absent['per_category'][6]['positive_agreement'] is None


def test_paired_player_includes_feet_and_body() -> None:
    result = paired_player(['A', 'B', 'A', 'G'], ['C', 'G', 'D', 'B'])
    assert result['nominal_exact_two_sided_p'] == 0.625
    assert result['reference_player_second_nonplayer'] == 3
    assert result['reference_nonplayer_second_player'] == 1
    assert paired_player(['A', 'B'], ['B', 'A'])['nominal_exact_two_sided_p'] == 1


def test_invalid_vectors() -> None:
    for a, b in [([], []), (['A'], []), (['A'], ['A']), (['X'], ['B'])]:
        with pytest.raises(ValueError):
            agreement(a, b)
