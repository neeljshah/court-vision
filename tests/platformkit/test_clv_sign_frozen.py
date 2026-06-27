"""tests.platformkit.test_clv_sign_frozen -- golden-constant guard for CLV sign + magnitude.

This file exists because the repo has a documented 'record_clv backwards' bug
class: a silent sign flip made CLV appear positive when it was negative. These
tests pin the sign AND magnitude against hand-derived constants so any future
regression is caught immediately.

DERIVATION (do NOT replace these constants by calling the function):

    clv_pct = (fair_close - taken_p) / taken_p * 100.0   [from clv_ledger module doc]
    taken_p  = 1 / taken_decimal
    fair_close = Shin-devigged fair probability for the BET SIDE

    For the closing line home=1.50, away=2.70:
      booksum   = 1/1.50 + 1/2.70 = 0.6667 + 0.3704 = 1.0370 (vig present)
      Shin devig solves for z s.t. sum(fair_p) == 1, yielding:
        fair_home = 0.648148148...  (full Shin output)
        fair_away = 0.351851852...

    ScenA HOME BETTER  taken=2.50  taken_p=0.40
      clv = (0.648148 - 0.40) / 0.40 * 100  = 62.037037  > 0  beat_close=True
    ScenB HOME WORSE   taken=1.30  taken_p=0.76923077
      clv = (0.648148 - 0.769231) / 0.769231 * 100 = -15.740741 < 0  beat_close=False
    ScenC AWAY WORSE   taken=1.90  taken_p=0.52631579
      clv = (0.351852 - 0.526316) / 0.526316 * 100 = -33.148148 < 0  beat_close=False
    ScenD AWAY BETTER  taken=3.10  taken_p=0.32258065
      clv = (0.351852 - 0.322581) / 0.322581 * 100 =   9.074074  > 0  beat_close=True

    For the closing line home=1.9091, away=1.9091 (symmetric, booksum ~1.0476):
      Shin devig -> fair_home = fair_away = 0.5 (exactly, by symmetry)
    ScenE EQUAL        taken=2.0   taken_p=0.50
      clv = (0.5 - 0.5) / 0.5 * 100 = 0.0  beat_close=False (not strictly >0)

Run ONLY this file:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/test_clv_sign_frozen.py -q
"""
from __future__ import annotations

import pytest
from scripts.platformkit.clv_ledger import compute_clv

# ---------------------------------------------------------------------------
# Pre-registered golden constants (hand-derived -- see module docstring above).
# NEVER update these to match the function; fix the function instead.
# ---------------------------------------------------------------------------

# Asymmetric two-way close: home=-200 (1.50), away=+170 (2.70)
# Shin-devigged: fair_home = 0.64814815, fair_away = 0.35185185
_CLOSE_HOME_1_50 = 1.50
_CLOSE_AWAY_2_70 = 2.70

_FAIR_HOME_ASYM = 0.64814815   # 8dp rounded, matches compute_clv output
_FAIR_AWAY_ASYM = 0.35185185

# Scenario A: bet HOME at 2.50 (implied 0.40) vs close 1.50/2.70 -> BETTER price
_TAKEN_A = 2.50
_TAKEN_P_A = 0.40              # 1 / 2.50 exactly
_CLV_A = 62.037037             # (0.64814815 - 0.40) / 0.40 * 100, rounded 6dp
_BEAT_A = True

# Scenario B: bet HOME at 1.30 (implied ~0.7692) vs close 1.50/2.70 -> WORSE price
_TAKEN_B = 1.30
_TAKEN_P_B = 0.76923077        # 1 / 1.30 rounded 8dp
_CLV_B = -15.740741            # (0.64814815 - 0.76923077) / 0.76923077 * 100
_BEAT_B = False

# Scenario C: bet AWAY at 1.90 (implied ~0.5263) vs close 1.50/2.70 -> WORSE price
_TAKEN_C = 1.90
_TAKEN_P_C = 0.52631579        # 1 / 1.90 rounded 8dp
_CLV_C = -33.148148            # (0.35185185 - 0.52631579) / 0.52631579 * 100
_BEAT_C = False

