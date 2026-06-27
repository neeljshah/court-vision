"""Per-file tests for the Milestone-8 multi-score SHIP/REJECT gate.

Run ONLY this file (a bare `pytest tests/` freezes the box):
    python -m pytest tests/improve/test_proper_score_gate.py -q

The KEYSTONE test is `test_crps_only_better_is_rejected`: a candidate that wins
on one proper score but regresses on another must be REJECTED, with the
dissenting score named. That is the honesty invariant the whole ratchet rests on.
"""
from __future__ import annotations

import numpy as np

from improve.proper_score_gate import score_gate, _z_for, _PINBALL_QUANTILES


# ---------------------------------------------------------------------------
# kind="prob"
# ---------------------------------------------------------------------------


def test_all_scores_better_ships():
    # outcomes; candidate tracks them sharply, base is a flat hedge.
    y = [1, 0, 1, 0, 1, 0, 1, 0]
    base = [0.5] * 8
    cand = [0.9, 0.1, 0.85, 0.15, 0.92, 0.08, 0.88, 0.12]
    out = score_gate(base, cand, y, kind="prob")
    assert out["ship"] is True
    # candidate improved (negative delta) on BOTH proper scores.
    assert out["deltas"]["brier"] < 0
    assert out["deltas"]["logloss"] < 0
    assert out["scores"]["brier_cand"] < out["scores"]["brier_base"]
    assert out["scores"]["logloss_cand"] < out["scores"]["logloss_base"]


def test_all_scores_worse_rejected():
    y = [1, 0, 1, 0, 1, 0]
    base = [0.9, 0.1, 0.8, 0.2, 0.85, 0.15]   # sharp+correct
    cand = [0.5] * 6                            # collapsed to base rate
    out = score_gate(base, cand, y, kind="prob")
    assert out["ship"] is False
    assert any("brier" in r for r in out["reasons"])


def test_one_score_better_other_worse_is_rejected():
    """KEYSTONE: a candidate that wins one proper score but regresses ANOTHER
    must be REJECTED, with the dissenting score named.

    This mirrors the milestone's "CRPS-only-better-but-Brier-worse -> REJECT"
    rule via the directly-constructible Brier-vs-log-loss disagreement: the
    candidate is marginally sharper in the bulk (Brier improves) but makes ONE
    catastrophic confident-wrong call (log-loss, which is unbounded for
    confident-wrong, regresses). The two proper scores DISAGREE, so the gate
    must NOT ship -- a one-sided "improvement" that hides a regression.
    """
    n = 200
    y = np.zeros(n)
    y[:100] = 1.0
    base = np.where(y == 1, 0.60, 0.40)
    cand = np.where(y == 1, 0.62, 0.38)   # marginally sharper -> Brier better
    cand[0] = 1e-6                          # y[0]=1 predicted ~0: confident-wrong

    out = score_gate(base, cand, y, kind="prob")
    # Confirm the scores genuinely disagree (one better, one worse) ...
    assert out["deltas"]["brier"] < 0, "candidate should improve Brier"
    assert out["deltas"]["logloss"] > 0, "candidate should regress log-loss"
    # ... therefore the gate must REJECT and name the regressing score.
    assert out["ship"] is False
    assert any("logloss" in r for r in out["reasons"])


def test_interval_all_better_ships():
    rng = np.random.default_rng(1)
    n = 400
    y = rng.normal(0.0, 1.0, n)
    base = (np.full(n, 0.5), np.full(n, 1.6))   # biased + wide
    cand = (np.zeros(n), np.full(n, 1.05))      # centered + well-scaled
    out = score_gate(base, cand, y, kind="interval")
    assert out["ship"] is True
    assert out["deltas"]["crps"] < 0
    assert out["deltas"]["pinball"] < 0


def test_identical_preds_ship_within_eps():
    # An identical candidate has zero regression -> ships (no proper score worse).
    y = [1, 0, 1, 1, 0]
    p = [0.7, 0.2, 0.6, 0.8, 0.3]
    out = score_gate(p, list(p), y, kind="prob")
    assert out["ship"] is True
    assert abs(out["deltas"]["brier"]) <= 1e-9
    assert abs(out["deltas"]["logloss"]) <= 1e-9


# ---------------------------------------------------------------------------
# degenerate / purity contract -> no-ship, never raises
# ---------------------------------------------------------------------------


def test_empty_input_no_ship():
    out = score_gate([], [], [], kind="prob")
    assert out["ship"] is False
    assert out["reasons"]


def test_length_mismatch_no_ship():
    out = score_gate([0.5, 0.5], [0.5], [1, 0], kind="prob")
    assert out["ship"] is False
    assert any("length" in r for r in out["reasons"])


def test_nan_input_no_ship():
    out = score_gate([0.5, float("nan")], [0.5, 0.5], [1, 0], kind="prob")
    assert out["ship"] is False
    assert any("non-finite" in r or "degenerate" in r for r in out["reasons"])


def test_unknown_kind_no_ship():
    out = score_gate([0.5], [0.5], [1], kind="bogus")
    assert out["ship"] is False
    assert any("unknown kind" in r for r in out["reasons"])


def test_nonpositive_sigma_no_ship():
    y = [0.0, 1.0, -1.0]
    out = score_gate((np.zeros(3), np.zeros(3)), (np.zeros(3), np.ones(3)), y, kind="interval")
    assert out["ship"] is False
    assert any("sigma" in r for r in out["reasons"])


def test_malformed_interval_no_ship():
    # not a (mu, sigma) pair -> rejected, not raised.
    out = score_gate([0.1, 0.2, 0.3], ([0.0], [1.0]), [0.0], kind="interval")
    assert out["ship"] is False
    assert out["reasons"]


# ---------------------------------------------------------------------------
# helper sanity
# ---------------------------------------------------------------------------


def test_z_for_matches_known_normal_quantiles():
    # cross-check the scipy-free inverse-CDF against textbook values.
    expected = {0.1: -1.281552, 0.25: -0.67449, 0.5: 0.0, 0.75: 0.67449, 0.9: 1.281552}
    z = _z_for(_PINBALL_QUANTILES)
    for q, zq in zip(_PINBALL_QUANTILES, z):
        assert abs(zq - expected[q]) < 1e-4


def test_never_raises_on_garbage():
    for bad in (None, "x", object(), [[1, 2], [3, 4]]):
        out = score_gate(bad, bad, [1, 0], kind="prob")
        assert out["ship"] is False
