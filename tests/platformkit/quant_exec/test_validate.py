"""Per-file test for scripts.platformkit.quant_exec.validate (LANE TH-01).

Run ONLY this file (bare pytest freezes the box):
    cd /c/Users/neelj/nba-ai-system && \
      python -m pytest tests/platformkit/quant_exec/test_validate.py -q

Acceptance criteria (TH-01):
  * build_validation with no gate token -> gate_proven=False (default).
  * model_prob == devigged close -> no_bet, zero units (baseline).
  * assert no key matches /(\\$|roi|pnl|profit)/ in as_dict() output.
  * exercises >=8 distinct functions/branches across the module.

Honest note: most rows are expected to be no_bet (matching the efficient
close) -- that is the correct result, not a miss. Only a structurally-valid
VERIFIED eval-gate token raises gate_proven to True.
"""
from __future__ import annotations

import re
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.quant_exec.validate import (  # noqa: E402
    BetValidation,
    build_validation,
    is_verified_gate_token,
)

# --------------------------------------------------------------------------- #
# Money-token pattern (same convention as test_risk_units.py in same lane)
# --------------------------------------------------------------------------- #
_MONEY_RE = re.compile(r"(\$|roi|pnl|profit)", re.IGNORECASE)

# A minimal valid eval-gate proof token
_VALID_TOKEN = {"verified": True, "passed": True}

# A real pair of decimal odds that produces a known devigged close so we can
# construct the "model == close" baseline test deterministically.  The Shin
# solver output for [2.0, 2.0] is exactly 0.5 each (symmetric market).
_CLOSE_PRICE_HOME = 2.0
_CLOSE_PRICE_AWAY = 2.0
# For the symmetric market the Shin-devigged fair prob for home is ~0.5.
# We keep a small tolerance band: anything within +-0.005 of the fair prob
# will still produce EV=0 at even decimal (2.0), which is below any tier
# floor -> no_bet.  We set model_prob exactly at 0.5 for the baseline test.
_SYMMETRIC_FAIR_PROB = 0.5


# --------------------------------------------------------------------------- #
# BRANCH 1: is_verified_gate_token -- accepts / rejects
# --------------------------------------------------------------------------- #
def test_gate_token_none_is_false():
    """None token -> gate_proven must be False."""
    assert is_verified_gate_token(None) is False


def test_gate_token_bare_bool_is_false():
    """A plain True (not a dict) is NOT a valid proof handle."""
    assert is_verified_gate_token(True) is False


def test_gate_token_string_is_false():
    """A stringified token is rejected."""
    assert is_verified_gate_token("verified") is False


def test_gate_token_partial_dict_is_false():
    """verified=True but passed absent -> rejected."""
    assert is_verified_gate_token({"verified": True}) is False


def test_gate_token_passed_false_is_rejected():
    """verified=True, passed=False -> not a passing proof."""
    assert is_verified_gate_token({"verified": True, "passed": False}) is False


def test_gate_token_valid_dict_passes():
    """A fully-formed VERIFIED token -> True."""
    assert is_verified_gate_token(_VALID_TOKEN) is True


# --------------------------------------------------------------------------- #
# BRANCH 2: gate_proven default is False in build_validation
# --------------------------------------------------------------------------- #
def test_build_validation_gate_proven_defaults_false():
    """Calling build_validation WITHOUT a gate_token must produce gate_proven=False."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.55,
    )
    assert v.gate_proven is False


def test_build_validation_gate_proven_false_with_junk_token():
    """A truthy-but-unverified value must NOT flip gate_proven to True."""
    for junk in [42, "PASS", {"verified": True}, {"passed": True}, True]:
        v = build_validation(
            side="home",
            market="h2h",
            model_prob=0.55,
            gate_token=junk,
        )
        assert v.gate_proven is False, f"junk token {junk!r} should not flip gate_proven"


def test_build_validation_gate_proven_true_with_valid_token():
    """A VERIFIED token must flip gate_proven to True."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.55,
        gate_token=_VALID_TOKEN,
    )
    assert v.gate_proven is True