# Scenario D: bet AWAY at 3.10 (implied ~0.3226) vs close 1.50/2.70 -> BETTER price
_TAKEN_D = 3.10
_TAKEN_P_D = 0.32258065        # 1 / 3.10 rounded 8dp
_CLV_D = 9.074074              # (0.35185185 - 0.32258065) / 0.32258065 * 100
_BEAT_D = True

# Symmetric two-way close: home=-105/away=-105 (1.9091/1.9091)
# Shin devig -> fair = 0.5 / 0.5 exactly by symmetry
_CLOSE_HOME_SYM = 1.9091
_CLOSE_AWAY_SYM = 1.9091

# Scenario E: bet HOME at 2.0 (implied 0.50) vs symmetric 1.9091/1.9091 -> EQUAL
_TAKEN_E = 2.0
_TAKEN_P_E = 0.50              # 1 / 2.0 exactly
_CLV_E = 0.0                   # (0.5 - 0.5) / 0.5 * 100 = 0
_BEAT_E = False                # not strictly > 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_ABS_TOL = 1e-4   # 4dp tolerance; clv_pct rounds to 6dp so 1e-4 is generous


def _check(result: dict, expected_taken_p: float, expected_fair_close: float,
           expected_clv_pct: float, expected_beat_close: bool,
           expected_side_fair: float) -> None:
    """Assert sign + magnitude invariants on a compute_clv result dict."""
    assert result["taken_p"] == pytest.approx(expected_taken_p, abs=_ABS_TOL)
    assert result["fair_close"] == pytest.approx(expected_fair_close, abs=_ABS_TOL)
    assert result["clv_pct"] == pytest.approx(expected_clv_pct, abs=_ABS_TOL)
    assert result["beat_close"] is expected_beat_close
    # SIGN invariants -- the core regression guard
    if expected_clv_pct > 0:
        assert result["clv_pct"] > 0, "CLV sign FLIPPED: expected positive, got negative"
    elif expected_clv_pct < 0:
        assert result["clv_pct"] < 0, "CLV sign FLIPPED: expected negative, got positive"


