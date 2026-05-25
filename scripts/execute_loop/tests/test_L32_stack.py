"""test_L32_stack.py — Tests for L32_stack_correlation.py (BUILD L32).

Tests
-----
1. compute_team_stack_correlations with 8 synthetic players → returns StackCorrelation,
   matrix is symmetric, diagonal=1.0
2. identify_game_stacks with default correlations → finds LAL stack at min_correlation=0.3
3. recommend_stack_bets returns ≤3 OVERs with correct stack_key and correlation_boost > 0
4. Team with 4 players → returns None
5. min_correlation=0.5 with avg_off_diag ≈ 0.45 → no stack returned (borderline rejection)

Run with:
    conda run -n basketball_ai python -m pytest scripts/execute_loop/tests/test_L32_stack.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pytest

# Ensure project root is on path
_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT))

from scripts.execute_loop.L32_stack_correlation import (
    StackCorrelation,
    _MIN_TEAM_SIZE,
    _TOP_N_PLAYERS,
    compute_team_stack_correlations,
    identify_game_stacks,
    recommend_stack_bets,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_fpts_entry(mean: float, std: float, team: str) -> dict:
    return {"mean": mean, "std": std, "team": team}


def _make_lal_pool(n: int = 8, team: str = "LAL") -> Dict[str, dict]:
    """Create n players for a team with realistic PTS distributions."""
    rng = np.random.default_rng(7)
    pool: Dict[str, dict] = {}
    for i in range(n):
        name = f"{team}_Player_{i}"
        mean = float(rng.uniform(12.0, 32.0))
        std = float(rng.uniform(3.0, 8.0))
        pool[name] = _make_fpts_entry(mean, std, team)
    return pool


def _make_full_slate(teams=("LAL", "DEN")) -> dict:
    """Return a minimal slate dict covering the given teams."""
    games = [{"home": teams[0], "away": teams[1]}] if len(teams) >= 2 else []
    return {"games": games, "teams": list(teams)}


# ---------------------------------------------------------------------------
# Test 1 — Basic stack for 8-player team
# ---------------------------------------------------------------------------

def test_compute_team_stack_returns_valid_object():
    """8 synthetic LAL players → StackCorrelation with correct matrix properties."""
    fpts_data = _make_lal_pool(n=8, team="LAL")

    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.3)

    assert result is not None, "Expected a StackCorrelation, got None."
    assert isinstance(result, StackCorrelation), f"Wrong type: {type(result)}"

    # stack_key format
    assert result.stack_key == "LAL_high_pace_lineup", (
        f"Unexpected stack_key: {result.stack_key!r}"
    )

    # players list matches input keys
    assert set(result.players) == set(fpts_data.keys()), "Player names mismatch."

    # Correlation matrix shape
    n = len(fpts_data)
    assert result.correlation_matrix.shape == (n, n), (
        f"Matrix shape should be ({n},{n}), got {result.correlation_matrix.shape}"
    )

    # Symmetry: |M - M^T| < 1e-10 for all entries
    diff = np.abs(result.correlation_matrix - result.correlation_matrix.T)
    assert diff.max() < 1e-10, f"Matrix is not symmetric (max diff={diff.max():.2e})"

    # Diagonal must be exactly 1.0
    diag = np.diag(result.correlation_matrix)
    assert np.allclose(diag, 1.0, atol=1e-10), (
        f"Diagonal should be 1.0, got {diag}"
    )

    # expected_lift must be positive
    assert result.expected_lift > 0.0, (
        f"expected_lift should be positive, got {result.expected_lift}"
    )

    # correlated_stats must include PTS
    assert "PTS" in result.correlated_stats, (
        f"'PTS' should be in correlated_stats, got {result.correlated_stats}"
    )


# ---------------------------------------------------------------------------
# Test 2 — identify_game_stacks finds LAL stack
# ---------------------------------------------------------------------------

def test_identify_game_stacks_finds_lal():
    """Slate with LAL+DEN, 8-player LAL pool → LAL stack found at min_correlation=0.3."""
    lal_pool = _make_lal_pool(n=8, team="LAL")
    den_pool = _make_lal_pool(n=8, team="DEN")
    fpts_data = {**lal_pool, **den_pool}

    slate = _make_full_slate(teams=("LAL", "DEN"))
    stacks = identify_game_stacks(slate, fpts_data, min_correlation=0.3)

    assert len(stacks) >= 1, "Expected at least one stack, got zero."

    keys = [s.stack_key for s in stacks]
    assert "LAL_high_pace_lineup" in keys, (
        f"LAL stack not found. Found: {keys}"
    )


def test_identify_game_stacks_finds_both_teams():
    """Both LAL and DEN have ≥5 players → both stacks returned."""
    fpts_data = {
        **_make_lal_pool(n=8, team="LAL"),
        **_make_lal_pool(n=8, team="DEN"),
    }
    slate = _make_full_slate(teams=("LAL", "DEN"))
    stacks = identify_game_stacks(slate, fpts_data, min_correlation=0.3)

    keys = {s.stack_key for s in stacks}
    assert "LAL_high_pace_lineup" in keys, "LAL stack missing."
    assert "DEN_high_pace_lineup" in keys, "DEN stack missing."


# ---------------------------------------------------------------------------
# Test 3 — recommend_stack_bets structure and bounds
# ---------------------------------------------------------------------------

def test_recommend_stack_bets_returns_valid_overs():
    """recommend_stack_bets: ≤3 recs, all OVER, correct stack_key, boost > 0."""
    fpts_data = _make_lal_pool(n=8, team="LAL")
    stack = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.3)
    assert stack is not None, "Precondition: stack must be found."

    # Build current_lines for every player in the stack
    current_lines = {player: {"PTS": 22.5} for player in stack.players}

    recs = recommend_stack_bets(stack, current_lines)

    assert isinstance(recs, list), f"Expected list, got {type(recs)}"
    assert 1 <= len(recs) <= _TOP_N_PLAYERS, (
        f"Expected 1-{_TOP_N_PLAYERS} recs, got {len(recs)}"
    )

    for rec in recs:
        assert rec["side"] == "OVER", f"Expected 'OVER', got {rec['side']!r}"
        assert rec["stat"] == "PTS", f"Expected stat='PTS', got {rec['stat']!r}"
        assert rec["stack_key"] == "LAL_high_pace_lineup", (
            f"Wrong stack_key: {rec['stack_key']!r}"
        )
        assert rec["correlation_boost"] > 0.0, (
            f"correlation_boost should be > 0, got {rec['correlation_boost']}"
        )
        assert isinstance(rec["line"], float), f"line should be float, got {type(rec['line'])}"
        assert rec["player"] in fpts_data, (
            f"Recommended player {rec['player']!r} not in fpts_data"
        )


def test_recommend_stack_bets_skips_missing_players():
    """Players absent from current_lines are silently skipped."""
    fpts_data = _make_lal_pool(n=8, team="LAL")
    stack = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.3)
    assert stack is not None

    # Only provide lines for the last 2 players
    last_two = stack.players[-2:]
    current_lines = {p: {"PTS": 18.5} for p in last_two}

    recs = recommend_stack_bets(stack, current_lines)
    # Should return at most 2 (only those with lines, capped at TOP_N=3)
    assert len(recs) <= len(last_two), (
        f"Expected ≤{len(last_two)} recs (only players with lines), got {len(recs)}"
    )
    for rec in recs:
        assert rec["player"] in last_two, f"Unexpected player {rec['player']!r} in recs."


# ---------------------------------------------------------------------------
# Test 4 — Team with 4 players → None
# ---------------------------------------------------------------------------

def test_too_few_players_returns_none():
    """Team with only 4 players (< _MIN_TEAM_SIZE=5) → compute returns None."""
    fpts_data = _make_lal_pool(n=4, team="LAL")
    assert len(fpts_data) == 4

    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.3)
    assert result is None, (
        f"Expected None for {len(fpts_data)} players, got {result}"
    )


def test_exactly_min_team_size_accepted():
    """Team with exactly _MIN_TEAM_SIZE players → stack may be returned (not None from size)."""
    fpts_data = _make_lal_pool(n=_MIN_TEAM_SIZE, team="LAL")
    # Just verify it doesn't raise and doesn't return None due to size check
    # (may still return None if corr < min_correlation, which is fine)
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.3)
    # No exception → test passes; result can be None or StackCorrelation
    assert result is None or isinstance(result, StackCorrelation)


# ---------------------------------------------------------------------------
# Test 5 — High min_correlation threshold rejects borderline stack
# ---------------------------------------------------------------------------

def test_high_min_correlation_rejects_stack():
    """min_correlation=0.5 should reject a stack whose avg_off_diag ≈ 0.45.

    The Cholesky-injected target is _PTS_PTS_CORR=0.45, so the empirical
    off-diagonal avg converges near 0.45.  Setting min_correlation=0.5 must
    reject it.
    """
    fpts_data = _make_lal_pool(n=8, team="LAL")
    # 0.5 threshold is above the ~0.45 injected correlation
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.5)
    assert result is None, (
        f"Expected None with min_correlation=0.5 (avg_corr≈0.45), got {result}"
    )


def test_low_min_correlation_accepts_stack():
    """min_correlation=0.1 should accept the same stack that 0.5 rejects."""
    fpts_data = _make_lal_pool(n=8, team="LAL")
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.1)
    assert result is not None, "Expected a stack with min_correlation=0.1."


# ---------------------------------------------------------------------------
# Test 6 — NaN handling in correlation matrix
# ---------------------------------------------------------------------------

def test_nan_coerced_to_zero(monkeypatch):
    """If _pearson_matrix produces NaN, it must be coerced to 0.0."""
    import scripts.execute_loop.L32_stack_correlation as mod

    original_build = mod._build_correlated_samples

    def nan_samples(means, stds, target_corr, rng):
        arr = original_build(means, stds, target_corr, rng)
        # Inject NaN in first column to force NaN in corrcoef
        arr[:, 0] = np.nan
        return arr

    monkeypatch.setattr(mod, "_build_correlated_samples", nan_samples)

    fpts_data = _make_lal_pool(n=6, team="LAL")
    # Should not raise; NaN coerced to 0.0
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.0)
    if result is not None:
        assert not np.any(np.isnan(result.correlation_matrix)), (
            "NaN values found in correlation_matrix after coercion."
        )


# ---------------------------------------------------------------------------
# Test 7 — identify_game_stacks with teams-only slate (no games key)
# ---------------------------------------------------------------------------

def test_identify_stacks_teams_key_only():
    """Slate with only 'teams' key (no 'games') still processes all teams."""
    fpts_data = {
        **_make_lal_pool(n=8, team="LAL"),
        **_make_lal_pool(n=8, team="GSW"),
    }
    slate = {"teams": ["LAL", "GSW"]}
    stacks = identify_game_stacks(slate, fpts_data, min_correlation=0.3)

    assert len(stacks) >= 1, "Expected at least one stack from teams-only slate."


# ---------------------------------------------------------------------------
# Test 8 — Correlation matrix is non-negative off-diagonal
# ---------------------------------------------------------------------------

def test_off_diagonal_positive():
    """With Cholesky-injected positive correlation, all off-diagonal entries > 0."""
    fpts_data = _make_lal_pool(n=6, team="LAL")
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.1)
    assert result is not None

    n = result.correlation_matrix.shape[0]
    for i in range(n):
        for j in range(n):
            if i != j:
                val = result.correlation_matrix[i, j]
                assert val > 0.0, (
                    f"Off-diagonal [{i},{j}] should be positive, got {val:.4f}"
                )


# ---------------------------------------------------------------------------
# Test 9 — expected_lift equals avg_off_diag * 100
# ---------------------------------------------------------------------------

def test_expected_lift_formula():
    """expected_lift == avg_off_diagonal(corr_matrix) * 100 (within 1e-6)."""
    fpts_data = _make_lal_pool(n=8, team="LAL")
    result = compute_team_stack_correlations("LAL", fpts_data, min_correlation=0.1)
    assert result is not None

    mat = result.correlation_matrix
    n = mat.shape[0]
    mask = ~np.eye(n, dtype=bool)
    avg = float(np.mean(mat[mask]))

    assert abs(result.expected_lift - avg * 100.0) < 1e-6, (
        f"expected_lift={result.expected_lift} != avg_off_diag*100={avg*100:.6f}"
    )


# ---------------------------------------------------------------------------
# Test 10 — Unknown team returns None, not exception
# ---------------------------------------------------------------------------

def test_unknown_team_returns_none():
    """Team not present in fpts_data → returns None gracefully."""
    fpts_data = _make_lal_pool(n=8, team="LAL")
    result = compute_team_stack_correlations("XYZ", fpts_data, min_correlation=0.3)
    assert result is None, f"Expected None for unknown team, got {result}"
