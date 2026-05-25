"""test_L02_fpts.py — Tests for L02_fpts_distribution.py (BUILD L2).

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L02_fpts.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure project root is on path
_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT))

from scripts.execute_loop.L02_fpts_distribution import (
    FPTSDistribution,
    compute_player_fpts,
    score_box_to_fpts,
    simulate_lineup_fpts,
)


# ---------------------------------------------------------------------------
# Test 1 — DK scoring with DD + TD bonus
# ---------------------------------------------------------------------------
def test_score_box_dk_triple_double():
    """pts=30, reb=10, ast=10, fg3m=2, stl=1, blk=1, tov=3 with DK scoring."""
    box = {"pts": 30, "reb": 10, "ast": 10, "fg3m": 2, "stl": 1, "blk": 1, "tov": 3}
    result = score_box_to_fpts(box, "DK")
    # base: 30*1 + 10*1.25 + 10*1.5 + 2*0.5 + 1*2 + 1*2 + 3*(-0.5)
    #     = 30 + 12.5 + 15 + 1.0 + 2 + 2 - 1.5 = 61.0
    # TD bonus = +3.0 → 64.0
    assert abs(result - 64.0) < 1e-9, f"Expected 64.0, got {result}"


# ---------------------------------------------------------------------------
# Test 2 — FD scoring (no DD/TD bonus)
# ---------------------------------------------------------------------------
def test_score_box_fd_no_bonus():
    """Same box, FD scoring — no DD/TD bonus in FanDuel."""
    box = {"pts": 30, "reb": 10, "ast": 10, "fg3m": 2, "stl": 1, "blk": 1, "tov": 3}
    result = score_box_to_fpts(box, "FD")
    # 30*1 + 10*1.2 + 10*1.5 + 2*0 + 1*3 + 1*3 + 3*(-1.0)
    # = 30 + 12 + 15 + 0 + 3 + 3 - 3 = 60.0
    assert abs(result - 60.0) < 1e-9, f"Expected 60.0, got {result}"


# ---------------------------------------------------------------------------
# Test 3 — DK double-double (no triple)
# ---------------------------------------------------------------------------
def test_score_box_dk_double_double_only():
    """pts=25, reb=10, ast=5 — exactly double-double (pts + reb), DK +1.5."""
    box = {"pts": 25, "reb": 10, "ast": 5, "fg3m": 0, "stl": 0, "blk": 0, "tov": 0}
    result = score_box_to_fpts(box, "DK")
    # base: 25*1 + 10*1.25 + 5*1.5 = 25 + 12.5 + 7.5 = 45.0
    # DD bonus = +1.5 → 46.5
    assert abs(result - 46.5) < 1e-9, f"Expected 46.5, got {result}"


# ---------------------------------------------------------------------------
# Test 4 — Unknown book raises ValueError
# ---------------------------------------------------------------------------
def test_score_box_unknown_book_raises():
    box = {"pts": 20, "reb": 5, "ast": 3, "fg3m": 1, "stl": 1, "blk": 0, "tov": 2}
    with pytest.raises(ValueError, match="Unknown book"):
        score_box_to_fpts(box, "UNKNOWN")


# ---------------------------------------------------------------------------
# Test 5 — Jokic smoke test (skipped if models missing)
# ---------------------------------------------------------------------------
def test_compute_player_fpts_jokic_smoke():
    """Smoke test: Nikola Jokic with DK scoring should return a valid FPTSDistribution."""
    _model_dir = _PROJECT / "data" / "models"
    _model_file = _model_dir / "prop_pts_v3_lgb.txt"
    if not _model_file.exists():
        pytest.skip("prop_pts_v3_lgb.txt missing — model not trained yet")

    result = compute_player_fpts(
        "Nikola Jokic", "LAL", "2024-25",
        book="DK",
        n_samples=1000,
    )
    if result is None:
        pytest.skip("Jokic prediction returned None (gamelog data missing)")

    assert isinstance(result, FPTSDistribution)
    assert result.mean > 30.0, f"Expected mean > 30, got {result.mean}"
    assert result.std > 0.0, f"Expected std > 0, got {result.std}"
    assert result.samples.shape == (1000,), f"Expected (1000,) samples, got {result.samples.shape}"
    # Sanity-check quantile ordering
    assert result.q10 <= result.q50 <= result.q90
    # per_stat_means should have all 7 stats
    from src.prediction.prop_pergame import STATS
    for s in STATS:
        assert s in result.per_stat_means, f"Missing stat {s} in per_stat_means"
    # DD/TD probs in [0, 1]
    assert 0.0 <= result.has_double_double_p <= 1.0
    assert 0.0 <= result.has_triple_double_p <= 1.0


# ---------------------------------------------------------------------------
# Test 6 — n_samples=0 returns empty samples array
# ---------------------------------------------------------------------------
def test_compute_player_fpts_zero_samples():
    """n_samples=0 returns FPTSDistribution with len(samples)==0."""
    _model_dir = _PROJECT / "data" / "models"
    _model_file = _model_dir / "prop_pts_v3_lgb.txt"
    if not _model_file.exists():
        pytest.skip("prop_pts_v3_lgb.txt missing — model not trained yet")

    result = compute_player_fpts(
        "Nikola Jokic", "LAL", "2024-25",
        book="DK",
        n_samples=0,
    )
    if result is None:
        pytest.skip("Jokic prediction returned None (gamelog data missing)")

    assert isinstance(result, FPTSDistribution)
    assert len(result.samples) == 0
    # Analytical q50 should be finite and positive
    assert np.isfinite(result.q50), "q50 should be finite for n_samples=0"
    assert result.q50 > 0.0, f"q50 should be positive, got {result.q50}"
    # mean/std/q10/q90 are NaN for n_samples=0
    assert np.isnan(result.mean)
    assert np.isnan(result.std)
    assert np.isnan(result.q10)
    assert np.isnan(result.q90)


# ---------------------------------------------------------------------------
# Test 7 — Unknown player returns None
# ---------------------------------------------------------------------------
def test_compute_player_fpts_unknown_player():
    """Requesting an unknown player returns None (with a warning)."""
    import warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = compute_player_fpts(
            "NotARealPlayer XYZ", "LAL", "2024-25",
            book="DK",
            n_samples=10,
        )
    assert result is None, f"Expected None for unknown player, got {result}"
    # Should have emitted a warning
    assert any("not found" in str(warning.message).lower() for warning in w), \
        "Expected a 'not found' warning for unknown player"


# ---------------------------------------------------------------------------
# Test 8 — simulate_lineup_fpts sums independent samples
# ---------------------------------------------------------------------------
def test_simulate_lineup_fpts_shape_and_sum():
    """simulate_lineup_fpts returns correct shape and sums player distributions."""
    rng = np.random.default_rng(42)
    n = 5000

    players = [
        FPTSDistribution(
            mean=35.0, std=5.0,
            q10=28.0, q50=35.0, q90=42.0,
            samples=rng.normal(35.0, 5.0, size=10000),
            per_stat_means={"pts": 25.0, "reb": 8.0, "ast": 5.0,
                            "fg3m": 2.0, "stl": 1.0, "blk": 0.5, "tov": 2.5},
            has_double_double_p=0.4,
            has_triple_double_p=0.05,
        ),
        FPTSDistribution(
            mean=28.0, std=4.0,
            q10=22.0, q50=28.0, q90=34.0,
            samples=rng.normal(28.0, 4.0, size=10000),
            per_stat_means={"pts": 20.0, "reb": 5.0, "ast": 3.0,
                            "fg3m": 1.0, "stl": 1.0, "blk": 1.0, "tov": 2.0},
            has_double_double_p=0.1,
            has_triple_double_p=0.0,
        ),
    ]

    lineup_fpts = simulate_lineup_fpts(players, n_samples=n)
    assert lineup_fpts.shape == (n,), f"Expected shape ({n},), got {lineup_fpts.shape}"
    # Lineup mean should be close to sum of player means (within 3 sigma of CLT)
    expected_mean = sum(p.mean for p in players)
    lineup_mean = float(np.mean(lineup_fpts))
    std_err = float(np.std(lineup_fpts)) / np.sqrt(n)
    assert abs(lineup_mean - expected_mean) < 4 * std_err, (
        f"Lineup mean {lineup_mean:.2f} too far from expected {expected_mean:.2f}"
    )


# ---------------------------------------------------------------------------
# Test 9 — simulate_lineup_fpts handles empty samples (analytical fallback)
# ---------------------------------------------------------------------------
def test_simulate_lineup_fpts_empty_samples_fallback():
    """Players with empty samples use their mean as analytical contribution."""
    players = [
        FPTSDistribution(
            mean=30.0, std=0.0,
            q10=float("nan"), q50=30.0, q90=float("nan"),
            samples=np.array([], dtype=float),
            per_stat_means={},
        ),
        FPTSDistribution(
            mean=20.0, std=0.0,
            q10=float("nan"), q50=20.0, q90=float("nan"),
            samples=np.array([], dtype=float),
            per_stat_means={},
        ),
    ]
    lineup = simulate_lineup_fpts(players, n_samples=100)
    assert lineup.shape == (100,)
    # All values should be exactly 50.0 (sum of analytical means)
    np.testing.assert_allclose(lineup, 50.0, rtol=1e-9)
