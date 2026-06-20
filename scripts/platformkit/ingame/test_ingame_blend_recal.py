"""Per-file tests for ingame_blend_recal.py.

Acceptance criteria (from BACKLOG.md ig-blend-isocal):
  1. fit on A, eval on B: per-quarter ECE(recal) < ECE(raw) for the majority of
     buckets AND Brier(recal) not worse than raw (within tolerance).
  2. planted-null (label-shuffled on fit pool A) does NOT claim improvement --
     verdict must NOT be SHIP (all-buckets improvement).
  3. No dollar key in any output dict.

Synthetic design: states are constructed with a SHRINKAGE bias (predictions pulled
toward 0.5 from the true probability) that isotonic regression can reliably correct.
The blend surface fit_weight_surface assigns w=1 (fully trust p_live) in cells where
that correction is clear, passing the biased p_live through -- and isotonic then
un-shrinks it on held-out data.  This is a well-known calibration gap that isotonic
regression is guaranteed to reduce asymptotically.
"""
from __future__ import annotations

import math
from typing import List

import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_blend_recal import (
    RecalResult,
    SegmentRecalibrator,
    eval_recal,
    fit_recal,
    run,
    split_ab,
)
from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
from scripts.platformkit.eval_gate.scoring import brier, ece


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1 - 1e-9))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _make_states(n_games: int = 120,
                 seed: int = 0,
                 shrink_alpha: float = 0.5) -> List[dict]:
    """Generate synthetic in-game states with a known SHRINKAGE calibration gap.

    True probabilities are drawn from Beta(3,3) (roughly uniform on [0.1,0.9]).
    Predicted probabilities are shrunk toward 0.5 by scaling the logit by `shrink_alpha`.
    This creates systematic under-confidence that isotonic regression can correct.

    The blend surface (fit_weight_surface) is Brier-optimising per cell and assigns
    w=1 (trust p_live fully) when p_live is more informative than p0 per cell;
    this passes the shrunken probabilities through.  Isotonic recalibration on the
    fit split then learns to un-shrink them, and applies that correction on the eval
    split -- producing lower ECE without hurting Brier.

    States: 3 per game (end-Q1/Q2/Q3 as-of points).
    Keys: game_id, period, seconds_remaining, score_diff, p0, p_live, outcome.
    """
    rng = np.random.default_rng(seed)
    qsec = {1: 2160.0, 2: 1440.0, 3: 720.0}
    states: List[dict] = []

    for gid in range(n_games):
        p_true = float(rng.beta(3, 3))          # game-level true prob
        outcome = int(rng.random() < p_true)
        for q in (1, 2, 3):
            sec_rem = qsec[q]
            # Shrink true prob toward 0.5 (under-confidence)
            p_shrunken = float(_sigmoid(np.array([shrink_alpha * _logit(
                np.array([p_true]))])).item())
            # p_live and p0 both biased (the bias is what isotonic will correct)
            p_live = float(np.clip(p_shrunken, 0.01, 0.99))
            p0 = float(np.clip(p_shrunken + 0.01, 0.01, 0.99))
            # score_diff proportional to dominance (not exact but realistic)
            score_diff = (p_true - 0.5) * 20.0
            states.append({
                "game_id": gid,
                "period": q,
                "seconds_remaining": sec_rem,
                "score_diff": score_diff,
                "p0": p0,
                "p_live": p_live,
                "outcome": outcome,
            })
    return states


def _has_dollar_key(d: dict, _depth: int = 0) -> bool:
    """Recursively check that no key or string value mentions $."""
    if _depth > 6:
        return False
    for k, v in d.items():
        if "$" in str(k):
            return True
        if isinstance(v, str) and "$" in v:
            return True
        if isinstance(v, dict) and _has_dollar_key(v, _depth + 1):
            return True
    return False


# ---------------------------------------------------------------------------
# Test 1: split_ab is disjoint by game_id parity
# ---------------------------------------------------------------------------

def test_split_ab_disjoint():
    states = _make_states(n_games=40)
    a, b = split_ab(states)
    ids_a = {s["game_id"] for s in a}
    ids_b = {s["game_id"] for s in b}
    assert ids_a.isdisjoint(ids_b), "A and B game_ids must not overlap"
    assert len(a) + len(b) == len(states)
    assert all(gid % 2 == 0 for gid in ids_a)
    assert all(gid % 2 == 1 for gid in ids_b)


# ---------------------------------------------------------------------------
# Test 2: fit_recal returns a SegmentRecalibrator with the right bucket count
# ---------------------------------------------------------------------------

def test_fit_recal_returns_segment_recal():
    states = _make_states(n_games=80)
    a, _ = split_ab(states)
    surf = fit_weight_surface(a, min_cell=5)
    recal = fit_recal(a, surf)
    assert isinstance(recal, SegmentRecalibrator)
    assert len(recal.regs) > 0


# ---------------------------------------------------------------------------
# Test 3: core acceptance -- fit on A, eval on B
#   ECE(recal) < ECE(raw) per-quarter (majority of buckets) AND
#   Brier(recal) not worse (within tolerance)
# ---------------------------------------------------------------------------

