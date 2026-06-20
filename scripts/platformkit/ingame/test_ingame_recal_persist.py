"""Per-file tests for ingame_recal_persist.py.

Acceptance (BACKLOG ig-recal-persist):
  1. SHIP/PARTIAL -> surfaces/nba_recal.json written w/ per-bucket maps + verdict + n.
  2. NOT_IMPROVED / thin -> nothing written (no orphan file).
  3. Round-trips on load. ASCII only. No $/roi/pnl key in artifact.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import pytest

from scripts.platformkit.ingame.ingame_blend_recal import (
    RecalResult,
    SegmentRecalibrator,
    _IdentityReg,
    eval_recal,
    fit_recal,
    split_ab,
)
from scripts.platformkit.eval_gate.ingame_blend import fit_weight_surface
from scripts.platformkit.ingame.ingame_recal_persist import (
    _ARTIFACT_NAME,
    _PERSIST_VERDICTS,
    _extract_iso_map,
    load_recal_surface,
    persist_recal_surface,
    run_and_persist,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _logit(p: np.ndarray) -> np.ndarray:
    return np.log(np.clip(p, 1e-9, 1 - 1e-9) / np.clip(1 - p, 1e-9, 1 - 1e-9))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _make_states(n_games: int = 120, seed: int = 0,
                 shrink_alpha: float = 0.5) -> List[dict]:
    rng = np.random.default_rng(seed)
    qsec = {1: 2160.0, 2: 1440.0, 3: 720.0}
    states: List[dict] = []
    for gid in range(n_games):
        p_true = float(rng.beta(3, 3))
        outcome = int(rng.random() < p_true)
        for q in (1, 2, 3):
            p_sh = float(_sigmoid(np.array(
                [shrink_alpha * _logit(np.array([p_true]))])).item())
            states.append({
                "game_id": gid, "period": q,
                "seconds_remaining": qsec[q],
                "score_diff": (p_true - 0.5) * 20.0,
                "p0": float(np.clip(p_sh + 0.01, 0.01, 0.99)),
                "p_live": float(np.clip(p_sh, 0.01, 0.99)),
                "outcome": outcome,
            })
    return states


def _make_recal(n_games: int = 400, seed: int = 7, min_cell: int = 5):
    states = _make_states(n_games=n_games, seed=seed, shrink_alpha=0.45)
    a, b = split_ab(states)
    surf = fit_weight_surface(a, min_cell=min_cell)
    recal = fit_recal(a, surf)
    result = eval_recal(a, b, min_cell=min_cell)
    return result, recal


def _has_banned_key(obj, _d: int = 0) -> bool:
    BANNED = ("$", "roi", "pnl", "profit")
    if _d > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(t in str(k).lower() for t in BANNED):
                return True
            if isinstance(v, str) and any(t in v.lower() for t in BANNED):
                return True
            if isinstance(v, (dict, list)) and _has_banned_key(v, _d + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_banned_key(item, _d + 1):
                return True
    return False


# ---------------------------------------------------------------------------
# Test 1: SHIP/PARTIAL writes artifact; schema OK + round-trips + no banned keys
# ---------------------------------------------------------------------------

def test_ship_writes_and_round_trips():
    result, recal = _make_recal()
    if result.verdict not in _PERSIST_VERDICTS:
        pytest.skip(f"Data gave {result.verdict}; need SHIP/PARTIAL")

    with tempfile.TemporaryDirectory() as tmp:
        path = persist_recal_surface(result, recal, sport="nba", surfaces_dir=tmp)
        assert path is not None and os.path.exists(path)

        with open(path, encoding="ascii") as f:
            art = json.load(f)

        # Schema checks
        assert art["verdict"] in _PERSIST_VERDICTS
        assert art["sport"] == "nba"
        assert isinstance(art["n_fit"], int) and art["n_fit"] > 0
        assert isinstance(art["n_eval"], int) and art["n_eval"] > 0
        assert "honesty" in art
        assert len(art["per_bucket"]) > 0
        for bucket in art["per_bucket"].values():
            assert "iso_map" in bucket

        # No banned keys
        assert not _has_banned_key(art), "Banned key in artifact"

        # ASCII only
        with open(path, "rb") as f:
            raw = f.read()
        assert not [b for b in raw if b > 127], "Non-ASCII bytes found"

        # Atomic write: no .tmp leftover
        assert not os.path.exists(path + ".tmp")

        # Round-trip
        loaded = load_recal_surface(sport="nba", surfaces_dir=tmp)
        assert loaded is not None
        assert loaded["verdict"] == result.verdict
        assert loaded["n_fit"] == result.n_fit
        for key in result.per_bucket:
            assert key in loaded["per_bucket"]
            assert "iso_map" in loaded["per_bucket"][key]


# ---------------------------------------------------------------------------
# Test 2: NOT_IMPROVED and INSUFFICIENT_DATA write nothing (no orphan file)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("verdict", ["NOT_IMPROVED", "INSUFFICIENT_DATA"])
def test_no_persist_for_bad_verdicts(verdict):
    dummy = RecalResult(verdict=verdict)
    dummy_recal = SegmentRecalibrator()
    dummy_recal.regs[0] = _IdentityReg()
    with tempfile.TemporaryDirectory() as tmp:
        path = persist_recal_surface(dummy, dummy_recal, sport="nba",
                                     surfaces_dir=tmp)
        assert path is None
        assert not (Path(tmp) / _ARTIFACT_NAME).exists()


# ---------------------------------------------------------------------------
# Test 3: load returns None when file is absent
# ---------------------------------------------------------------------------

def test_load_returns_none_when_absent():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_recal_surface(sport="nba", surfaces_dir=tmp) is None


# ---------------------------------------------------------------------------
# Test 4: _extract_iso_map returns None for _IdentityReg
# ---------------------------------------------------------------------------

def test_extract_iso_map_identity():
    assert _extract_iso_map(_IdentityReg()) is None


# ---------------------------------------------------------------------------
# Test 5: _extract_iso_map extracts thresholds from a real IsotonicRegression
# ---------------------------------------------------------------------------

def test_extract_iso_map_real():
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:
        pytest.skip("sklearn not available")
    reg = IsotonicRegression(out_of_bounds="clip")
    reg.fit(np.array([0.1, 0.3, 0.5, 0.7, 0.9]),
            np.array([0.0, 0.0, 1.0, 1.0, 1.0]))
    iso_map = _extract_iso_map(reg)
    assert iso_map is not None
    assert len(iso_map["x_thresholds"]) == len(iso_map["y_thresholds"])
    assert len(iso_map["x_thresholds"]) > 0


# ---------------------------------------------------------------------------
# Test 6: run_and_persist end-to-end high-level runner
# ---------------------------------------------------------------------------

def test_run_and_persist_end_to_end():
    states = _make_states(n_games=400, seed=11, shrink_alpha=0.45)
    with tempfile.TemporaryDirectory() as tmp:
        result, path = run_and_persist(states, sport="nba",
                                       surfaces_dir=tmp, min_cell=5)

    assert result.verdict in {
        "SHIP", "PARTIAL", "NOT_IMPROVED", "INSUFFICIENT_DATA"
    }
    if result.verdict in _PERSIST_VERDICTS:
        assert path is not None and os.path.exists(path)
        with open(path, encoding="ascii") as f:
            art = json.load(f)
        assert art["verdict"] == result.verdict
        assert "per_bucket" in art
        assert "honesty" in art
        assert not _has_banned_key(art)
    else:
        assert path is None
