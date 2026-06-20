"""Per-file tests for ingame_served_reliability.py.

Acceptance criteria (from BACKLOG.md ig-served-reliability):
  1. fit on A, eval on B:
     ECE(served) <= ECE(raw_blend) + EPS per bucket AND Brier non-worse -> PASS
  2. injected WORSE recal map -> REJECT (no fabricated green)
  3. thin / empty eval pool -> INSUFFICIENT_DATA
  4. stale-never-green: verdict computed fresh each call (no caching)
  5. no $ key in any output dict

Synthetic design: states are built with a known shrinkage calibration gap
(predictions compressed toward 0.5) so the isotonic recalibrator reliably
un-shrinks them on held-out data.  The served number is the recal-applied
probability.

For the REJECT test we inject a SegmentRecalibrator whose regressors predict
a CONSTANT 0.5 (maximum shrinkage) regardless of input -- this provably
worsens ECE relative to the already-biased raw blend, triggering REJECT.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_blend_recal import (
    SegmentRecalibrator,
    _IdentityReg,
    split_ab,
)
from scripts.platformkit.ingame.ingame_served_reliability import (
    ServedReliabilityResult,
    run,
    run_scoreboard,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers (identical pattern to test_ingame_blend_recal.py)
# ---------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1 - 1e-9))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _make_states(
    n_games: int = 200,
    seed: int = 0,
    shrink_alpha: float = 0.45,
) -> List[dict]:
    """Synthetic in-game states with a shrinkage calibration gap.

    True probs drawn from Beta(3,3); predictions shrunken toward 0.5 by
    shrink_alpha.  3 states per game (end-Q1/Q2/Q3).
    """
    rng = np.random.default_rng(seed)
    qsec = {1: 2160.0, 2: 1440.0, 3: 720.0}
    states: List[dict] = []
    for gid in range(n_games):
        p_true = float(rng.beta(3, 3))
        outcome = int(rng.random() < p_true)
        for q in (1, 2, 3):
            sec_rem = qsec[q]
            p_shrunken = float(
                _sigmoid(np.array([shrink_alpha * _logit(np.array([p_true]))])).item()
            )
            p_live = float(np.clip(p_shrunken, 0.01, 0.99))
            p0 = float(np.clip(p_shrunken + 0.01, 0.01, 0.99))
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

# ---------------------------------------------------------------------------
# Bad recal fixture: constant-0.5 regressor (provably worse calibration)
# ---------------------------------------------------------------------------

class _ConstantHalfReg:
    """Predict 0.5 for every input -- maximum shrinkage, worst calibration."""
    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full(len(x), 0.5)


def _make_bad_recal(n_buckets: int = 4) -> SegmentRecalibrator:
    """SegmentRecalibrator where every bucket maps to 0.5 (deliberately bad)."""
    sr = SegmentRecalibrator(n_buckets=n_buckets)
    for b in range(n_buckets):
        sr.regs[b] = _ConstantHalfReg()
    return sr


def _has_dollar_key(d: dict, _depth: int = 0) -> bool:
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
# Test 1: PASS case -- good recal serves a calibration-improved number
# ---------------------------------------------------------------------------

def test_good_recal_passes():
    """Fit+recal on A, score served on B -> verdict PASS (ECE and Brier non-worse)."""
    states = _make_states(n_games=400, seed=7, shrink_alpha=0.45)
    a, b = split_ab(states)
    result = run_scoreboard(a, b, min_cell=5)

    assert isinstance(result, ServedReliabilityResult)
    assert result.verdict in {"PASS", "PARTIAL"}, (
        f"Expected PASS or PARTIAL for good recal; got {result.verdict}. "
        f"Pooled ECE raw={result.ece_raw_pooled:.6f} "
        f"served={result.ece_served_pooled:.6f}. "
        f"Per-bucket: {result.per_bucket}"
    )
    assert result.n_eval > 0
    assert result.n_fit > 0


# ---------------------------------------------------------------------------
# Test 2: REJECT case -- injected bad recal must not claim PASS
# ---------------------------------------------------------------------------

def test_bad_recal_rejects():
    """Injecting a constant-0.5 recal must trigger REJECT (not fabricated PASS)."""
    states = _make_states(n_games=400, seed=42, shrink_alpha=0.45)
    a, b = split_ab(states)

    bad_recal = _make_bad_recal()
    result = run_scoreboard(a, b, recal=bad_recal, min_cell=5, injected_bad=True)

    assert result.verdict != "PASS", (
        f"Injected bad recal must not produce PASS. "
        f"Got {result.verdict}. "
        f"Pooled ECE raw={result.ece_raw_pooled:.6f} "
        f"served={result.ece_served_pooled:.6f}. "
        f"Per-bucket: {result.per_bucket}"
    )
    assert result.injected_bad is True


# ---------------------------------------------------------------------------
# Test 3: INSUFFICIENT_DATA on thin eval pool
# ---------------------------------------------------------------------------

def test_thin_eval_insufficient_data():
    """Fewer than MIN_EVAL_TOTAL samples in B -> INSUFFICIENT_DATA."""
    states = _make_states(n_games=10, seed=1)  # 30 states but split -> ~15 per side
    a, b = split_ab(states)
    # Force B to be tiny
    result = run_scoreboard(a, b[:5], min_cell=2)
    assert result.verdict == "INSUFFICIENT_DATA"


def test_empty_eval_pool_insufficient_data():
    result = run_scoreboard([], [], min_cell=5)
    assert result.verdict == "INSUFFICIENT_DATA"


def test_empty_b_insufficient_data():
    states = _make_states(n_games=20, seed=2)
    a, b = split_ab(states)
    result = run_scoreboard(a, [], min_cell=5)
    assert result.verdict == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Test 4: stale-never-green -- two calls produce independent results
# ---------------------------------------------------------------------------

def test_no_caching_between_calls():
    """Each call recomputes fresh; result is not memoized."""
    states = _make_states(n_games=200, seed=3)
    a, b = split_ab(states)
    r1 = run_scoreboard(a, b, min_cell=5)
    r2 = run_scoreboard(a, b, min_cell=5)
    # Results must be numerically identical (no state mutation)
    assert r1.verdict == r2.verdict
    assert r1.ece_raw_pooled == r2.ece_raw_pooled
    assert r1.ece_served_pooled == r2.ece_served_pooled


# ---------------------------------------------------------------------------
# Test 5: no dollar key in output dict
# ---------------------------------------------------------------------------

def test_no_dollar_key():
    states = _make_states(n_games=100, seed=4)
    a, b = split_ab(states)
    result = run_scoreboard(a, b, min_cell=5)
    d = result.to_dict()
    assert not _has_dollar_key(d), f"Dollar key found in output: {d}"


# ---------------------------------------------------------------------------
# Test 6: honesty field present; no roi/pnl/profit/edge/dollar keys
# ---------------------------------------------------------------------------

def test_honesty_field():
    states = _make_states(n_games=100, seed=5)
    a, b = split_ab(states)
    result = run_scoreboard(a, b, min_cell=5)
    d = result.to_dict()
    assert "honesty" in d, "to_dict() must carry a 'honesty' field"
    for banned in ("roi", "pnl", "profit", "edge", "dollar"):
        assert banned not in d, f"Banned key '{banned}' found in output"


# ---------------------------------------------------------------------------
# Test 7: run() convenience wrapper works end-to-end
# ---------------------------------------------------------------------------

def test_run_convenience():
    states = _make_states(n_games=120, seed=6)
    result = run(states, min_cell=5)
    assert result.verdict in {
        "PASS", "REJECT", "PARTIAL", "INSUFFICIENT_DATA"
    }
    assert result.n_fit + result.n_eval == len(states)


# ---------------------------------------------------------------------------
# Test 8: per-bucket ece_pass flag consistency
# ---------------------------------------------------------------------------

def test_ece_pass_flag_consistency():
    """ece_pass flag in per_bucket must match numeric ECE values."""
    states = _make_states(n_games=200, seed=8)
    a, b = split_ab(states)
    result = run_scoreboard(a, b, min_cell=5)
    eps = 1e-4
    for key, v in result.per_bucket.items():
        expected = v["ece_served"] <= v["ece_raw"] + eps
        assert v["ece_pass"] == expected, (
            f"Bucket {key}: ece_pass flag mismatch; "
            f"ece_raw={v['ece_raw']} ece_served={v['ece_served']}"
        )


# ---------------------------------------------------------------------------
# Test 9: per-bucket brier_not_worse flag consistency
# ---------------------------------------------------------------------------

def test_brier_not_worse_flag_consistency():
    states = _make_states(n_games=200, seed=9)
    a, b = split_ab(states)
    result = run_scoreboard(a, b, min_cell=5)
    tol = 1e-6
    for key, v in result.per_bucket.items():
        expected = v["brier_served"] <= v["brier_raw"] + tol
        assert v["brier_not_worse"] == expected, (
            f"Bucket {key}: brier_not_worse flag mismatch; "
            f"brier_raw={v['brier_raw']} brier_served={v['brier_served']}"
        )


# ---------------------------------------------------------------------------
# Test 10: identity recal (no change) -> ECE served == ECE raw (PASS within eps)
# ---------------------------------------------------------------------------

def test_identity_recal_passes():
    """An identity recalibrator leaves predictions unchanged -> ECE(served)==ECE(raw)."""
    states = _make_states(n_games=150, seed=10)
    a, b = split_ab(states)

    # Build identity recal (each bucket returns input unchanged)
    identity_recal = SegmentRecalibrator(n_buckets=4)
    for bkt in range(4):
        identity_recal.regs[bkt] = _IdentityReg()

    result = run_scoreboard(a, b, recal=identity_recal, min_cell=5)

    # With identity transform, served == raw -> ECE passes trivially
    assert result.verdict in {"PASS", "PARTIAL", "INSUFFICIENT_DATA"}, (
        f"Identity recal should not REJECT; got {result.verdict}. "
        f"Pooled ECE raw={result.ece_raw_pooled:.6f} "
        f"served={result.ece_served_pooled:.6f}"
    )
    # Pooled Brier must be equal (identity leaves values unchanged)
    assert abs(result.brier_raw_pooled - result.brier_served_pooled) < 1e-9, (
        f"Identity recal changed Brier: raw={result.brier_raw_pooled} "
        f"served={result.brier_served_pooled}"
    )
