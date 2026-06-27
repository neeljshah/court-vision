"""tests.governance.test_leak_audit -- the leak guard is an ENFORCED gate.

A leak-free build (the frozen golden fixture) PASSES. An injected future-dated
feature BLOCKS. A required feature that reads 0.0 everywhere (silent-zero) BLOCKS.
select_inside=False BLOCKS, and the walk_forward leak-free harness is exercised
(select_inside asserted via the harness's own record). Run ONLY this file (a full
pytest run freezes the box):

    python -m pytest tests/governance/test_leak_audit.py -q

PROVENANCE NOTE: the leak-free PASS case uses the frozen SYNTHETIC golden fixture
(a reproducibility anchor, not a real calibration claim). The leak-BLOCK cases are
STRUCTURAL: they inject a real schema/vintage violation into that same fixture and
assert the gate refuses it. Nothing here is skipped / mocked into a false green.
"""
from __future__ import annotations

import copy

import pytest

from governance import leak_audit
from scripts.platformkit.eval_gate.golden_loader import load_golden


def _golden():
    """Load the frozen leak-free golden states (raises if the fixture is missing)."""
    return load_golden()


def _trivial_predict(train, test, select_inside):
    return 0.5


# --------------------------------------------------------------------------- #
# leak-free build PASSES                                                       #
# --------------------------------------------------------------------------- #
def test_leak_free_build_passes():
    states = _golden()
    verdict = leak_audit.audit(states)
    assert verdict["leak_free"] is True, verdict["findings"]
    assert verdict["findings"] == []
    assert verdict["n_states"] == len(states)
    assert verdict["version"] == leak_audit.AUDIT_VERSION


def test_leak_free_build_passes_with_walkforward():
    """Driving the leak-free walk_forward (vintage re-asserted) still PASSES."""
    states = _golden()
    verdict = leak_audit.audit(states, predict_fn=_trivial_predict,
                               select_inside=True)
    assert verdict["leak_free"] is True, verdict["findings"]
    assert verdict["select_inside"] is True


def test_accepts_object_exposing_states():
    states = _golden()

    class _Build:
        pass

    b = _Build()
    b.states = states
    verdict = leak_audit.audit(b)
    assert verdict["leak_free"] is True, verdict["findings"]


# --------------------------------------------------------------------------- #
# injected FUTURE-DATED feature BLOCKS                                         #
# --------------------------------------------------------------------------- #
def test_future_dated_feature_blocks():
    states = copy.deepcopy(_golden())
    # Make one feature's availability LATER than the prediction-time boundary.
    s = states[0]
    feat = next(iter(s["feature_avail"]))
    # state_ts is e.g. 2025-02-12T19:00:00 -> push availability to a future date.
    s["feature_avail"][feat] = "2999-01-01T00:00:00"

    verdict = leak_audit.audit(states)
    assert verdict["leak_free"] is False
    kinds = {f["kind"] for f in verdict["findings"]}
    # schema guard and/or per-state vintage guard must fire on the leak.
    assert kinds & {"future_dated_feature", "schema_leak_or_coverage"}, kinds


def test_future_dated_feature_blocks_even_without_schema_validation():
    """Defense in depth: the per-state vintage guard alone BLOCKS the leak."""
    states = copy.deepcopy(_golden())
    s = states[3]
    feat = next(iter(s["feature_avail"]))
    s["feature_avail"][feat] = "2999-01-01T00:00:00"

    verdict = leak_audit.audit(states, validate_schema=False)
    assert verdict["leak_free"] is False
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "future_dated_feature" in kinds, kinds
    # the finding names the offending game.
    leak = [f for f in verdict["findings"] if f["kind"] == "future_dated_feature"][0]
    assert leak.get("game_id") == s["game_id"]


# --------------------------------------------------------------------------- #
# zero-read of a required feature BLOCKS                                       #
# --------------------------------------------------------------------------- #
def test_zero_read_required_feature_blocks():
    states = copy.deepcopy(_golden())
    # Force a known feature to 0.0 at EVERY state -> silent-zero wiring bug.
    feat = next(iter(states[0]["features"]))
    for s in states:
        if feat in s["features"]:
            s["features"][feat] = 0.0

    verdict = leak_audit.audit(states, required_features=[feat])
    assert verdict["leak_free"] is False
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "zero_read" in kinds, kinds


def test_partial_zero_is_not_a_zero_read():
    """A feature that is 0.0 at some states but non-zero elsewhere is real data."""
    states = copy.deepcopy(_golden())
    feat = next(iter(states[0]["features"]))
    # Zero everywhere except the first state -> NOT a silent zero.
    for s in states:
        if feat in s["features"]:
            s["features"][feat] = 0.0
    states[0]["features"][feat] = 1.0

    verdict = leak_audit.audit(states, required_features=[feat])
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "zero_read" not in kinds, kinds


def test_missing_required_feature_blocks():
    states = _golden()
    verdict = leak_audit.audit(states, required_features=["__not_a_real_feature__"])
    assert verdict["leak_free"] is False
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "missing_required_feature" in kinds, kinds


# --------------------------------------------------------------------------- #
# select_inside is ASSERTED (full-history selection BLOCKS)                    #
# --------------------------------------------------------------------------- #
def test_select_outside_window_blocks():
    states = _golden()
    verdict = leak_audit.audit(states, select_inside=False)
    assert verdict["leak_free"] is False
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "select_outside_window" in kinds, kinds
    assert verdict["select_inside"] is False


def test_select_inside_true_does_not_flag():
    states = _golden()
    verdict = leak_audit.audit(states, select_inside=True)
    kinds = {f["kind"] for f in verdict["findings"]}
    assert "select_outside_window" not in kinds


# --------------------------------------------------------------------------- #
# malformed build -> blocking finding (never false-green)                      #
# --------------------------------------------------------------------------- #
def test_bad_build_blocks():
    verdict = leak_audit.audit(42)
    assert verdict["leak_free"] is False
    assert verdict["findings"][0]["kind"] == "bad_build"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
