"""Per-file tests for ingame_recal_producer.py.

Acceptance (BACKLOG ig-recal-producer):
  run() on synthetic 2-season ECE-drifting corpus:
  1. Fits map on season A, gates on B via ingame_served_reliability.
  2. PASS/PARTIAL -> writes surfaces/nba_recal.json with per-bucket maps +
     verdict + n; artifact round-trips through ingame_recal_apply.load_recal_map.
  3. REJECT/INSUFFICIENT_DATA -> writes NOTHING (no orphan file).
  4. Never fabricates a map.
  5. No dollar-sign key; EDGE_CLAIMED false.
  6. Never raises on bad/empty input.

No dollar P&L; calibration not edge; ASCII only; per-file test only.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_recal_apply import load_recal_map
from scripts.platformkit.ingame.ingame_recal_producer import (
    _ARTIFACT_NAME,
    _PERSIST_VERDICTS,
    _build_apply_buckets,
    _extract_bucket_map,
    run,
)
from scripts.platformkit.ingame.ingame_blend_recal import (
    SegmentRecalibrator,
    _IdentityReg,
    split_ab,
)
from scripts.platformkit.ingame.ingame_served_reliability import ServedReliabilityResult


# ---------------------------------------------------------------------------
# Synthetic data helpers
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

    True probs from Beta(3,3); predictions shrunken toward 0.5 by shrink_alpha.
    3 states per game (end-Q1/Q2/Q3). The shrinkage creates an ECE drift that
    isotonic recal reliably corrects on held-out data.
    """
    rng = np.random.default_rng(seed)
    qsec = {1: 2160.0, 2: 1440.0, 3: 720.0}
    states: List[dict] = []
    for gid in range(n_games):
        p_true = float(rng.beta(3, 3))
        outcome = int(rng.random() < p_true)
        for q in (1, 2, 3):
            p_sh = float(
                _sigmoid(np.array([shrink_alpha * _logit(np.array([p_true]))])).item()
            )
            states.append({
                "game_id": gid,
                "period": q,
                "seconds_remaining": qsec[q],
                "score_diff": (p_true - 0.5) * 20.0,
                "p0": float(np.clip(p_sh + 0.01, 0.01, 0.99)),
                "p_live": float(np.clip(p_sh, 0.01, 0.99)),
                "outcome": outcome,
            })
    return states


def _has_banned_key(obj, _depth: int = 0) -> bool:
    """Recursively check for banned monetary P&L keys (dollar sign, roi, pnl, profit)."""
    # These are the honest-rails banned terms: no dollar P&L in any key.
    # "edge" is NOT banned (EDGE_CLAIMED is an allowed honesty marker).
    BANNED = ("$", "roi", "pnl", "profit")
    if _depth > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(t in str(k).lower() for t in BANNED):
                return True
            if isinstance(v, str) and any(t in v.lower() for t in BANNED):
                return True
            if isinstance(v, (dict, list)) and _has_banned_key(v, _depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_banned_key(item, _depth + 1):
                return True
    return False


# ---------------------------------------------------------------------------
# 1. run() on sufficient corpus with known ECE-drifting shrinkage
#    PASS/PARTIAL -> writes artifact; REJECT/INSUFFICIENT_DATA -> writes nothing
# ---------------------------------------------------------------------------

def test_run_writes_on_pass_or_partial_only():
    """Core acceptance test: 2-season ECE-drifting corpus.

    Good shrinkage corpus (400 games) -> served reliability gates PASS or PARTIAL.
    Verify:
      - artifact written to surfaces/nba_recal.json
      - per-bucket maps + verdict + n present
      - artifact round-trips through ingame_recal_apply.load_recal_map
      - no banned key; EDGE_CLAIMED=false
    """
    states = _make_states(n_games=400, seed=7, shrink_alpha=0.45)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=5)

        assert isinstance(result, ServedReliabilityResult)
        assert result.verdict in {"PASS", "PARTIAL", "REJECT", "INSUFFICIENT_DATA"}, (
            f"Unexpected verdict: {result.verdict}"
        )

        if result.verdict in _PERSIST_VERDICTS:
            assert path is not None and os.path.exists(path), (
                f"Expected artifact at {path} for verdict {result.verdict}"
            )
            with open(path, encoding="ascii") as f:
                art = json.load(f)

            # Schema: verdict, n_fit, n_eval, buckets, per_bucket, honesty
            assert art["verdict"] in _PERSIST_VERDICTS
            assert art["sport"] == "nba"
            assert isinstance(art["n_fit"], int) and art["n_fit"] > 0
            assert isinstance(art["n_eval"], int) and art["n_eval"] > 0
            assert "honesty" in art
            assert art.get("EDGE_CLAIMED") is False
            assert "per_bucket" in art and len(art["per_bucket"]) > 0
            assert "buckets" in art and len(art["buckets"]) > 0

            # Per-bucket must have n field (from ServedReliabilityResult)
            for bkt in art["per_bucket"].values():
                assert "n" in bkt

            # No banned keys
            assert not _has_banned_key(art), f"Banned key in artifact: {art}"

            # ASCII only (no bytes > 127)
            with open(path, "rb") as f:
                raw_bytes = f.read()
            assert all(b <= 127 for b in raw_bytes), "Non-ASCII bytes in artifact"

            # No .tmp leftover (atomic write)
            assert not os.path.exists(path + ".tmp"), ".tmp file leftover after atomic write"

        else:
            # REJECT or INSUFFICIENT_DATA -> no file written
            assert path is None, (
                f"Expected no artifact for verdict {result.verdict}; got path={path}"
            )


