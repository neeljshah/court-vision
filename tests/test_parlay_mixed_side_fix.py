"""Tests for the gated CV_PARLAY_FIX_MIXED_SIDE covariance fix.

Default (flag OFF) MUST be byte-identical to the historical behavior: a mixed
OVER/UNDER same-game pair flips the sign of rho. Flag ON keeps the physically
correct (un-flipped) stat covariance.
"""
import importlib

import src.prediction.parlay_engine as pe


def _pair(side_a, side_b):
    base = {"game_id": "G1", "player_id": 1, "team": "OKC"}
    a = {**base, "prop_stat": "pts", "side": side_a}
    b = {**base, "prop_stat": "reb", "side": side_b}
    return a, b


def test_same_side_unaffected_by_flag():
    a, b = _pair("over", "over")
    pe._PARLAY_FIX_MIXED_SIDE = False
    off = pe._correlation(a, b)
    pe._PARLAY_FIX_MIXED_SIDE = True
    on = pe._correlation(a, b)
    pe._PARLAY_FIX_MIXED_SIDE = False
    assert off == on, "same-side correlation must not depend on the flag"
    assert off > 0, "pts/reb same-player same-side rho should be positive"


def test_mixed_side_flag_off_preserves_flip():
    """Flag OFF = byte-identical current behavior: mixed side flips sign (negative)."""
    a, b = _pair("over", "under")
    pe._PARLAY_FIX_MIXED_SIDE = False
    off = pe._correlation(a, b)
    assert off < 0, "default (flag OFF) must preserve the historical sign flip"


def test_mixed_side_flag_on_keeps_physical_sign():
    """Flag ON = correct: mixed side keeps the true (positive) stat covariance."""
    a, b = _pair("over", "under")
    pe._PARLAY_FIX_MIXED_SIDE = True
    on = pe._correlation(a, b)
    pe._PARLAY_FIX_MIXED_SIDE = False
    assert on > 0, "fix ON must keep the physical positive pts/reb correlation"


def test_flag_off_equals_magnitude_of_flag_on():
    """The fix only changes SIGN for mixed side, not magnitude."""
    a, b = _pair("over", "under")
    pe._PARLAY_FIX_MIXED_SIDE = False
    off = pe._correlation(a, b)
    pe._PARLAY_FIX_MIXED_SIDE = True
    on = pe._correlation(a, b)
    pe._PARLAY_FIX_MIXED_SIDE = False
    assert abs(off) == abs(on) and off == -on


def test_default_module_flag_is_off():
    """Importing with no env set must leave the flag OFF (safe default)."""
    importlib.reload(pe)
    assert pe._PARLAY_FIX_MIXED_SIDE is False
