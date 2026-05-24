"""tests/test_guard_fg3m_scale.py — Cycle 97c (loop 5) T1.

Validates the guard-FG3M position-conditioned scale factory and (when the
probe ships) its production wire-in into predict_pergame. Tests exercise
the factory directly so they don't require on-disk model artifacts —
pytest-light, runs in <1s on a fresh checkout.

Required tests (per cycle 97c spec):
  1. factor=1.0 → zero MAE delta (the NO-OP reproduction guard).
  2. factor=1.15 → guard FG3M scales.
  3. non-guard position → unchanged.
  4. non-FG3M stat → unchanged.
  5. position=None → unchanged.
  6. WF fold sign matches single-split sign.

End-to-end coverage of the predict_pergame wire-in (when 97c ships) is
provided by the production_mae anchor test running on real models.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from scripts.probe_guard_fg3m_scale import (  # noqa: E402
    _GUARD_POSITIONS, make_guard_fg3m_scale,
)


# ── 1. NO-OP reproduction (factor=1.0) ───────────────────────────────────────

def test_factor_1p0_yields_zero_delta_across_all_inputs():
    """factor=1.0 must return predictions UNCHANGED for every (stat, position)
    combination — the NO-OP reproduction guard that prevents wrapper-state
    pollution from leaking into the shipped path."""
    fn = make_guard_fg3m_scale(factor=1.0)
    pred = np.array([1.5, 2.0, 0.8, 3.1, 0.0], dtype=float)
    rows = [
        {"position": "Guard"},
        {"position": "Guard-Forward"},
        {"position": "Forward-Guard"},
        {"position": "Center"},
        {"position": None},
    ]
    for stat in ("fg3m", "pts", "reb", "ast", "stl", "blk", "tov"):
        out = fn(pred, rows, stat)
        assert np.allclose(out, pred, atol=0.0, rtol=0.0), \
            f"factor=1.0 must yield exact zero delta for stat={stat!r}"


# ── 2. factor=1.15 actually scales guard FG3M ────────────────────────────────

def test_factor_1p15_scales_guard_fg3m():
    """factor=1.15 multiplies FG3M prediction for any guard-flavoured position."""
    fn = make_guard_fg3m_scale(factor=1.15)
    pred = np.array([1.0, 2.0, 3.0], dtype=float)
    rows = [
        {"position": "Guard"},
        {"position": "Guard-Forward"},
        {"position": "Forward-Guard"},
    ]
    out = fn(pred, rows, "fg3m")
    assert out[0] == pytest.approx(1.0 * 1.15)
    assert out[1] == pytest.approx(2.0 * 1.15)
    assert out[2] == pytest.approx(3.0 * 1.15)


# ── 3. non-guard position is unchanged ───────────────────────────────────────

def test_non_guard_position_unchanged():
    """Centers / Forwards / hybrid-Center positions must NOT be scaled."""
    fn = make_guard_fg3m_scale(factor=1.15)
    pred = np.array([0.5, 1.2, 2.0, 0.9], dtype=float)
    rows = [
        {"position": "Center"},
        {"position": "Forward"},
        {"position": "Center-Forward"},
        {"position": "Forward-Center"},
    ]
    out = fn(pred, rows, "fg3m")
    assert np.allclose(out, pred, atol=0.0, rtol=0.0)
    # Sanity: these positions are intentionally NOT in the guard whitelist.
    for r in rows:
        assert r["position"] not in _GUARD_POSITIONS


# ── 4. non-FG3M stat is unchanged ────────────────────────────────────────────

def test_non_fg3m_stat_unchanged():
    """Even for guard rows, only stat='fg3m' is scaled. PTS/REB/AST/STL/BLK/TOV
    must pass through untouched so the cycle 97b haircut domain (PTS/REB/AST)
    is never double-dipped."""
    fn = make_guard_fg3m_scale(factor=1.15)
    pred = np.array([20.0, 5.0, 8.0], dtype=float)
    rows = [
        {"position": "Guard"},
        {"position": "Guard-Forward"},
        {"position": "Forward-Guard"},
    ]
    for stat in ("pts", "reb", "ast", "stl", "blk", "tov"):
        out = fn(pred, rows, stat)
        assert np.allclose(out, pred, atol=0.0, rtol=0.0), \
            f"stat={stat!r} must pass through untouched on guard rows"


# ── 5. position=None is unchanged ────────────────────────────────────────────

def test_position_none_unchanged():
    """A row with missing position (uncached pid) defaults to no-scale —
    the fallback semantics for fresh checkouts where player_positions.parquet
    is absent."""
    fn = make_guard_fg3m_scale(factor=1.15)
    pred = np.array([1.0, 2.0], dtype=float)
    rows = [
        {"position": None},
        {},  # no 'position' key at all → also treated as None
    ]
    out = fn(pred, rows, "fg3m")
    assert np.allclose(out, pred, atol=0.0, rtol=0.0)


# ── 6. WF fold sign matches single-split sign ────────────────────────────────

def test_wf_fold_sign_matches_single_split_sign():
    """For a synthetic dataset where the scale is unambiguously beneficial
    (predictions consistently 1.17x BELOW truth on guard rows), every WF
    fold must improve AND the single-split must improve — i.e. the sign of
    the WF fold deltas matches the sign of the single-split delta.

    This guards against the failure mode where single-split looks great but
    WF folds diverge in sign (cycle 96e called out the dual-gate discipline
    specifically to catch this)."""
    from scripts.probe_guard_fg3m_scale import walk_forward_post_adjust
    from scripts.validate_adjustment import _bulk_predict

    # Monkey-patch _bulk_predict so we don't need on-disk models.
    rng = np.random.default_rng(42)
    n = 400  # divisible by 4 for clean fold split
    # Guard rows have predictions consistently 1.17x BELOW truth → scaling UP
    # by 1.17 unambiguously reduces MAE. Non-guard rows are perfectly calibrated.
    rows = []
    truths = np.zeros(n)
    raw_preds = np.zeros(n)
    for i in range(n):
        if i % 2 == 0:
            # Guard row, model under-predicts.
            truths[i] = 1.17 * (1.0 + 0.1 * rng.standard_normal())
            raw_preds[i] = truths[i] / 1.17
            rows.append({"position": "Guard", "target_fg3m": truths[i]})
        else:
            # Non-guard row, model is well-calibrated.
            truths[i] = 1.0 + 0.1 * rng.standard_normal()
            raw_preds[i] = truths[i]
            rows.append({"position": "Center", "target_fg3m": truths[i]})

    import scripts.probe_guard_fg3m_scale as probe_mod

    # Monkey-patch _bulk_predict in the probe module to return slices of raw_preds.
    # The walk_forward helper calls _bulk_predict(stat, sub_X) with sub_X carrying
    # row ordering — we recover the slice indices from the rows themselves by
    # using their target as a stable key (truths array indices align).
    def _fake_bulk_predict(stat, sub_X):
        # sub_X is a positional slice — we replicate that slice on raw_preds
        # by looking up how many rows precede the first row in sub_rows. But
        # walk_forward_post_adjust passes sub_X derived from holdout[lo:hi],
        # so the slice length tells us the fold range. We just track via a
        # closure-mutated counter.
        return raw_preds[_fake_bulk_predict.cursor:
                         _fake_bulk_predict.cursor + len(sub_X)]
    _fake_bulk_predict.cursor = 0

    # The fold walker calls bulk_predict per fold. We need cursor to advance
    # in lock-step with the lo:hi slices. Simplest: wrap walk_forward_post_adjust
    # ourselves and feed it a stub that uses the actual lo:hi.
    orig_bulk = probe_mod._bulk_predict

    def _bulk_by_slice(stat, sub_X):
        out = raw_preds[_bulk_by_slice.cursor:_bulk_by_slice.cursor + len(sub_X)]
        _bulk_by_slice.cursor += len(sub_X)
        return out
    _bulk_by_slice.cursor = 0

    probe_mod._bulk_predict = _bulk_by_slice
    try:
        # Single-split baseline / adjusted MAE on the full synthetic holdout.
        fn = make_guard_fg3m_scale(factor=1.17)
        ss_baseline = float(np.mean(np.abs(raw_preds - truths)))
        ss_adjusted = float(np.mean(np.abs(fn(raw_preds, rows, "fg3m") - truths)))
        ss_delta = ss_adjusted - ss_baseline
        assert ss_delta < 0, ("Synthetic setup must yield single-split "
                              f"improvement; got delta={ss_delta:+.4f}")

        # WF fold deltas.
        X_dummy = np.zeros((n, 1))  # only length matters for the stub
        _bulk_by_slice.cursor = 0
        wf_deltas = probe_mod.walk_forward_post_adjust(
            fn, rows, X_dummy, n_folds=4, stat="fg3m"
        )
    finally:
        probe_mod._bulk_predict = orig_bulk

    assert len(wf_deltas) == 4
    # Every fold must move in the same direction as the single-split delta.
    for i, d in enumerate(wf_deltas):
        assert np.sign(d) == np.sign(ss_delta), (
            f"WF fold {i+1} delta {d:+.4f} sign disagrees with "
            f"single-split delta {ss_delta:+.4f} — dual-gate would catch this"
        )
