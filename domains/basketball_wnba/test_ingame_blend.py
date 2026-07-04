"""Per-file tests for domains/basketball_wnba/ingame_blend.py.

Covers: sec_remaining / fraction_elapsed regulation math (WNBA 2400s), OT
handling, blend_prob monotonicity + p0-recovery at tipoff, is_buzzer exactness.
Hermetic -- no network, no data files.

Run: cd /c/Users/neelj/nba-ai-system && python -m pytest domains/basketball_wnba/test_ingame_blend.py -q
"""
from __future__ import annotations

import math

import pytest

from domains.basketball_wnba.ingame_blend import (
    OT_SEC,
    PERIOD_SEC,
    REG_SEC,
    LiveState,
    blend_prob,
    fraction_elapsed,
    is_buzzer,
    sec_remaining,
)


# ---------------------------------------------------------------------------
# sec_remaining / regulation constants
# ---------------------------------------------------------------------------

def test_regulation_is_2400s_not_nba_2880():
    assert REG_SEC == 2400.0
    assert PERIOD_SEC == 600.0


def test_sec_remaining_q1_full_clock():
    # Q1 with 10:00 left -> 3 full remaining periods (1800) + 600 = 2400
    assert sec_remaining(1, 600) == 2400.0


def test_sec_remaining_q4_with_time():
    assert sec_remaining(4, 180) == 180.0


def test_sec_remaining_ot_returns_clock_directly():
    assert sec_remaining(5, 200) == 200.0


def test_sec_remaining_final_buzzer_is_zero():
    assert sec_remaining(4, 0) == 0.0


def test_sec_remaining_never_negative():
    assert sec_remaining(4, -5) == 0.0
    assert sec_remaining(5, -1) == 0.0


# ---------------------------------------------------------------------------
# fraction_elapsed
# ---------------------------------------------------------------------------

def test_fraction_elapsed_zero_at_tipoff():
    assert fraction_elapsed(1, 600) == pytest.approx(0.0)


def test_fraction_elapsed_one_at_buzzer():
    assert fraction_elapsed(4, 0) == pytest.approx(1.0)


def test_fraction_elapsed_half_at_halftime():
    # end of Q2 (period=2, clock=0) -> 1200/2400 elapsed = 0.5
    assert fraction_elapsed(2, 0) == pytest.approx(0.5)


def test_fraction_elapsed_clamped_unit_interval():
    for period, clock in [(1, 9999), (4, -50), (2, 300)]:
        f = fraction_elapsed(period, clock)
        assert 0.0 <= f <= 1.0


def test_fraction_elapsed_ot_is_one():
    # OT means regulation is fully elapsed
    assert fraction_elapsed(5, 250) == 1.0
    assert fraction_elapsed(6, 10) == 1.0


# ---------------------------------------------------------------------------
# blend_prob -- p0 recovery, monotonicity, OT
# ---------------------------------------------------------------------------

def test_p0_recovered_exactly_at_tipoff():
    # t=0 (period=1, full clock) -> w_prior=1, ramp=0 -> p_live == p0
    for p0 in [0.2, 0.5, 0.73, 0.91]:
        state = LiveState(period=1, clock_s=PERIOD_SEC, home_score=0, away_score=0)
        p_live = blend_prob(p0, state)
        assert p_live == pytest.approx(p0, abs=1e-9)


def test_tied_score_stays_near_p0_scaled_by_prior_weight():
    # score_diff=0 kills the score term entirely regardless of ramp -> p_live
    # depends only on w_prior(t)*logit(p0); at mid-game with p0=0.5 this must be 0.5.
    state = LiveState(period=2, clock_s=300, home_score=50, away_score=50)
    p_live = blend_prob(0.5, state)
    assert p_live == pytest.approx(0.5, abs=1e-9)


def test_monotone_increasing_in_score_diff():
    # Fixed time, increasing home lead -> strictly increasing p_live.
    p0 = 0.5
    diffs = [-20, -10, -5, 0, 5, 10, 20]
    probs = []
    for d in diffs:
        state = LiveState(period=3, clock_s=200, home_score=60 + max(d, 0),
                           away_score=60 + max(-d, 0))
        probs.append(blend_prob(p0, state))
    for a, b in zip(probs, probs[1:]):
        assert b > a, f"not monotone: {probs}"


def test_late_game_large_lead_pushes_toward_one():
    state = LiveState(period=4, clock_s=30, home_score=90, away_score=60)
    p_live = blend_prob(0.5, state)
    assert p_live > 0.9


def test_late_game_large_deficit_pushes_toward_zero():
    state = LiveState(period=4, clock_s=30, home_score=60, away_score=90)
    p_live = blend_prob(0.5, state)
    assert p_live < 0.1


def test_ot_handling_uses_ot_clock_and_full_ramp():
    # OT: fraction_elapsed=1 -> w_prior=0 (prior fully faded), ramp uses
    # sec_remaining=clock_s directly (OT_SEC=300 convention documented, not
    # asserted here since sec_remaining(period>=5) ignores period length).
    state = LiveState(period=5, clock_s=OT_SEC, home_score=80, away_score=78)
    p_live = blend_prob(0.5, state)
    assert 0.5 < p_live < 1.0
    # A big OT lead still pushes decisively toward 1.
    state_blowout = LiveState(period=5, clock_s=OT_SEC, home_score=95, away_score=78)
    assert blend_prob(0.5, state_blowout) > blend_prob(0.5, state)


def test_blend_prob_always_in_unit_interval():
    for p0 in [0.01, 0.5, 0.99]:
        for period in [1, 2, 3, 4, 5]:
            for diff in [-50, 0, 50]:
                state = LiveState(period=period, clock_s=100,
                                   home_score=60 + max(diff, 0),
                                   away_score=60 + max(-diff, 0))
                p = blend_prob(p0, state)
                assert 0.0 <= p <= 1.0
                assert math.isfinite(p)


# ---------------------------------------------------------------------------
# is_buzzer
# ---------------------------------------------------------------------------

def test_is_buzzer_true_at_q4_zero_clock():
    state = LiveState(period=4, clock_s=0.0, home_score=80, away_score=70)
    assert is_buzzer(state) is True


def test_is_buzzer_false_before_q4_ends():
    state = LiveState(period=4, clock_s=1.0, home_score=80, away_score=70)
    assert is_buzzer(state) is False


def test_is_buzzer_false_in_ot():
    state = LiveState(period=5, clock_s=0.0, home_score=80, away_score=79)
    assert is_buzzer(state) is False


def test_is_buzzer_false_in_earlier_periods():
    for period in [1, 2, 3]:
        state = LiveState(period=period, clock_s=0.0, home_score=10, away_score=5)
        assert is_buzzer(state) is False


# ---------------------------------------------------------------------------
# no foul-state dependency (honest degrade)
# ---------------------------------------------------------------------------

def test_live_state_has_no_foul_fields():
    """LiveState carries no players/foul/bonus fields -- the honest degrade
    (dropped, not zero-filled/faked) requested by the brief."""
    state = LiveState(period=2, clock_s=300, home_score=40, away_score=38)
    for absent in ("players", "foul_diff", "bonus", "home_bonus", "away_bonus"):
        assert not hasattr(state, absent)