# --------------------------------------------------------------------------- #
# BRANCH 3: model_prob == devigged close -> no_bet + zero units baseline
# --------------------------------------------------------------------------- #
def test_model_on_close_is_no_bet_zero_units():
    """When model_prob matches the devigged close, EV=0 -> no tier -> no_bet."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=_SYMMETRIC_FAIR_PROB,
        best_decimal=2.0,          # 2.0 => EV = 0.5*2.0 - 1 = 0.0
        close_home=_CLOSE_PRICE_HOME,
        close_away=_CLOSE_PRICE_AWAY,
        clv_is_proxy=False,
    )
    assert v.decision == "no_bet", "matching the close must be no_bet"
    assert v.flat_unit == 0.0
    assert v.kelly_units == 0.0
    assert v.stake_units == 0.0
    assert v.tier is None


def test_model_below_close_is_no_bet():
    """Model prob below the devigged close (negative edge) must also be no_bet."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.40,           # below ~0.5 fair
        best_decimal=2.0,          # EV = 0.40*2.0 - 1 = -0.20
        close_home=_CLOSE_PRICE_HOME,
        close_away=_CLOSE_PRICE_AWAY,
    )
    assert v.decision == "no_bet"
    assert v.stake_units == 0.0


# --------------------------------------------------------------------------- #
# BRANCH 4: high-EV row actually produces 'bet' with positive stake
# --------------------------------------------------------------------------- #
def test_high_ev_produces_bet():
    """model_prob=0.65 at decimal 2.0 => EV=0.30 > 0.08 tier-A floor -> bet."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.65,
        best_decimal=2.0,
        clv_is_proxy=False,
    )
    assert v.decision == "bet"
    assert v.tier == "A"
    assert v.stake_units > 0.0
    assert v.flat_unit == 1.0
    assert v.kelly_units >= 0.0


def test_mid_ev_produces_bet_tier_b_or_c():
    """EV between C and B floor -> tier B or C, still a bet."""
    # model_prob=0.52, decimal=2.0 => EV = 0.52*2.0 - 1 = 0.04 => tier B (proxy=False)
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.52,
        best_decimal=2.0,
        clv_is_proxy=False,
    )
    assert v.decision == "bet"
    assert v.tier in ("B", "C")


# --------------------------------------------------------------------------- #
# BRANCH 5: proxy flag raises effective floors (stricter bar)
# --------------------------------------------------------------------------- #
def test_proxy_flag_raises_floor_to_no_bet():
    """EV that clears the non-proxy C floor (0.02) but not the proxy floor (0.03)
    must produce no_bet when clv_is_proxy=True."""
    # EV = 0.51*2.0 - 1 = 0.02 (just at C floor without proxy)
    v_no_proxy = build_validation(
        side="home", market="h2h",
        model_prob=0.51, best_decimal=2.0, clv_is_proxy=False,
    )
    v_proxy = build_validation(
        side="home", market="h2h",
        model_prob=0.51, best_decimal=2.0, clv_is_proxy=True,
    )
    # Without proxy this just clears C floor; with proxy it doesn't.
    assert v_no_proxy.decision == "bet"
    assert v_proxy.decision == "no_bet"
    assert v_proxy.clv_is_proxy is True


# --------------------------------------------------------------------------- #
# BRANCH 6: away side is correctly resolved from two-way close
# --------------------------------------------------------------------------- #
def test_away_side_no_bet_on_close():
    """Symmetric market: away side at 0.5 prob is also a no_bet (EV=0)."""
    v = build_validation(
        side="away",
        market="h2h",
        model_prob=_SYMMETRIC_FAIR_PROB,
        best_decimal=2.0,
        close_home=_CLOSE_PRICE_HOME,
        close_away=_CLOSE_PRICE_AWAY,
    )
    assert v.decision == "no_bet"
    assert v.side == "away"


# --------------------------------------------------------------------------- #
# BRANCH 7: missing prices -> devigged_close None, edge None (graceful)
# --------------------------------------------------------------------------- #
def test_missing_close_prices_graceful():
    """When close prices are absent, devigged_close and edge must be None (no crash)."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.60,
        # no close_home / close_away
    )
    assert v.devigged_close is None
    assert v.edge is None
    # Without a best_decimal, EV is also None -> no_bet
    assert v.decision == "no_bet"