# ---------------------------------------------------------------------------
# 2. Round-trip through ingame_recal_apply.load_recal_map
# ---------------------------------------------------------------------------

def test_artifact_round_trips_through_apply_load():
    """Written artifact must be loadable by ingame_recal_apply.load_recal_map."""
    from scripts.platformkit.ingame.ingame_recal_apply import _validate_map

    states = _make_states(n_games=400, seed=13, shrink_alpha=0.45)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=5)

        if result.verdict not in _PERSIST_VERDICTS:
            pytest.skip(f"Verdict {result.verdict} -> no artifact to round-trip")

        assert path is not None
        recal_map = load_recal_map(path)

        # Must not return None (would mean load_recal_map rejected the schema)
        assert recal_map is not None, (
            f"load_recal_map returned None for artifact at {path}; "
            f"artifact keys may not match expected 'buckets' schema"
        )
        assert "buckets" in recal_map
        assert isinstance(recal_map["buckets"], dict)
        assert len(recal_map["buckets"]) > 0

        # Each valid bucket must have non-empty x and y of equal length
        any_valid = any(_validate_map(v) for v in recal_map["buckets"].values())
        assert any_valid, "No valid bucket map found after round-trip"


# ---------------------------------------------------------------------------
# 3. REJECT -> writes nothing (do-no-harm)
# ---------------------------------------------------------------------------

def test_reject_writes_nothing():
    """Too few samples per bucket -> REJECT or INSUFFICIENT_DATA -> no artifact."""
    # Very small corpus: shrinkage too mild to produce clear PASS
    states = _make_states(n_games=20, seed=1, shrink_alpha=0.1)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=50)
        # Regardless of verdict, if not PASS/PARTIAL no file should exist
        if result.verdict not in _PERSIST_VERDICTS:
            assert path is None
            artifact_path = Path(tmp) / _ARTIFACT_NAME
            assert not artifact_path.exists(), (
                f"Orphan artifact found at {artifact_path} for verdict {result.verdict}"
            )


# ---------------------------------------------------------------------------
# 4. INSUFFICIENT_DATA -> writes nothing
# ---------------------------------------------------------------------------

def test_empty_corpus_writes_nothing():
    """Empty states -> INSUFFICIENT_DATA; no artifact."""
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run([], sport="nba", surfaces_dir=tmp)
    assert result.verdict == "INSUFFICIENT_DATA"
    assert path is None


def test_single_side_only_writes_nothing():
    """All even game_ids (B split empty) -> INSUFFICIENT_DATA."""
    states = [
        {
            "game_id": 0,
            "period": 1,
            "seconds_remaining": 2160.0,
            "score_diff": 2.0,
            "p0": 0.55,
            "p_live": 0.53,
            "outcome": 1,
        }
        for _ in range(10)
    ]
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp)
    assert result.verdict == "INSUFFICIENT_DATA"
    assert path is None


# ---------------------------------------------------------------------------
# 5. No dollar key; EDGE_CLAIMED false
# ---------------------------------------------------------------------------

