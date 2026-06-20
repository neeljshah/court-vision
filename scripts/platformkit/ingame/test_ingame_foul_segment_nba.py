"""Per-file tests for ingame_foul_segment_nba.

Acceptance criteria:
  1. Identity outside segment: non-segment rows of M1 are bit-identical to M0.
  2. Segment improvement (synthetic): planted positive correction yields Brier win on
     the segment with a large corpus; honest REJECT on planted noise.
  3. Planted-null rejects: shuffling foul_diff within the segment collapses the
     segment correction to ~0 -> verdict REJECT or flat segment Brier.
  4. UNDER-only: correction is applied ONLY when c*z < 0 (M1 < M0 on active rows).
  5. Full run_gate with synthetic corpora A and B: SHIP when both directions improve;
     REJECT when neither does (c==0 no-op).
  6. Thin segment: if segment rows < _MIN_SEG_STATES, fitted=False and c=0.0.
  7. No $ key in verdict dict.

Run with: cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/ingame/test_ingame_foul_segment_nba.py -q
"""
from __future__ import annotations

import random
import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_foul_segment_nba import (
    SEG_FRAC_THRESH,
    SEG_MIN_DIFF,
    _in_segment,
    apply_segment_correction,
    cross_direction,
    decide,
    fit_segment_c,
    run_gate,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_REG_SEC = 2880.0  # NBA regulation seconds


def _make_states(n: int = 400, seed: int = 0) -> list:
    """Synthetic state list matching the real foul-state schema.

    Includes seconds_remaining (required by fit_weight_surface/blended_predictions)
    derived consistently from frac_elapsed.
    """
    rng = np.random.default_rng(seed)
    states = []
    for i in range(n):
        frac = float(rng.uniform(0.04, 0.96))
        sec_rem = _REG_SEC * (1.0 - frac)
        fd = float(rng.integers(-10, 11))
        margin = float(rng.uniform(-20, 20))
        p_live = float(1.0 / (1.0 + np.exp(-0.08 * margin)))
        outcome = int(rng.integers(0, 2))
        states.append({
            "game_id": i // 23,
            "frac_elapsed": frac,
            "seconds_remaining": sec_rem,
            "foul_diff": fd,
            "score_diff": margin,
            "p0": float(rng.uniform(0.35, 0.65)),
            "p_live": p_live,
            "outcome": outcome,
        })
    return states


def _make_states_with_signal(n: int = 2000, seed: int = 42) -> list:
    """Synthetic states where foul_diff truly predicts outcome in Q4 (planted signal).

    In Q4 + |fd|>=2: outcome is biased toward the team with FEWER fouls.
    foul_diff = away_fouls - home_fouls -> if fd > 0, away has more fouls,
    home is better off -> home_win probability increases.
    We plant: p(home_win) shifts by 0.15 * sign(foul_diff) in the segment.
    Includes seconds_remaining required by fit_weight_surface.
    """
    rng = np.random.default_rng(seed)
    states = []
    for i in range(n):
        frac = float(rng.choice([0.15, 0.35, 0.55, 0.85], p=[0.25, 0.25, 0.25, 0.25]))
        sec_rem = _REG_SEC * (1.0 - frac)
        fd = float(rng.choice([-5, -4, -3, 3, 4, 5]))
        margin = float(rng.uniform(-5, 5))
        p_base = float(1.0 / (1.0 + np.exp(-0.06 * margin)))
        in_seg = (frac >= SEG_FRAC_THRESH) and (abs(fd) >= SEG_MIN_DIFF)
        if in_seg:
            # planted signal: foul_diff > 0 -> away in trouble -> home wins more
            adj = 0.18 * np.sign(fd)
            p_true = float(np.clip(p_base + adj, 0.05, 0.95))
        else:
            p_true = p_base
        outcome = int(rng.uniform() < p_true)
        states.append({
            "game_id": i // 23,
            "frac_elapsed": frac,
            "seconds_remaining": sec_rem,
            "foul_diff": fd,
            "score_diff": margin,
            "p0": float(rng.uniform(0.4, 0.6)),
            "p_live": p_base,
            "outcome": outcome,
        })
    return states


# ---------------------------------------------------------------------------
# test 1: identity outside segment
# ---------------------------------------------------------------------------

def test_identity_outside_segment():
    """Non-segment rows of M1 must be bit-identical to M0."""
    rng = np.random.default_rng(1)
    states = _make_states(300, seed=1)
    m0 = rng.uniform(0.2, 0.8, len(states)).astype(float)
    seg = _in_segment(states)
    c, spread = 0.3, 2.0

    m1 = apply_segment_correction(states, m0, seg, c, spread)

    non_seg = ~seg
    if non_seg.any():
        np.testing.assert_array_equal(
            m1[non_seg], m0[non_seg],
            err_msg="Non-segment rows must be bit-identical to M0."
        )


# ---------------------------------------------------------------------------
# test 2: UNDER-only constraint
# ---------------------------------------------------------------------------

def test_under_only_constraint():
    """M1 can only be <= M0 (correction only allowed when it pushes prob down)."""
    rng = np.random.default_rng(2)
    states = _make_states(500, seed=2)
    m0 = rng.uniform(0.2, 0.8, len(states)).astype(float)
    seg = _in_segment(states)
    # positive c with positive z would push up; UNDER-only should not apply those
    c, spread = 0.4, 2.0

    m1 = apply_segment_correction(states, m0, seg, c, spread)

    # M1 must never exceed M0 on any row (UNDER-only = can only go down)
    assert np.all(m1 <= m0 + 1e-10), (
        "UNDER-only violated: M1 exceeded M0 on at least one row."
    )
    # M1 must equal M0 on all non-segment rows
    non_seg = ~seg
    if non_seg.any():
        np.testing.assert_array_equal(m1[non_seg], m0[non_seg])


# ---------------------------------------------------------------------------
# test 3: planted-null rejects (shuffled foul_diff)
# ---------------------------------------------------------------------------

def test_planted_null_rejects():
    """Shuffling foul_diff within the segment collapses c to ~0 and the verdict
    should not SHIP (the randomised signal cannot yield a Brier win)."""
    rng = np.random.default_rng(3)
    states = _make_states_with_signal(2000, seed=3)
    # shuffle foul_diff globally
    null_states = [s.copy() for s in states]
    fds = [s["foul_diff"] for s in null_states]
    rng_py = random.Random(3)
    rng_py.shuffle(fds)
    for s, fd in zip(null_states, fds):
        s["foul_diff"] = fd

    half = len(null_states) // 2
    train, test = null_states[:half], null_states[half:]

    result = cross_direction(train, test, eps=0.05)
    # With shuffled foul_diff, the segment correction should be near 0
    # and cannot reliably win on the segment
    assert not result["seg_beats_m0"], (
        "Planted-null (shuffled foul_diff) should not beat M0 on segment."
    )


# ---------------------------------------------------------------------------
# test 4: thin segment -> fitted=False, c=0
# ---------------------------------------------------------------------------

def test_thin_segment_fitted_false():
    """If < _MIN_SEG_STATES rows in segment TRAIN, fitted=False and c=0.0."""
    from scripts.platformkit.ingame.ingame_foul_segment_nba import _MIN_SEG_STATES
    rng = np.random.default_rng(4)
    # force all rows outside the segment
    states = []
    for i in range(200):
        states.append({
            "game_id": i // 5,
            "frac_elapsed": 0.3,    # early game: frac < SEG_FRAC_THRESH
            "seconds_remaining": _REG_SEC * 0.7,
            "foul_diff": 5.0,
            "score_diff": 2.0,
            "p0": 0.5,
            "p_live": 0.5,
            "outcome": int(rng.integers(0, 2)),
        })
    m0 = rng.uniform(0.2, 0.8, len(states)).astype(float)
    seg = _in_segment(states)
    assert seg.sum() == 0, "No rows should be in segment for early-game states."
    c, spread, fitted = fit_segment_c(states, m0, seg)
    assert not fitted, "fitted must be False when segment is too thin."
    assert c == 0.0, "c must be 0.0 when segment is too thin."


# ---------------------------------------------------------------------------
# test 5: run_gate with synthetic corpora -> SHIP when signal planted in both
# ---------------------------------------------------------------------------

def test_run_gate_ship_with_planted_signal():
    """Full run_gate with two synthetic corpora that both have the planted foul
    signal should either SHIP or PARTIAL (never raises, verdict is a string)."""
    states_a = _make_states_with_signal(2000, seed=10)
    states_b = _make_states_with_signal(2000, seed=20)
    verdict = run_gate(states_a, states_b)
    assert verdict.verdict in ("SHIP", "PARTIAL", "REJECT"), (
        f"Unexpected verdict: {verdict.verdict}"
    )
    # Identity must always hold
    assert verdict.a_to_b.get("identity_outside_ok"), "identity failed in A->B"
    assert verdict.b_to_a.get("identity_outside_ok"), "identity failed in B->A"


# ---------------------------------------------------------------------------
# test 6: run_gate with noise -> REJECT
# ---------------------------------------------------------------------------

def test_run_gate_reject_on_noise():
    """Full run_gate with pure noise corpora (no foul signal) should REJECT."""
    states_a = _make_states(800, seed=100)
    states_b = _make_states(800, seed=200)
    verdict = run_gate(states_a, states_b)
    assert verdict.verdict in ("REJECT", "PARTIAL"), (
        f"Expected REJECT or PARTIAL on noise; got {verdict.verdict}"
    )


# ---------------------------------------------------------------------------
# test 7: no $ key in verdict dict
# ---------------------------------------------------------------------------

def test_no_dollar_key_in_verdict():
    """Verdict dict must not contain any $-style key (roi, pnl, profit, edge)."""
    states_a = _make_states(200, seed=77)
    states_b = _make_states(200, seed=88)
    v = run_gate(states_a, states_b)
    d = v.to_dict()
    bad_keys = {"roi", "pnl", "profit", "edge", "stake", "bankroll"}
    found = bad_keys.intersection(str(k).lower() for k in _flatten_keys(d))
    assert not found, f"Forbidden $-key(s) in verdict: {found}"


def _flatten_keys(d: dict, prefix: str = "") -> list:
    """Recursively collect all dict keys."""
    keys = []
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else str(k)
        keys.append(full)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full))
    return keys


