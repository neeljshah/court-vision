"""Per-file test for the LANE npbkbo-live-model wire-dispatch stage (CORRECTED FINDING:
KBO's own BASE fit verdict is HONEST_NEGATIVE, disqualified by the same planted
pure-noise control that disqualified NPB -- params were never persisted, so
kbo_live_model.kbo_home_prob() has no frozen params to load and correctly returns None
on every input; live_board wires NO KBO branch, symmetric with NPB).

Covers: (1) kbo_live_model._load_params() honestly returns None (disqualified fit, no
data/domains/kbo/ingame_base_params.json on disk) and kbo_home_prob() therefore returns
None on every input incl. an otherwise-well-formed state, (2) live_board.
live_model_home_prob dispatches NO branch for kbo (same as npb -- both HONEST_NEGATIVE),
and (3) existing sports (mlb/soccer) are unaffected.

Run (per-file only -- never the full suite):
    cd /c/Users/neelj/nba-ai-system && \
        python -m pytest scripts/platformkit/ingame/test_kbo_live_model.py -q
"""
from __future__ import annotations

from scripts.platformkit.frontend import live_board as lb
from scripts.platformkit.ingame import kbo_live_model as klm


# --------------------------------------------------------------- kbo_live_model direct
def test_kbo_load_params_returns_none_disqualified_fit_never_persisted():
    """The KBO BASE fit's own verdict (data/domains/kbo/ingame_base_fit_verdict.json) is
    HONEST_NEGATIVE / disqualified_by_noise_control=true / params_persisted=false -- so
    data/domains/kbo/ingame_base_params.json does not exist on disk and _load_params()
    must honestly return None, never fabricate a slope."""
    assert klm._load_params() is None


def test_kbo_home_prob_none_even_on_well_formed_state():
    """Even a fully-populated, in-range state returns None: there are no persisted
    params to apply the formula with (disqualified fit), not merely a missing-field
    guard -- this locks the honest gap against regression."""
    state = {"state_diff": 2.0, "frac_elapsed": 0.5, "status": "in_progress_or_scheduled"}
    assert klm.kbo_home_prob(state) is None


def test_kbo_home_prob_none_on_missing_state_diff():
    assert klm.kbo_home_prob({"frac_elapsed": 0.5}) is None


def test_kbo_home_prob_none_on_missing_frac_elapsed():
    assert klm.kbo_home_prob({"state_diff": 1.0}) is None


def test_kbo_home_prob_none_on_final_game():
    state = {"state_diff": 4.0, "frac_elapsed": 0.9, "status": "Final"}
    assert klm.kbo_home_prob(state) is None


def test_kbo_home_prob_none_on_out_of_range_frac():
    assert klm.kbo_home_prob({"state_diff": 1.0, "frac_elapsed": 1.5}) is None


def test_kbo_home_prob_none_on_non_dict():
    assert klm.kbo_home_prob(None) is None  # type: ignore[arg-type]


def test_kbo_home_prob_never_raises_on_garbage():
    assert klm.kbo_home_prob({"state_diff": "nope", "frac_elapsed": 0.5}) is None


# ---------------------------------------------------------- dispatch via live_board
def test_dispatch_kbo_stays_unwired_honest_negative():
    """KBO's own BASE fit verdict is HONEST_NEGATIVE (disqualified_by_noise_control) --
    no dispatch branch exists, so even a fully-populated, in-range synthetic state
    returns None, symmetric with npb. Locks the corrected finding against regression."""
    state = {"state_diff": 2.0, "frac_elapsed": 0.4, "status": "in_progress_or_scheduled"}
    assert lb.live_model_home_prob("kbo", state) is None


def test_dispatch_kbo_none_for_real_live_feed_shape_missing_frac():
    """The REAL npb_kbo_live_state feed always emits frac_elapsed=None -- confirms the
    dispatch fails closed on the actual live shape, never fabricating a number."""
    state = {"home": "LG Twins", "away": "KT Wiz", "home_score": 2.0, "away_score": 2.0,
             "state_diff": 0.0, "frac_elapsed": None, "status": "in_progress_or_scheduled"}
    assert lb.live_model_home_prob("kbo", state) is None


def test_dispatch_kbo_none_for_missing_state():
    assert lb.live_model_home_prob("kbo", None) is None  # type: ignore[arg-type]


def test_dispatch_npb_stays_unwired_honest_negative():
    """NPB's own BASE fit verdict is HONEST_NEGATIVE -- no dispatch branch exists, so
    every npb state (even a fully-populated one) returns None, exactly as before this
    lane. This locks the prior gap-test's assertion against regression."""
    state = {"home": "Yomiuri Giants", "away": "Hanshin Tigers",
              "state_diff": 2.0, "frac_elapsed": 0.5, "status": "in_progress_or_scheduled"}
    assert lb.live_model_home_prob("npb", state) is None


def test_existing_sports_unaffected_unknown_sport_still_none():
    assert lb.live_model_home_prob("nhl", {"state_diff": 1.0, "frac_elapsed": 0.5}) is None


def test_existing_sports_unaffected_bad_state_type_still_none():
    assert lb.live_model_home_prob("mlb", "not-a-dict") is None  # type: ignore[arg-type]