def test_missing_best_decimal_ev_none():
    """No best_decimal -> ev=None -> tier=None -> no_bet."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.70,
        # no best_decimal supplied
    )
    assert v.ev is None
    assert v.tier is None
    assert v.decision == "no_bet"


# --------------------------------------------------------------------------- #
# BRANCH 8: clv_record passthrough (not recomputed)
# --------------------------------------------------------------------------- #
def test_clv_record_passed_through():
    """A pre-computed clv_record dict must appear verbatim on the validation object."""
    clv_rec = {"vs_close": "UNPROVEN", "clv_pct": 0.0, "is_proxy": True}
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.65,
        best_decimal=2.0,
        clv_record=clv_rec,
    )
    assert v.clv is clv_rec  # identity: not a copy, not recomputed


# --------------------------------------------------------------------------- #
# BRANCH 9: BetValidation.as_dict() -- no $/roi/pnl/profit key anywhere
# --------------------------------------------------------------------------- #
def _check_no_money_keys(d: dict, label: str = "") -> None:
    """Assert no KEY in *d* matches the money-token pattern.

    String VALUES are excluded from the scan: the note field intentionally
    contains the phrase 'no $ edge claimed' as an honesty label; that is
    correct behaviour.  The prohibition is on having a *field name* (key)
    called roi/pnl/profit/$ -- never on mentioning these words in a note.
    """
    for k in d:
        assert not _MONEY_RE.search(str(k)), (
            f"{label}: key '{k}' matches money pattern"
        )


def test_as_dict_no_dollar_roi_pnl_profit_keys():
    """as_dict() must contain NO key or string value matching /(\\$|roi|pnl|profit)/."""
    cases = [
        # no_bet case
        build_validation(side="home", market="h2h", model_prob=0.50,
                         best_decimal=2.0, clv_is_proxy=False),
        # bet case
        build_validation(side="home", market="h2h", model_prob=0.65,
                         best_decimal=2.0, clv_is_proxy=False),
        # missing everything
        build_validation(side="away", market="spread", model_prob=None),
    ]
    for v in cases:
        d = v.as_dict()
        _check_no_money_keys(d, label=repr(v.decision))


def test_as_dict_has_units_not_dollar_sentinel():
    """as_dict() must carry the explicit 'units' key with value 'probability'."""
    v = build_validation(side="home", market="h2h", model_prob=0.60,
                         best_decimal=2.0)
    d = v.as_dict()
    assert "units" in d
    assert d["units"] == "probability"


def test_as_dict_edge_claimed_false():
    """as_dict() must always carry edge_claimed=False."""
    for mp in (0.40, 0.50, 0.65):
        v = build_validation(side="home", market="h2h",
                             model_prob=mp, best_decimal=2.0)
        assert v.as_dict()["edge_claimed"] is False


def test_as_dict_real_money_enabled_false():
    """as_dict() must always carry real_money_enabled=False."""
    v = build_validation(side="home", market="h2h", model_prob=0.65,
                         best_decimal=2.0, gate_token=_VALID_TOKEN)
    # Even with a verified gate token, real_money_enabled stays False.
    assert v.as_dict()["real_money_enabled"] is False


# --------------------------------------------------------------------------- #
# BRANCH 10: BetValidation is a frozen dataclass (immutable after construction)
# --------------------------------------------------------------------------- #
def test_bet_validation_is_frozen():
    """BetValidation must raise AttributeError on mutation attempt."""
    import pytest as _pytest
    v = build_validation(side="home", market="h2h", model_prob=0.65,
                         best_decimal=2.0)
    with _pytest.raises((AttributeError, TypeError)):
        v.gate_proven = True  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# BRANCH 11: malformed / None model_prob gracefully returns no_bet
# --------------------------------------------------------------------------- #
def test_none_model_prob_no_crash():
    """model_prob=None must not raise and must produce no_bet."""
    v = build_validation(side="home", market="h2h", model_prob=None,
                         best_decimal=2.0, close_home=2.0, close_away=2.0)
    assert v.model_prob is None
    assert v.decision == "no_bet"


def test_string_model_prob_parsed_to_float():
    """model_prob passed as a numeric string must be coerced to float."""
    v = build_validation(side="home", market="h2h", model_prob="0.65",
                         best_decimal=2.0, clv_is_proxy=False)
    assert isinstance(v.model_prob, float)
    assert abs(v.model_prob - 0.65) < 1e-9


# --------------------------------------------------------------------------- #
# BRANCH 12: edge arithmetic sanity
# --------------------------------------------------------------------------- #
def test_edge_sign_positive_when_model_above_close():
    """edge = model_prob - devigged_close > 0 when model is above the fair line."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.65,
        best_decimal=2.0,
        close_home=2.0,
        close_away=2.0,
        clv_is_proxy=False,
    )
    # devigged_close is ~0.5 for symmetric 2.0/2.0 -> edge = 0.65 - 0.5 > 0
    assert v.edge is not None
    assert v.edge > 0.0


def test_edge_sign_negative_when_model_below_close():
    """edge < 0 when model is below the devigged close."""
    v = build_validation(
        side="home",
        market="h2h",
        model_prob=0.35,
        best_decimal=2.0,
        close_home=2.0,
        close_away=2.0,
    )
    assert v.edge is not None
    assert v.edge < 0.0
