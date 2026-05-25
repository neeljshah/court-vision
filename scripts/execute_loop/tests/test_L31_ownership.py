"""test_L31_ownership.py — Tests for L31_ownership.py (BUILD L31).

Tests
-----
1. Sum approx 8: 50-player synthetic slate → 7.95 ≤ Σ ≤ 8.05
2. Star (salary=11000, fpts.mean=50) → ownership > 0.20
3. Low-value (salary=8000, fpts.mean=15) → ownership ≤ 0.07
4. Late-news boost: monkeypatched L20 → that player's ownership ≥ base + 0.13
5. Roundtrip: predict_ownership → file written → load_ownership returns identical dict
6. Cap at 0.70: one player with huge value → final ≤ 0.70
7. Missing fpts_data entry → ownership == 0.0

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L31_ownership.py -v
"""
from __future__ import annotations

import datetime
import json
import sys
from pathlib import Path
from typing import Dict
from unittest.mock import patch

import numpy as np
import pytest

# Ensure project root is on path
_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT))

from scripts.execute_loop.L01_slate_ingester import SlateContest
from scripts.execute_loop.L02_fpts_distribution import FPTSDistribution
from scripts.execute_loop.L31_ownership import (
    _BASE_OWNERSHIP,
    _OWNERSHIP_DIR,
    compute_value_score,
    heuristic_ownership_v1,
    load_ownership,
    predict_ownership,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DK_SLOTS = ["PG", "SG", "SF", "PF", "C", "FLEX", "UTIL", "UTIL"]
_POSITIONS = ["PG", "SG", "SF", "PF", "C"]


def _make_dist(mean: float) -> FPTSDistribution:
    """Build a minimal FPTSDistribution with the given mean."""
    return FPTSDistribution(
        mean=mean,
        std=5.0,
        q10=max(0.0, mean - 8.0),
        q50=mean,
        q90=mean + 8.0,
        samples=np.random.default_rng(42).normal(mean, 5.0, 500),
        per_stat_means={},
        has_double_double_p=0.1,
        has_triple_double_p=0.01,
    )


def _make_player(
    pid: str,
    salary: int = 7000,
    position: str = "PG",
    name: str = "Player",
) -> dict:
    return {
        "player_id": pid,
        "name": name,
        "team": "LAL",
        "position": position,
        "salary": salary,
        "status": "",
    }


def _make_slate(players: list) -> SlateContest:
    return SlateContest(
        contest_id="test_contest",
        book="dk",
        sport="NBA",
        slate_type="classic",
        salary_cap=50000,
        roster_slots=_DK_SLOTS,
        lock_time="2026-05-25T19:00:00+00:00",
        game_ids=["g1"],
        players=players,
    )


def _make_50_player_slate():
    """Build a 50-player slate with varied salaries and projected FPTS."""
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}
    positions = _POSITIONS * 10  # 10 per position = 50 total
    rng = np.random.default_rng(7)

    for i in range(50):
        pid = f"p{i:03d}"
        salary = int(rng.integers(3500, 11000))
        pos = positions[i]
        mean_fpts = float(rng.uniform(8.0, 55.0))
        players.append(_make_player(pid, salary=salary, position=pos, name=f"Player{i}"))
        fpts_data[pid] = _make_dist(mean_fpts)

    return _make_slate(players), fpts_data


# ---------------------------------------------------------------------------
# Test 1 — Sum approx 8
# ---------------------------------------------------------------------------

