"""Tests for Shin (1992) devig vs proportional power-sum."""

from __future__ import annotations

import math

import pytest

from src.prediction.devig import (
    american_to_prob,
    proportional_devig,
    shin_devig,
    shin_devig_pair,
)


def test_no_vig_returns_inputs():
    # If implied probs already sum to 1, devig is identity.
    probs = [0.4, 0.6]
    out = shin_devig(probs)
    assert sum(out) == pytest.approx(1.0, abs=1e-9)
    assert out[0] == pytest.approx(0.4, abs=1e-9)
    assert out[1] == pytest.approx(0.6, abs=1e-9)


def test_proportional_normalizes_to_one():
    out = proportional_devig([0.55, 0.50])  # overround = 1.05
    assert sum(out) == pytest.approx(1.0, abs=1e-12)
    assert out[0] == pytest.approx(0.55 / 1.05, abs=1e-9)


def test_shin_sums_to_one():
    out = shin_devig([0.55, 0.50])
    assert sum(out) == pytest.approx(1.0, abs=1e-9)


def test_shin_diverges_from_proportional_on_favourite():
    # On a heavy favourite line (-300 / +220), Shin and proportional devig
    # disagree. Proportional assumes the overround is split evenly between
    # outcomes; Shin assumes the book loads more vig onto the longshot to
    # protect against insider information. Result: Shin returns a HIGHER
    # probability for the favourite than proportional does.
    over_odds, under_odds = -300, +220
    pi_over = american_to_prob(over_odds)   # ~0.75
    pi_under = american_to_prob(under_odds)  # ~0.3125
    prop = proportional_devig([pi_over, pi_under])
    shin = shin_devig([pi_over, pi_under])
    assert shin[0] > prop[0], (
        f"Shin should give favourite HIGHER prob than proportional; "
        f"got Shin={shin[0]:.4f} prop={prop[0]:.4f}"
    )
    assert shin[1] < prop[1]
    # And the gap should be material (>0.1pp) at this vig level.
    assert abs(shin[0] - prop[0]) > 0.001


def test_shin_pair_matches_list_form():
    a, b = shin_devig_pair(-110, -110)
    out = shin_devig([american_to_prob(-110), american_to_prob(-110)])
    assert a == pytest.approx(out[0], abs=1e-9)
    assert b == pytest.approx(out[1], abs=1e-9)


def test_shin_balanced_market_is_half():
    a, b = shin_devig_pair(-110, -110)  # standard juice
    assert a == pytest.approx(0.5, abs=1e-9)
    assert b == pytest.approx(0.5, abs=1e-9)


def test_american_to_prob_known_values():
    assert american_to_prob(+100) == pytest.approx(0.5)
    assert american_to_prob(-200) == pytest.approx(2 / 3, abs=1e-9)
    assert american_to_prob(+300) == pytest.approx(0.25)