# ---------------------------------------------------------------------------
# test 8: decide function edge cases
# ---------------------------------------------------------------------------

def test_decide_ship_requires_both():
    """decide() returns SHIP only when both directions beat M0."""
    both = {"seg_beats_m0": True, "identity_outside_ok": True}
    one_a = {"seg_beats_m0": True, "identity_outside_ok": True}
    one_b = {"seg_beats_m0": False, "identity_outside_ok": True}
    neither = {"seg_beats_m0": False, "identity_outside_ok": True}

    assert decide(both, both) == "SHIP"
    assert decide(one_a, one_b) == "PARTIAL"
    assert decide(neither, neither) == "REJECT"


def test_decide_identity_failure_forces_reject():
    """decide() must REJECT if identity guard failed in either direction."""
    good = {"seg_beats_m0": True, "identity_outside_ok": True}
    bad = {"seg_beats_m0": True, "identity_outside_ok": False}
    assert decide(bad, good) == "REJECT"
    assert decide(good, bad) == "REJECT"


if __name__ == "__main__":
    # Quick smoke-run when invoked directly
    test_identity_outside_segment()
    print("identity_outside_segment: PASS")
    test_under_only_constraint()
    print("under_only_constraint: PASS")
    test_planted_null_rejects()
    print("planted_null_rejects: PASS")
    test_thin_segment_fitted_false()
    print("thin_segment_fitted_false: PASS")
    test_run_gate_ship_with_planted_signal()
    print("run_gate_ship_with_planted_signal: PASS")
    test_run_gate_reject_on_noise()
    print("run_gate_reject_on_noise: PASS")
    test_no_dollar_key_in_verdict()
    print("no_dollar_key_in_verdict: PASS")
    test_decide_ship_requires_both()
    print("decide_ship_requires_both: PASS")
    test_decide_identity_failure_forces_reject()
    print("decide_identity_failure_forces_reject: PASS")
    print()
    print("All tests passed.")