def test_sum_approx_eight():
    """50-player slate: Σ ownership ∈ [7.95, 8.05]."""
    slate, fpts_data = _make_50_player_slate()
    result = heuristic_ownership_v1(slate, fpts_data)

    assert len(result) > 0, "Expected non-empty ownership dict."
    total = sum(result.values())
    assert 7.95 <= total <= 8.05, (
        f"Expected Σ ≈ 8.0, got {total:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 2 — Star ownership
# ---------------------------------------------------------------------------

def test_star_ownership():
    """Star (salary=11000, fpts.mean=50) in a controlled small pool should own > 0.20.

    Uses 15 players where the star's value is clearly top-tier in its position bucket,
    ensuring the top-value bonus + star premium are both applied and survive normalisation.
    """
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}

    # 14 filler players — modest salary, modest FPTS (value ≈ 3-4)
    for i in range(14):
        pid = f"fill{i}"
        pos = _POSITIONS[i % len(_POSITIONS)]
        players.append(_make_player(pid, salary=7000, position=pos))
        fpts_data[pid] = _make_dist(25.0)

    # Star: salary=11000, FPTS=50 → value = 50/11 ≈ 4.55 — top PG by value + star premium
    star_pid = "star_001"
    players.append(_make_player(star_pid, salary=11000, position="PG", name="StarPlayer"))
    fpts_data[star_pid] = _make_dist(50.0)

    slate = _make_slate(players)
    result = heuristic_ownership_v1(slate, fpts_data)

    assert star_pid in result, "Star player not in result."
    assert result[star_pid] > 0.20, (
        f"Expected star ownership > 0.20, got {result[star_pid]:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 3 — Low-value ownership
# ---------------------------------------------------------------------------

def test_low_value_ownership():
    """Low-value player (salary=8000, fpts.mean=15) should own ≤ 0.07 after normalization."""
    # Build a 30-player pool; insert a low-value player
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}
    rng = np.random.default_rng(13)

    for i in range(29):
        pid = f"p{i:03d}"
        salary = int(rng.integers(4000, 12000))
        pos = _POSITIONS[i % len(_POSITIONS)]
        mean_fpts = float(rng.uniform(25.0, 60.0))
        players.append(_make_player(pid, salary=salary, position=pos))
        fpts_data[pid] = _make_dist(mean_fpts)

    low_pid = "low_001"
    players.append(_make_player(low_pid, salary=8000, position="SG", name="LowValue"))
    fpts_data[low_pid] = _make_dist(15.0)

    slate = _make_slate(players)
    result = heuristic_ownership_v1(slate, fpts_data)

    assert low_pid in result, "Low-value player not in result."
    assert result[low_pid] <= 0.07, (
        f"Expected low-value ownership ≤ 0.07, got {result[low_pid]:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 4 — Late-news boost
# ---------------------------------------------------------------------------

def test_late_news_boost(monkeypatch):
    """Player with confirmed_starter_late status should receive ≥ base + 0.13 boost."""
    boost_pid = "late_news_001"
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}
    rng = np.random.default_rng(99)

    for i in range(20):
        pid = f"base{i:03d}"
        pos = _POSITIONS[i % len(_POSITIONS)]
        players.append(_make_player(pid, salary=int(rng.integers(4000, 9000)), position=pos))
        fpts_data[pid] = _make_dist(float(rng.uniform(15.0, 40.0)))

    # Late-news player starts with a modest projection
    players.append(_make_player(boost_pid, salary=6000, position="PF", name="LateNewsGuy"))
    fpts_data[boost_pid] = _make_dist(20.0)

    slate = _make_slate(players)

    # Monkeypatch L20 inside the module under test
    fake_status = {boost_pid: "confirmed_starter_late"}
    monkeypatch.setattr(
        "scripts.execute_loop.L31_ownership._load_late_news_statuses",
        lambda: fake_status,
    )

    result = heuristic_ownership_v1(slate, fpts_data)

    assert boost_pid in result, "Late-news player not in result."
    # Minimum expected: base (0.05) + late-news boost (0.15) = 0.20, post-norm may shrink but ≥ 0.18
    # Use a conservative lower bound: base_ownership + 0.13
    assert result[boost_pid] >= _BASE_OWNERSHIP + 0.13, (
        f"Expected ownership ≥ {_BASE_OWNERSHIP + 0.13:.2f}, got {result[boost_pid]:.4f}"
    )


# ---------------------------------------------------------------------------
# Test 5 — Roundtrip persist + load
# ---------------------------------------------------------------------------

def test_roundtrip_persist_load(tmp_path, monkeypatch):
    """predict_ownership writes file; load_ownership returns same values (tol 1e-6)."""
    slate, fpts_data = _make_50_player_slate()

    # Redirect ownership dir to tmp_path
    monkeypatch.setattr("scripts.execute_loop.L31_ownership._OWNERSHIP_DIR", tmp_path)

    today = datetime.date.today().isoformat()
    result = predict_ownership(slate, fpts_data, _ownership_dir=tmp_path)

    assert len(result) > 0, "predict_ownership returned empty dict."

    # File should exist at tmp_path/<today>.json
    written_path = tmp_path / f"{today}.json"
    assert written_path.exists(), f"Ownership file not written at {written_path}"

    loaded = load_ownership(today, ownership_dir=tmp_path)
    assert loaded is not None, "load_ownership returned None for existing file."
    assert set(loaded.keys()) == set(result.keys()), "Key mismatch after roundtrip."

    for pid in result:
        assert abs(loaded[pid] - result[pid]) < 1e-6, (
            f"Ownership mismatch for {pid}: persisted={result[pid]}, loaded={loaded[pid]}"
        )


# ---------------------------------------------------------------------------
# Test 6 — Cap at 0.70
# ---------------------------------------------------------------------------