# ---------------------------------------------------------------------------
# Scenario A -- HOME side, BETTER price than the close
# ---------------------------------------------------------------------------
def test_home_better_than_close_sign_positive():
    """HOME bet at 2.50, close home=1.50/away=2.70: taken_p=0.40 < fair_home -> clv > 0."""
    r = compute_clv("home", _TAKEN_A, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    _check(r, _TAKEN_P_A, _FAIR_HOME_ASYM, _CLV_A, _BEAT_A, _FAIR_HOME_ASYM)


def test_home_better_beat_close_true():
    r = compute_clv("home", _TAKEN_A, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["beat_close"] is True


def test_home_better_magnitude():
    """Golden constant: clv_pct must be ~62.037037."""
    r = compute_clv("home", _TAKEN_A, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["clv_pct"] == pytest.approx(_CLV_A, abs=_ABS_TOL)


# ---------------------------------------------------------------------------
# Scenario B -- HOME side, WORSE price than the close
# ---------------------------------------------------------------------------
def test_home_worse_than_close_sign_negative():
    """HOME bet at 1.30, close home=1.50/away=2.70: taken_p=0.769 > fair_home -> clv < 0."""
    r = compute_clv("home", _TAKEN_B, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    _check(r, _TAKEN_P_B, _FAIR_HOME_ASYM, _CLV_B, _BEAT_B, _FAIR_HOME_ASYM)


def test_home_worse_beat_close_false():
    r = compute_clv("home", _TAKEN_B, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["beat_close"] is False


def test_home_worse_magnitude():
    """Golden constant: clv_pct must be ~-15.740741."""
    r = compute_clv("home", _TAKEN_B, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["clv_pct"] == pytest.approx(_CLV_B, abs=_ABS_TOL)


# ---------------------------------------------------------------------------
# Scenario C -- AWAY side, WORSE price (covers away-side correct sign extraction)
# ---------------------------------------------------------------------------
def test_away_worse_than_close_sign_negative():
    """AWAY bet at 1.90, close home=1.50/away=2.70: taken_p=0.526 > fair_away -> clv < 0."""
    r = compute_clv("away", _TAKEN_C, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    _check(r, _TAKEN_P_C, _FAIR_AWAY_ASYM, _CLV_C, _BEAT_C, _FAIR_AWAY_ASYM)


def test_away_worse_beat_close_false():
    r = compute_clv("away", _TAKEN_C, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["beat_close"] is False


def test_away_worse_magnitude():
    """Golden constant: clv_pct must be ~-33.148148."""
    r = compute_clv("away", _TAKEN_C, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["clv_pct"] == pytest.approx(_CLV_C, abs=_ABS_TOL)


def test_away_uses_fair_away_not_fair_home():
    """Regression guard: away bet must use fair_away (0.3519), not fair_home (0.6481)."""
    r = compute_clv("away", _TAKEN_C, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    # If the function accidentally used fair_home for an away bet, clv would be
    # wildly wrong: (0.6481 - 0.5263) / 0.5263 * 100 = +23.1 -> positive, not -33.
    assert r["fair_close"] == pytest.approx(_FAIR_AWAY_ASYM, abs=_ABS_TOL)
    assert r["clv_pct"] < 0


# ---------------------------------------------------------------------------
# Scenario D -- AWAY side, BETTER price (covers away-side positive sign)
# ---------------------------------------------------------------------------
def test_away_better_than_close_sign_positive():
    """AWAY bet at 3.10, close home=1.50/away=2.70: taken_p=0.323 < fair_away -> clv > 0."""
    r = compute_clv("away", _TAKEN_D, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    _check(r, _TAKEN_P_D, _FAIR_AWAY_ASYM, _CLV_D, _BEAT_D, _FAIR_AWAY_ASYM)


def test_away_better_beat_close_true():
    r = compute_clv("away", _TAKEN_D, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["beat_close"] is True


def test_away_better_magnitude():
    """Golden constant: clv_pct must be ~9.074074."""
    r = compute_clv("away", _TAKEN_D, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r["clv_pct"] == pytest.approx(_CLV_D, abs=_ABS_TOL)


# ---------------------------------------------------------------------------
# Scenario E -- EQUAL: taken price at fair value -> clv near zero, beat_close False
# ---------------------------------------------------------------------------
def test_equal_price_clv_near_zero():
    """Symmetric close 1.9091/1.9091; taken=2.0 (implied 0.50 = fair): clv ~0."""
    r = compute_clv("home", _TAKEN_E, _CLOSE_HOME_SYM, _CLOSE_AWAY_SYM)
    assert r["clv_pct"] == pytest.approx(_CLV_E, abs=_ABS_TOL)


def test_equal_price_beat_close_false():
    """Equal price -> clv == 0.0 -> beat_close must be False (not strictly > 0)."""
    r = compute_clv("home", _TAKEN_E, _CLOSE_HOME_SYM, _CLOSE_AWAY_SYM)
    assert r["beat_close"] is False


# ---------------------------------------------------------------------------
# Cross-side consistency: swapping home/away sides on asymmetric market must
# flip the fair_close selection correctly.
# ---------------------------------------------------------------------------
def test_home_and_away_fair_probs_are_distinct_on_asymmetric_market():
    """fair_close for home bet != fair_close for away bet on asymmetric market."""
    r_home = compute_clv("home", 2.0, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    r_away = compute_clv("away", 2.0, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    assert r_home["fair_close"] != pytest.approx(r_away["fair_close"], abs=_ABS_TOL)
    # home side is the favourite: fair_home > 0.5 > fair_away
    assert r_home["fair_close"] > 0.5
    assert r_away["fair_close"] < 0.5


def test_fair_probs_from_asymmetric_close_sum_to_one():
    """fair_home + fair_away must sum to 1 (Shin devig invariant, not round-trip)."""
    r_home = compute_clv("home", 2.0, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    r_away = compute_clv("away", 2.0, _CLOSE_HOME_1_50, _CLOSE_AWAY_2_70)
    total = r_home["fair_close"] + r_away["fair_close"]
    assert total == pytest.approx(1.0, abs=1e-5)


# ---------------------------------------------------------------------------
# Input validation guard -- bad side string must raise ValueError
# ---------------------------------------------------------------------------
def test_invalid_side_raises():
    with pytest.raises(ValueError, match="home.*away"):
        compute_clv("draw", 2.0, 1.50, 2.70)