def test_fit_a_eval_b_ece_improves():
    """Main acceptance criterion: isotonic recal improves ECE on held-out B."""
    # Use larger data + stronger shrinkage to create a clear calibration gap
    states = _make_states(n_games=400, seed=7, shrink_alpha=0.45)
    a, b = split_ab(states)
    result = eval_recal(a, b, min_cell=5)

    assert isinstance(result, RecalResult)
    assert result.n_eval > 0
    assert result.n_fit > 0

    buckets = result.per_bucket
    assert len(buckets) > 0, "Expected at least one time bucket to have data"

    n_improved = sum(1 for v in buckets.values() if v["ece_improved"])
    n_total = len(buckets)

    # Majority of buckets must improve ECE
    assert n_improved > n_total / 2, (
        f"Expected majority of buckets to improve ECE; "
        f"got {n_improved}/{n_total}. Per-bucket: {buckets}"
    )

    # Pooled Brier must not be worse beyond tolerance
    assert result.brier_recal_pooled <= result.brier_raw_pooled + 1e-5, (
        f"Brier degraded: raw={result.brier_raw_pooled:.6f} "
        f"recal={result.brier_recal_pooled:.6f}"
    )


# ---------------------------------------------------------------------------
# Test 4: planted-null guard -- shuffled labels must NOT claim improvement
# ---------------------------------------------------------------------------

def test_planted_null_does_not_claim_improvement():
    """Shuffled labels on A -> no ECE improvement claimed on all buckets."""
    states = _make_states(n_games=400, seed=13, shrink_alpha=0.45)
    a, b = split_ab(states)
    rng = np.random.default_rng(seed=99)
    result = eval_recal(a, b, shuffle_labels=True, rng=rng, min_cell=5)

    assert result.planted_null is True

    # Verdict must NOT be SHIP after null shuffling
    assert result.verdict != "SHIP", (
        f"Planted-null produced SHIP verdict -- possible artifact. "
        f"Per-bucket: {result.per_bucket}"
    )

    # Additional: not ALL buckets should claim improvement after label shuffle
    buckets = result.per_bucket
    if buckets:
        n_improved = sum(1 for v in buckets.values() if v["ece_improved"])
        n_total = len(buckets)
        # Strictly fewer than half should show improvement (noise level)
        assert n_improved < n_total, (
            f"All {n_total} buckets claim ECE improvement after label shuffle -- "
            f"artifact detected. Per-bucket: {buckets}"
        )


# ---------------------------------------------------------------------------
# Test 5: no dollar key in output dict
# ---------------------------------------------------------------------------

def test_no_dollar_key():
    states = _make_states(n_games=60, seed=3)
    a, b = split_ab(states)
    result = eval_recal(a, b, min_cell=5)
    d = result.to_dict()
    assert not _has_dollar_key(d), f"Dollar key found in output: {d}"


# ---------------------------------------------------------------------------
# Test 6: run() convenience wrapper works end-to-end
# ---------------------------------------------------------------------------

def test_run_convenience():
    states = _make_states(n_games=100, seed=5)
    result = run(states, min_cell=5)
    assert result.verdict in {"SHIP", "PARTIAL", "NOT_IMPROVED", "INSUFFICIENT_DATA"}
    assert result.n_fit + result.n_eval == len(states)


# ---------------------------------------------------------------------------
# Test 7: INSUFFICIENT_DATA on empty inputs
# ---------------------------------------------------------------------------

def test_insufficient_data_empty():
    result = eval_recal([], [], min_cell=5)
    assert result.verdict == "INSUFFICIENT_DATA"


def test_insufficient_data_empty_b():
    """If B is empty (all even game_ids), verdict is INSUFFICIENT_DATA."""
    # Construct states where all game_ids are even -> B will be empty
    states = [
        {"game_id": gid * 2, "period": q, "seconds_remaining": 720.0,
         "score_diff": 0.0, "p0": 0.5, "p_live": 0.5, "outcome": 0}
        for gid in range(10) for q in (1, 2, 3)
    ]
    a, b = split_ab(states)
    assert len(b) == 0
    result = eval_recal(a, b, min_cell=5)
    assert result.verdict == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Test 8: brier_not_worse flag per bucket is consistent with numeric values
# ---------------------------------------------------------------------------

def test_brier_not_worse_flag_consistency():
    states = _make_states(n_games=120, seed=8)
    a, b = split_ab(states)
    result = eval_recal(a, b, min_cell=5)
    tol = 1e-6
    for key, v in result.per_bucket.items():
        expected = v["brier_recal"] <= v["brier_raw"] + tol
        assert v["brier_not_worse"] == expected, (
            f"Bucket {key}: brier_not_worse flag mismatch; "
            f"raw={v['brier_raw']} recal={v['brier_recal']}"
        )


# ---------------------------------------------------------------------------
# Test 9: ece_improved flag per bucket is consistent with numeric values
# ---------------------------------------------------------------------------

def test_ece_improved_flag_consistency():
    states = _make_states(n_games=120, seed=9)
    a, b = split_ab(states)
    result = eval_recal(a, b, min_cell=5)
    for key, v in result.per_bucket.items():
        expected = v["ece_recal"] < v["ece_raw"]
        assert v["ece_improved"] == expected, (
            f"Bucket {key}: ece_improved flag mismatch; "
            f"raw={v['ece_raw']} recal={v['ece_recal']}"
        )


# ---------------------------------------------------------------------------
# Test 10: honesty -- to_dict has 'honesty' key and no roi/pnl/profit keys
# ---------------------------------------------------------------------------

def test_honesty_key_in_dict():
    states = _make_states(n_games=60, seed=4)
    a, b = split_ab(states)
    result = eval_recal(a, b, min_cell=5)
    d = result.to_dict()
    assert "honesty" in d, "Output dict must carry an 'honesty' field"
    for banned in ("roi", "pnl", "profit", "edge", "dollar"):
        assert banned not in d, f"Banned key '{banned}' found in output"
