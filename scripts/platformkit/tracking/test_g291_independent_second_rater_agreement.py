"""Focused mathematical and denominator checks for G291."""

import pytest

from scripts.platformkit.tracking.g291_independent_second_rater_agreement import (
    CATEGORIES, agreement, paired_player,
)


def test_kappa_identical_vectors_is_one() -> None:
    result = agreement(list(CATEGORIES) * 4, list(CATEGORIES) * 4)
    assert result['kappa'] == 1.0
    assert result['kappa_se'] == 0.0


def test_kappa_chance_agreement_is_zero() -> None:
    a = [x for x in CATEGORIES for _ in CATEGORIES]
    b = list(CATEGORIES) * 4
    result = agreement(a, b)
    assert result['kappa'] == 0.0
    assert result['raw_agreement'] == 0.25
    assert result['kappa_se'] == pytest.approx((1 / 48) ** 0.5)


def test_mcnemar_uses_only_paired_discordance() -> None:
    a = ['PLAYER'] * 3 + ['CANNOT JUDGE']
    b = ['NOT A PERSON'] * 3 + ['PLAYER']
    result = paired_player(a, b)
    assert result['nominal_exact_two_sided_p'] == 0.625
    assert result['second_minus_reference'] == -0.5
    assert result['discordant_n'] == 4


def test_absent_second_category_stays_separate() -> None:
    result = agreement(list(CATEGORIES), ['PLAYER'] * 4)
    assert result['reference_marginal'] == [1, 1, 1, 1]
    assert result['second_marginal'] == [4, 0, 0, 0]
    assert result['per_category'][2]['positive_agreement'] == 0
    assert result['per_category'][3]['reference_n'] == 1


def test_invalid_vectors_and_undefined_kappa_rejected() -> None:
    with pytest.raises(ValueError):
        agreement(['PLAYER'], [])
    with pytest.raises(ValueError):
        agreement(['PLAYER'], ['PLAYER'])