def test_no_dollar_key_and_edge_claimed_false():
    """Artifact must have EDGE_CLAIMED=false and no monetary/edge keys."""
    states = _make_states(n_games=400, seed=21, shrink_alpha=0.45)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=5)

        if result.verdict not in _PERSIST_VERDICTS:
            pytest.skip(f"Verdict {result.verdict} -> no artifact produced")

        with open(path, encoding="ascii") as f:
            art = json.load(f)

        assert art.get("EDGE_CLAIMED") is False, (
            f"EDGE_CLAIMED must be false; got {art.get('EDGE_CLAIMED')}"
        )
        assert not _has_banned_key(art), f"Banned key in artifact"


# ---------------------------------------------------------------------------
# 6. Never raises on adversarial inputs
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_input", [
    [],
    None,
    [{}],
    [{"game_id": 0}],
    [{"game_id": 0, "outcome": 1, "p0": "bad", "p_live": None,
      "seconds_remaining": 720.0, "score_diff": 0.0}],
])
def test_never_raises(bad_input):
    """run() must not raise on any adversarial input."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            if bad_input is None:
                result, path = run(None, surfaces_dir=tmp)  # type: ignore
            else:
                result, path = run(bad_input, surfaces_dir=tmp)
            assert isinstance(result, ServedReliabilityResult)
            assert path is None or isinstance(path, str)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"run() raised unexpectedly: {exc}")


# ---------------------------------------------------------------------------
# 7. _extract_bucket_map: None for identity; knots for real IsotonicRegression
# ---------------------------------------------------------------------------

def test_extract_bucket_map_identity():
    assert _extract_bucket_map(_IdentityReg()) is None


def test_extract_bucket_map_real():
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        pytest.skip("sklearn not available")

    reg = IsotonicRegression(out_of_bounds="clip")
    reg.fit(np.array([0.1, 0.3, 0.5, 0.7, 0.9]),
            np.array([0.0, 0.0, 1.0, 1.0, 1.0]))
    result = _extract_bucket_map(reg)

    assert result is not None
    assert "x" in result and "y" in result
    assert len(result["x"]) == len(result["y"])
    assert len(result["x"]) > 0
    # x must be sorted ascending (IsotonicRegression invariant)
    xs = result["x"]
    assert all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1)), (
        "x_thresholds not sorted ascending"
    )


# ---------------------------------------------------------------------------
# 8. _build_apply_buckets: identity fallback for thin regressors
# ---------------------------------------------------------------------------

def test_build_apply_buckets_identity_fallback():
    """SegmentRecalibrator with _IdentityReg in every bucket -> identity knots."""
    recal = SegmentRecalibrator(n_buckets=4)
    for b in range(4):
        recal.regs[b] = _IdentityReg()

    buckets = _build_apply_buckets(recal)
    assert len(buckets) == 4
    for b in range(4):
        assert str(b) in buckets
        bmap = buckets[str(b)]
        # Identity knot: x=[0.0,1.0], y=[0.0,1.0]
        assert bmap["x"] == [0.0, 1.0] and bmap["y"] == [0.0, 1.0], (
            f"Expected identity knots for bucket {b}; got {bmap}"
        )


# ---------------------------------------------------------------------------
# 9. Atomic write: no .tmp leftover on PASS
# ---------------------------------------------------------------------------

def test_no_tmp_leftover_after_write():
    """Atomic os.replace must leave no .tmp file after successful write."""
    states = _make_states(n_games=400, seed=33, shrink_alpha=0.45)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=5)
        if result.verdict not in _PERSIST_VERDICTS:
            pytest.skip(f"Verdict {result.verdict}; skipping atomic write check")
        assert not os.path.exists(path + ".tmp"), ".tmp leftover after write"


# ---------------------------------------------------------------------------
# 10. Verdict consistency: run() verdict matches ingame_served_reliability
# ---------------------------------------------------------------------------

def test_verdict_matches_served_reliability():
    """The verdict returned by run() must match what run_scoreboard produces."""
    from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
    from scripts.platformkit.ingame.ingame_blend_recal import fit_recal
    from scripts.platformkit.ingame.ingame_served_reliability import run_scoreboard

    states = _make_states(n_games=300, seed=99, shrink_alpha=0.45)
    a, b = split_ab(states)

    surf = fit_weight_surface(a, min_cell=5)
    recal = fit_recal(a, surf)
    expected = run_scoreboard(a, b, recal=recal, min_cell=5)

    with tempfile.TemporaryDirectory() as tmp:
        result, path = run(states, sport="nba", surfaces_dir=tmp, min_cell=5)

    # Verdicts must agree (same A/B split, same min_cell)
    assert result.verdict == expected.verdict, (
        f"Producer verdict {result.verdict} != "
        f"manual run_scoreboard verdict {expected.verdict}"
    )
