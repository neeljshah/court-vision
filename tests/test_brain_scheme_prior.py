"""P7.1 — unit tests for src/sim/scheme_prior.py (the LLM scheme-prior applicator).

Proves the bounded-prior discipline WITHOUT touching the sim: clamp enforcement, confidence
shrink, leak rejection in betting mode, validation contract, and apply([]) no-op / determinism.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sim.scheme_prior import (  # noqa: E402
    SchemeAdjustment, apply_scheme_priors, effective_mult, validate_adjustment,
    PARAM_SPEC, VALID_PARAMS,
)


class _FakeModel:
    """Minimal TeamModel stand-in: .tri, .rate (pid->dict), and the team attrs the layer mutates."""
    def __init__(self):
        self.tri = "NYK"
        self.rate = {
            10: {"use_per_min": 0.80, "fg_rim": 0.60, "z_3": 0.30, "tov_share": 0.12},
            20: {"use_per_min": 0.50, "fg_rim": 0.55, "z_3": 0.45, "tov_share": 0.10},
        }
        self.tov_force = 1.05
        self.ft_force = 1.00
        self.pace_mult = 1.0
        self.rim_d = 65.0
        self.perim_d = 65.0


def _adj(entity, param, mult, conf=1.0, leak_safe=True, why="test"):
    return SchemeAdjustment(entity=entity, param=param, mult=mult, confidence=conf,
                            horizon="g4", leak_safe=leak_safe, why=why)


# --------------------------------------------------------------------------- validation
def test_validate_rejects_missing_fields():
    with pytest.raises(ValueError):
        validate_adjustment({"entity": 10, "param": "fg_rim"})  # missing most fields


def test_validate_rejects_unknown_param():
    with pytest.raises(ValueError):
        validate_adjustment(dict(entity=10, param="not_a_knob", mult=1.0, confidence=1.0,
                                 horizon="g4", leak_safe=True, why="x"))


def test_validate_rejects_bad_confidence_and_empty_why():
    base = dict(entity=10, param="fg_rim", mult=1.0, horizon="g4", leak_safe=True, why="x")
    with pytest.raises(ValueError):
        validate_adjustment({**base, "confidence": 1.5})
    with pytest.raises(ValueError):
        validate_adjustment({**base, "confidence": 1.0, "why": "   "})


def test_validate_rejects_implausible_raw_mult():
    with pytest.raises(ValueError):
        validate_adjustment(dict(entity=10, param="fg_rim", mult=3.0, confidence=1.0,
                                 horizon="g4", leak_safe=True, why="x"))


def test_every_param_has_a_clamp_band():
    for p in VALID_PARAMS:
        assert "lo" in PARAM_SPEC[p] and "hi" in PARAM_SPEC[p]
        assert PARAM_SPEC[p]["lo"] < 1.0 < PARAM_SPEC[p]["hi"]


# --------------------------------------------------------------------------- confidence shrink
def test_confidence_shrink_halves_effect():
    # mult 1.20 at confidence 0.5 -> eff = 1 + 0.5*(0.20) = 1.10
    a = _adj(10, "use_per_min", 1.20, conf=0.5)
    assert abs(effective_mult(a) - 1.10) < 1e-9


def test_confidence_zero_is_no_effect():
    a = _adj(10, "use_per_min", 1.50, conf=0.0)
    assert abs(effective_mult(a) - 1.0) < 1e-9


# --------------------------------------------------------------------------- clamp enforcement
def test_clamp_caps_a_confident_extreme_call():
    # use_per_min band hi=1.18; a confident 1.50 must clamp to 1.18, not dominate.
    a = _adj(10, "use_per_min", 1.50, conf=1.0)
    assert abs(effective_mult(a) - 1.18) < 1e-9


def test_clamp_floor():
    a = _adj(10, "fg_rim", 0.50, conf=1.0)  # fg_rim band lo=0.92
    assert abs(effective_mult(a) - 0.92) < 1e-9


def test_apply_records_clamp_event():
    m = _FakeModel()
    rep = apply_scheme_priors(m, [_adj(10, "use_per_min", 1.50, conf=1.0)])
    assert len(rep["clamped"]) == 1 and len(rep["applied"]) == 1
    assert abs(m.rate[10]["use_per_min"] - 0.80 * 1.18) < 1e-9


# --------------------------------------------------------------------------- leak rejection
def test_betting_mode_rejects_leak_unsafe():
    m = _FakeModel()
    before = m.rate[10]["fg_rim"]
    rep = apply_scheme_priors(m, [_adj(10, "fg_rim", 0.95, leak_safe=False)], betting_mode=True)
    assert m.rate[10]["fg_rim"] == before  # untouched
    assert rep["rejected"] and rep["rejected"][0]["reason"] == "leak_unsafe_in_betting"


def test_research_mode_applies_leak_unsafe():
    m = _FakeModel()
    rep = apply_scheme_priors(m, [_adj(10, "fg_rim", 0.95, leak_safe=False)], betting_mode=False)
    assert rep["applied"] and m.rate[10]["fg_rim"] < 0.60


# --------------------------------------------------------------------------- application targets
def test_player_knob_multiplies_rate():
    m = _FakeModel()
    apply_scheme_priors(m, [_adj(10, "fg_rim", 1.05, conf=1.0)])
    assert abs(m.rate[10]["fg_rim"] - 0.60 * 1.05) < 1e-9
    assert m.rate[20]["fg_rim"] == 0.55  # only the targeted pid moved


def test_team_knob_multiplies_attr():
    m = _FakeModel()
    apply_scheme_priors(m, [_adj("TEAM", "tov_force", 1.10, conf=1.0)])
    assert abs(m.tov_force - 1.05 * 1.10) < 1e-9


def test_unknown_pid_and_absent_knob_rejected():
    m = _FakeModel()
    rep = apply_scheme_priors(m, [_adj(999, "fg_rim", 1.05), _adj(10, "oreb_per_min", 1.05)])
    reasons = {r["reason"] for r in rep["rejected"]}
    assert "pid_not_in_rotation" in reasons      # pid 999 absent
    assert "knob_absent_on_player" in reasons     # pid 10 has no oreb_per_min key


# --------------------------------------------------------------------------- idempotence / no-op
def test_empty_list_is_noop():
    m = _FakeModel()
    snap = {pid: dict(r) for pid, r in m.rate.items()}
    rep = apply_scheme_priors(m, [])
    assert rep == {"applied": [], "rejected": [], "clamped": []}
    assert {pid: dict(r) for pid, r in m.rate.items()} == snap


def test_same_adjustments_deterministic_across_fresh_models():
    adjs = [_adj(10, "fg_rim", 1.05, conf=0.8), _adj("TEAM", "tov_force", 1.08)]
    m1, m2 = _FakeModel(), _FakeModel()
    apply_scheme_priors(m1, adjs)
    apply_scheme_priors(m2, adjs)
    assert m1.rate[10]["fg_rim"] == m2.rate[10]["fg_rim"]
    assert m1.tov_force == m2.tov_force
