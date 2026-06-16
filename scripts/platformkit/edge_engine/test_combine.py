"""Per-file test for edge_engine.combine. Run ONLY this file (full suite freezes).

  cd /c/Users/neelj/nba-ai-system && \
  C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_combine.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import pytest  # noqa: E402

from scripts.platformkit.edge_engine.combine import (  # noqa: E402
    DEFAULT_GATE_THRESHOLD, KNOB_BANDS, Combined, GatedSignal, combine,
    combine_all, validate_signal,
)

_MOVE = "2026-01-15T18:00:00"


def _sig(**kw) -> GatedSignal:
    base = dict(
        signal="charter_arrival_disruption", knob="minutes_load", lean=-1,
        weight=0.6, confidence=0.8, availability_ts="2026-01-15T11:00:00",
        subject_id="1610612743", fact_text="charter delayed; 4am arrival",
        source="https://x.com/beat/status/1",
    )
    base.update(kw)
    return GatedSignal(**base)


# --- validation / honesty rails ------------------------------------------------

def test_validate_accepts_clean_row():
    validate_signal(_sig().as_dict())  # no raise


def test_validate_rejects_unknown_knob():
    with pytest.raises(AssertionError):
        validate_signal(_sig(knob="not_a_knob").as_dict())


def test_validate_rejects_bad_lean():
    with pytest.raises(AssertionError):
        validate_signal(_sig(lean=2).as_dict())


def test_validate_rejects_out_of_range_weight():
    with pytest.raises(AssertionError):
        validate_signal(_sig(weight=1.5).as_dict())


def test_validate_forbids_outcome_number():
    d = _sig().as_dict()
    d["win_prob"] = 0.61  # an outcome number must never ride on a signal row
    with pytest.raises(AssertionError):
        validate_signal(d)


# --- firing / no-op default ----------------------------------------------------

def test_no_signals_is_noop():
    c = combine([], "minutes_load", "1610612743", _MOVE)
    assert c.fired is False and c.multiplier == 1.0 and c.n_signals == 0


def test_weak_signal_does_not_fire():
    # weight*conf*lean = 0.1*0.1*-1 = -0.01, below 0.02 threshold -> no-op
    weak = _sig(weight=0.1, confidence=0.1)
    c = combine([weak], "minutes_load", "1610612743", _MOVE)
    assert c.fired is False and c.multiplier == 1.0
    assert abs(c.combined_lean) < DEFAULT_GATE_THRESHOLD


def test_strong_signal_fires_and_moves_knob_down():
    c = combine([_sig()], "minutes_load", "1610612743", _MOVE)
    assert c.fired is True
    # lean -1 * 0.6 * 0.8 = -0.48 -> raw 0.52 -> clamped to band lo 0.90
    assert c.multiplier == KNOB_BANDS["minutes_load"][0]
    assert c.clamped is True


def test_multiplier_always_inside_band():
    for knob, (lo, hi) in KNOB_BANDS.items():
        up = _sig(knob=knob, lean=1, weight=1.0, confidence=1.0)
        dn = _sig(knob=knob, lean=-1, weight=1.0, confidence=1.0)
        cu = combine([up], knob, "1610612743", _MOVE)
        cd = combine([dn], knob, "1610612743", _MOVE)
        assert lo <= cu.multiplier <= hi
        assert lo <= cd.multiplier <= hi


def test_opposing_facts_net_to_noop():
    # two equal-and-opposite signals cancel -> combined lean ~0 -> no-op
    a = _sig(signal="a", lean=1, weight=0.6, confidence=0.8)
    b = _sig(signal="b", lean=-1, weight=0.6, confidence=0.8)
    c = combine([a, b], "minutes_load", "1610612743", _MOVE)
    assert c.fired is False and c.multiplier == 1.0
    assert abs(c.combined_lean) < 1e-9


def test_small_combined_lean_stays_unclamped():
    # weight*conf*lean = 0.3*0.1*1 = 0.03 -> fires, raw 1.03 inside pace band -> not clamped
    s = _sig(knob="pace", lean=1, weight=0.3, confidence=0.1)
    c = combine([s], "pace", "1610612743", _MOVE)
    assert c.fired is True and c.clamped is False
    assert abs(c.multiplier - 1.03) < 1e-9


# --- leak guard ----------------------------------------------------------------

def test_leak_guard_refuses_whole_fusion_on_hindsight():
    good = _sig(signal="good")
    bad = _sig(signal="bad", availability_ts="2026-01-15T19:00:00")  # after the move
    with pytest.raises(AssertionError) as e:
        combine([good, bad], "minutes_load", "1610612743", _MOVE)
    assert "LEAK" in str(e.value)


def test_leak_guard_passes_when_all_before_move():
    c = combine([_sig()], "minutes_load", "1610612743", _MOVE)
    assert c.fired is True  # no raise; known before the move


# --- grouping ------------------------------------------------------------------

def test_combine_all_groups_by_knob_and_subject():
    sigs = [
        _sig(knob="pace", subject_id="A", lean=1, weight=0.6, confidence=0.8),
        _sig(knob="minutes_load", subject_id="A"),
        _sig(knob="minutes_load", subject_id="B"),
    ]
    out = combine_all(sigs, _MOVE)
    assert len(out) == 3
    keys = {(c.knob, c.subject_id) for c in out}
    assert keys == {("pace", "A"), ("minutes_load", "A"), ("minutes_load", "B")}
    for c in out:
        assert isinstance(c, Combined)