def test_cap_at_070():
    """Even if raw ownership would exceed 0.70, final value ≤ 0.70."""
    # One dominant star with massive salary + FPTS, tiny rest of pool
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}

    # 7 filler players with very low projections
    for i in range(7):
        pid = f"filler{i}"
        pos = _POSITIONS[i % len(_POSITIONS)]
        players.append(_make_player(pid, salary=3500, position=pos))
        fpts_data[pid] = _make_dist(1.0)  # near-zero FPTS

    # Dominant player — would naturally "deserve" ~1.5 raw ownership
    dom_pid = "dominant"
    players.append(_make_player(dom_pid, salary=11500, position="C", name="Dominant"))
    fpts_data[dom_pid] = _make_dist(120.0)  # absurd projection

    slate = _make_slate(players)
    result = heuristic_ownership_v1(slate, fpts_data)

    assert dom_pid in result, "Dominant player not in result."
    assert result[dom_pid] <= 0.70, (
        f"Expected cap at 0.70, got {result[dom_pid]:.4f}"
    )
    # All players capped
    for pid, own in result.items():
        assert own <= 0.70 + 1e-9, f"Player {pid} exceeds cap: {own:.4f}"


# ---------------------------------------------------------------------------
# Test 7 — Missing fpts_data entry → 0.0
# ---------------------------------------------------------------------------

def test_missing_fpts_data_zero():
    """Player present in slate but absent from fpts_data → ownership == 0.0."""
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}

    for i in range(10):
        pid = f"p{i}"
        pos = _POSITIONS[i % len(_POSITIONS)]
        players.append(_make_player(pid, salary=7000 + i * 100, position=pos))
        fpts_data[pid] = _make_dist(30.0 + i)

    missing_pid = "ghost_player"
    players.append(_make_player(missing_pid, salary=8000, position="PG", name="Ghost"))
    # Intentionally NOT added to fpts_data

    slate = _make_slate(players)
    result = heuristic_ownership_v1(slate, fpts_data)

    assert missing_pid in result, "Missing-fpts player should be in result."
    assert result[missing_pid] == 0.0, (
        f"Expected ownership == 0.0 for missing fpts entry, got {result[missing_pid]}"
    )


# ---------------------------------------------------------------------------
# Additional — compute_value_score edge cases
# ---------------------------------------------------------------------------

def test_compute_value_score_normal():
    """Standard case: 8000 salary, 40 FPTS → 5.0."""
    assert abs(compute_value_score(8000.0, 40.0) - 5.0) < 1e-9


def test_compute_value_score_zero_salary():
    """Salary=0 → 0.0 (no ZeroDivisionError)."""
    assert compute_value_score(0.0, 30.0) == 0.0


def test_compute_value_score_zero_fpts():
    """FPTS=0 → 0.0 value."""
    assert compute_value_score(7500.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Additional — empty slate returns {}
# ---------------------------------------------------------------------------

def test_empty_slate_returns_empty_dict():
    """Empty slate → predict_ownership returns {} and no file written."""
    slate = _make_slate([])
    result = heuristic_ownership_v1(slate, {})
    assert result == {}, f"Expected empty dict for empty slate, got {result}"


# ---------------------------------------------------------------------------
# Additional — load_ownership returns None for missing file
# ---------------------------------------------------------------------------

def test_load_ownership_missing_file(tmp_path):
    """load_ownership returns None when file does not exist."""
    result = load_ownership("2000-01-01", ownership_dir=tmp_path)
    assert result is None, f"Expected None for missing file, got {result}"


# ---------------------------------------------------------------------------
# Additional — predict_ownership v2 raises NotImplementedError
# ---------------------------------------------------------------------------

def test_predict_ownership_v2_not_implemented(tmp_path):
    """predict_ownership(version='v2') raises NotImplementedError."""
    slate, fpts_data = _make_50_player_slate()
    with pytest.raises(NotImplementedError):
        predict_ownership(slate, fpts_data, version="v2", _ownership_dir=tmp_path)


# ---------------------------------------------------------------------------
# Additional — all-equal salaries → flat ownership
# ---------------------------------------------------------------------------

def test_all_equal_salaries_flat():
    """All equal salaries → ownership is evenly distributed (flat per player)."""
    n = 20
    players = []
    fpts_data: Dict[str, FPTSDistribution] = {}
    for i in range(n):
        pid = f"eq{i}"
        pos = _POSITIONS[i % len(_POSITIONS)]
        players.append(_make_player(pid, salary=7000, position=pos))
        fpts_data[pid] = _make_dist(30.0)

    slate = _make_slate(players)
    result = heuristic_ownership_v1(slate, fpts_data)

    values = list(result.values())
    assert len(values) == n
    # All values should be equal (flat distribution)
    assert max(values) - min(values) < 0.01, (
        f"Expected flat ownership with equal salaries, range={max(values) - min(values):.4f}"
    )
    total = sum(values)
    assert 7.95 <= total <= 8.05, f"Sum should still ≈ 8.0, got {total:.4f}"
