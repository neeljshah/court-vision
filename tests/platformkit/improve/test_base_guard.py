"""tests.platformkit.improve.test_base_guard -- the MF2 degenerate-base guard.

The 5-gate ratchet lacked a degenerate-base check for recal-variant candidates
(SKEPTIC_REVIEW MF2). `degenerate_base_reason` is that guard. These tests pin
the three degenerate verdicts and the genuine-candidate pass-through so a future
change cannot silently let a collapse-to-base / collapse-to-close stream SHIP.

Calibration, not edge: a degenerate candidate is an honest REJECT, never a win.
"""
from __future__ import annotations

import numpy as np

from scripts.platformkit.improve.base_guard import degenerate_base_reason


# A genuine, distinct, well-spread base stream + matched outcomes shared by the
# no-op and collapse cases so each test isolates ONE degeneracy axis.
_BASE = np.array([0.10, 0.30, 0.55, 0.72, 0.88, 0.21, 0.64, 0.41], dtype=float)
_Y = np.array([0, 0, 1, 1, 1, 0, 1, 0], dtype=float)


def test_no_op_candidate_returns_no_op():
    """Candidate identical to base (within float noise) -> 'no_op'."""
    cand = _BASE + 1e-12  # identity transform, pure float jitter
    assert degenerate_base_reason(cand, _BASE, _Y) == "no_op"


def test_constant_collapse_returns_collapsed_constant():
    """Candidate collapsed onto a single value (the base rate) -> 'collapsed_constant'."""
    cand = np.full(_BASE.shape, float(_Y.mean()), dtype=float)
    assert degenerate_base_reason(cand, _BASE, _Y) == "collapsed_constant"


def test_collapse_to_close_returns_collapsed_to_close():
    """Candidate that merely copies the close reference -> 'collapsed_to_close'.

    The candidate is distinct from base and well-spread (so it is NOT no_op and
    NOT collapsed_constant), but it equals p_close everywhere -- any BSS-vs-close
    came from matching the reference, not from skill.
    """
    p_close = np.array([0.12, 0.34, 0.58, 0.70, 0.85, 0.25, 0.60, 0.45], dtype=float)
    cand = p_close.copy()
    assert degenerate_base_reason(cand, _BASE, _Y, p_close=p_close) == "collapsed_to_close"


def test_genuine_distinct_candidate_returns_none():
    """A genuine, distinct, non-collapsed candidate -> None (not degenerate)."""
    # Distinct from base, well-spread (high sharpness), and distinct from close.
    cand = np.array([0.05, 0.40, 0.62, 0.80, 0.93, 0.15, 0.70, 0.33], dtype=float)
    p_close = np.array([0.12, 0.34, 0.58, 0.70, 0.85, 0.25, 0.60, 0.45], dtype=float)
    assert degenerate_base_reason(cand, _BASE, _Y, p_close=p_close) is None
    # And None still holds when no close reference is supplied.
    assert degenerate_base_reason(cand, _BASE, _Y) is None


def test_genuine_candidate_near_close_but_not_collapsed_returns_none():
    """Close as reference but candidate is genuinely distinct from it -> None.

    Guards against an over-eager close check: being NEAR the close (but outside
    epsilon at some points) is legitimate skill, not collapse.
    """
    p_close = np.array([0.12, 0.34, 0.58, 0.70, 0.85, 0.25, 0.60, 0.45], dtype=float)
    cand = p_close + np.array([0.03, -0.04, 0.05, -0.02, 0.04, -0.05, 0.03, -0.06])
    assert degenerate_base_reason(cand, _BASE, _Y, p_close=p_close) is None


def test_malformed_input_never_raises_and_flags_reject():
    """Non-finite / mismatched input -> a 'degenerate_input...' reason, never a raise."""
    bad = np.array([0.1, np.nan, 0.5, 0.7, 0.9, 0.2, 0.6, 0.4])
    r = degenerate_base_reason(bad, _BASE, _Y)
    assert r is not None and r.startswith("degenerate_input")

    short = np.array([0.1, 0.2, 0.3])
    r2 = degenerate_base_reason(short, _BASE, _Y)
    assert r2 is not None and r2.startswith("degenerate_input")
