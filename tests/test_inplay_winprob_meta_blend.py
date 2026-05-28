"""Tests for the iter68 v6_hp + iter71 meta_blend wiring in inplay_winprob.

Covers:
  * v6_hp boosters load for endQ1/endQ2/endQ3
  * v7_bag5 (5 seeds) loads for endQ2 and returns averaged prediction
  * iter62 isotonic loads as a wrapped IsotonicRegression
  * meta_blend composes correctly for endQ1 + endQ2 (skipped for endQ3 since
    v4_fouls features are not wired into the live snapshot path)
  * predict_home_win_prob routes through meta_blend (Q1, Q2) → v6_hp (Q3)
  * active_stack reports the correct layer + component load flags
  * Monotonicity in score_margin still holds under the new routing

Skips if artifacts missing (matches the test_inplay_winprob.py pattern).
"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from src.prediction.inplay_winprob import (  # noqa: E402
    SNAPSHOTS,
    _load_iter62_iso,
    _load_v6_hp,
    _load_v7_bag5_endq2,
    _predict_meta_blend,
    _predict_v6_hp,
    _predict_v7_bag5,
    active_stack,
    predict_home_win_prob,
    reset_cache,
)

_MODELS = os.path.join(PROJECT_DIR, "data", "models")


def _v6_hp_present() -> bool:
    return all(os.path.exists(
        os.path.join(_MODELS, f"inplay_winprob_endq{n}_v6_hp.lgb"))
        for n in (1, 2, 3))


def _meta_blend_present() -> bool:
    return all(os.path.exists(
        os.path.join(_MODELS, f"inplay_meta_blend_endq{n}.json"))
        for n in (1, 2, 3))


pytestmark = pytest.mark.skipif(
    not (_v6_hp_present() and _meta_blend_present()),
    reason="iter68 v6_hp or iter71 meta_blend artifacts missing",
)


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_cache()
    yield
    reset_cache()


# Synthetic snapshot: home up 5 at end of each period, average pace, slight
# home pregame favorite. Same shape as features_from_snapshot would produce.
def _make_feats(snap: str, score_margin: float = 5.0) -> dict:
    base = {
        "score_margin": score_margin,
        "total_pts": 100.0 if snap == "endQ1" else (180.0 if snap == "endQ2" else 200.0),
        "pace_so_far": 2.5 if snap == "endQ1" else 3.0,
        "q1_delta": 2.0,
        "last_q_margin": 2.0,
        "pregame_win_prob": 0.55,
        "home_team_id": 1610612747,  # LAL
        "season": "2024-25",
    }
    if snap in ("endQ2", "endQ3"):
        base["q2_delta"] = 2.0
    if snap == "endQ3":
        base["q3_delta"] = 1.0
        base["q1_usg_avg"] = 0.25
        base["halftime_pace_shift"] = 0.0
        base["trailing_team_q4_usg_hhi"] = 0.2
    return base


# ── v6_hp loader + predictor ──────────────────────────────────────────────────

@pytest.mark.parametrize("snap", SNAPSHOTS)
def test_v6_hp_loads_and_predicts(snap):
    booster = _load_v6_hp(snap)
    assert booster is not None, f"v6_hp booster for {snap} failed to load"
    p = _predict_v6_hp(_make_feats(snap), snap)
    assert p is not None and 0.0 <= p <= 1.0, \
        f"v6_hp({snap}) returned {p}, expected float in [0,1]"


# ── v7_bag5 (endQ2 only) ──────────────────────────────────────────────────────

def test_v7_bag5_endq2_loads_5_boosters():
    bag = _load_v7_bag5_endq2()
    if not bag:
        pytest.skip("v7_bag5 endQ2 artifacts missing")
    assert len(bag) == 5, f"expected 5 seed boosters, got {len(bag)}"


def test_v7_bag5_returns_unit_interval_for_endq2():
    bag = _load_v7_bag5_endq2()
    if not bag:
        pytest.skip("v7_bag5 endQ2 artifacts missing")
    p = _predict_v7_bag5(_make_feats("endQ2"))
    assert p is not None and 0.0 <= p <= 1.0


# ── iter62 isotonic loader ────────────────────────────────────────────────────

@pytest.mark.parametrize("snap", SNAPSHOTS)
def test_iter62_isotonic_loads_unwrapped_from_joblib_dict(snap):
    iso = _load_iter62_iso(snap)
    if iso is None:
        pytest.skip(f"iter62 isotonic missing for {snap}")
    # The on-disk artifact is a dict bundle; loader must unwrap to the
    # IsotonicRegression so .predict() / .transform() work directly.
    assert hasattr(iso, "predict"), \
        f"iter62 iso for {snap} not unwrapped from joblib dict"


# ── meta_blend predictor ──────────────────────────────────────────────────────

@pytest.mark.parametrize("snap", ["endQ1", "endQ2"])
def test_meta_blend_returns_unit_interval(snap):
    p = _predict_meta_blend(_make_feats(snap), snap)
    assert p is not None, f"meta_blend({snap}) returned None"
    assert 0.0 <= p <= 1.0, f"meta_blend({snap}) = {p}, expected [0,1]"


def test_meta_blend_skipped_for_endq3():
    # endQ3 is intentionally excluded from _META_BLEND_SNAPSHOTS because the
    # iter71 weights assign 0.388 to v4_fouls, which is not in the live path.
    # Falling back to sigmoid_margin alone would regress vs v6_hp standalone.
    p = _predict_meta_blend(_make_feats("endQ3"), "endQ3")
    assert p is None


# ── routing via predict_home_win_prob ─────────────────────────────────────────

def test_routing_endq1_uses_meta_blend():
    p = predict_home_win_prob(_make_feats("endQ1"), "endQ1")
    assert p is not None and 0.0 <= p <= 1.0
    info = active_stack("endQ1")
    assert info["layer"] == "meta_blend_iter71", \
        f"expected meta_blend_iter71, got {info['layer']}"
    assert info["meta_blend_loaded"] is True
    assert info["v6_hp_loaded"] is True


def test_routing_endq2_uses_meta_blend_with_v7_bag5():
    p = predict_home_win_prob(_make_feats("endQ2"), "endQ2")
    assert p is not None and 0.0 <= p <= 1.0
    info = active_stack("endQ2")
    assert info["layer"] == "meta_blend_iter71"
    assert info["v6_hp_loaded"] is True
    # v7_bag5 should be available for endQ2 specifically.
    bag = _load_v7_bag5_endq2()
    assert info["v7_bag5_loaded"] is bool(bag)


def test_routing_endq3_uses_v6_hp_standalone():
    p = predict_home_win_prob(_make_feats("endQ3"), "endQ3")
    assert p is not None and 0.0 <= p <= 1.0
    info = active_stack("endQ3")
    assert info["layer"] == "v6_hp_iter68", \
        f"expected v6_hp_iter68, got {info['layer']}"
    # endQ3 must NOT route through meta_blend even though the JSON exists.
    assert info["meta_blend_loaded"] is False


# ── monotonicity sanity check under new routing ───────────────────────────────

@pytest.mark.parametrize("snap", SNAPSHOTS)
def test_monotonicity_under_new_routing(snap):
    """Larger home lead → higher home WP (active stack, not just v1)."""
    probs = []
    for margin in (-15.0, -5.0, 0.0, 5.0, 15.0):
        feats = _make_feats(snap, score_margin=margin)
        feats["last_q_margin"] = margin / 3.0
        p = predict_home_win_prob(feats, snap)
        assert p is not None
        probs.append(p)
    # +15 must dominate -15. Looser bound for endQ1 (early game), tighter for endQ3.
    floor = {"endQ1": 0.20, "endQ2": 0.30, "endQ3": 0.40}[snap]
    assert probs[-1] > probs[0] + floor, \
        f"{snap} not directionally responsive to margin: {probs}"
