"""Unit tests for src/sim/game_simulator.py

Tests:
  1. Determinism with same seed
  2. Coherence constraint: sum(player pts) close to team total
  3. AST mean preservation
  4. Leak-free prior usage (no future info)
  5. Result shape / stat coverage
  6. Edge cases: single player per team, zero prior
"""
from __future__ import annotations

import numpy as np
import pytest

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sim.game_simulator import (
    simulate_game, PlayerPrior, GameContext, GameSimResult, STATS
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_prior(pid: int, team: str, pts: float = 20.0, reb: float = 5.0,
                ast: float = 3.0, fg3m: float = 1.5, stl: float = 0.8,
                blk: float = 0.4, tov: float = 1.5,
                proj_min: float = 32.0, min_std: float = 4.0) -> PlayerPrior:
    return PlayerPrior(
        player_id=pid,
        team=team,
        q50={"pts": pts, "reb": reb, "ast": ast,
             "fg3m": fg3m, "stl": stl, "blk": blk, "tov": tov},
        proj_min=proj_min,
        min_std=min_std,
    )


def _make_context(
    home_team: str = "BOS", away_team: str = "NYK",
    ppp_home: float = 1.12, ppp_away: float = 1.10,
    pace_home: float = 99.0, pace_away: float = 97.0,
) -> GameContext:
    return GameContext(
        game_date="2025-01-15",
        home_team=home_team,
        away_team=away_team,
        team_priors={
            "home_ppp": ppp_home, "away_ppp": ppp_away,
            "home_pace_per48": pace_home, "away_pace_per48": pace_away,
        },
    )


def _make_five_players(team: str, start_id: int = 1) -> list:
    base_stats = [
        (24.0, 4.0, 5.0, 0.5, 0.8, 0.2, 2.0, 30.0),
        (20.0, 5.0, 3.0, 1.5, 1.0, 0.5, 1.5, 32.0),
        (15.0, 6.0, 2.0, 1.0, 0.8, 1.2, 1.0, 28.0),
        (12.0, 8.0, 4.0, 0.8, 0.5, 1.0, 1.2, 25.0),
        (8.0, 3.0, 2.0, 0.5, 0.7, 0.4, 0.8, 20.0),
    ]
    players = []
    for i, (pts, reb, ast, fg3m, stl, blk, tov, mn) in enumerate(base_stats):
        players.append(_make_prior(
            pid=start_id + i, team=team,
            pts=pts, reb=reb, ast=ast, fg3m=fg3m,
            stl=stl, blk=blk, tov=tov, proj_min=mn,
        ))
    return players


# ---------------------------------------------------------------------------
# Test 1: Determinism with same seed
# ---------------------------------------------------------------------------

def test_determinism():
    """Identical seeds produce identical results."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()

    result_a = simulate_game(priors, ctx, n_sims=100, seed=7)
    result_b = simulate_game(priors, ctx, n_sims=100, seed=7)

    for ps_a, ps_b in zip(result_a.players, result_b.players):
        assert ps_a.player_id == ps_b.player_id
        np.testing.assert_array_equal(ps_a.samples, ps_b.samples)
        for s in STATS:
            assert abs(ps_a.sim_mean[s] - ps_b.sim_mean[s]) < 1e-9


def test_different_seeds_differ():
    """Different seeds produce different samples."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result_a = simulate_game(priors, ctx, n_sims=100, seed=1)
    result_b = simulate_game(priors, ctx, n_sims=100, seed=2)
    # At least one player should differ
    diffs = sum(
        not np.allclose(ps_a.samples, ps_b.samples)
        for ps_a, ps_b in zip(result_a.players, result_b.players)
    )
    assert diffs > 0


# ---------------------------------------------------------------------------
# Test 2: Coherence constraint
# ---------------------------------------------------------------------------

def test_coherence_pts_sum_close_to_team_total():
    """Sum of player sim_mean pts should be within ~10 pts of simulated team total mean."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=2000, seed=42)

    home_team_mean = float(result.home_team_total_samples.mean())
    home_players = [ps for ps in result.players if ps.team == "BOS"]
    sum_home_pts = sum(ps.sim_mean["pts"] for ps in home_players)

    # Should be within 10 pts (coherence target; soft renorm allows some drift)
    assert abs(sum_home_pts - home_team_mean) < 10.0, (
        f"Home coherence off: sum_player_pts={sum_home_pts:.1f} "
        f"vs team_total_mean={home_team_mean:.1f}"
    )

    away_team_mean = float(result.away_team_total_samples.mean())
    away_players = [ps for ps in result.players if ps.team == "NYK"]
    sum_away_pts = sum(ps.sim_mean["pts"] for ps in away_players)
    assert abs(sum_away_pts - away_team_mean) < 10.0


def test_coherence_per_sim():
    """Per-sim: sum of player pts samples should be reasonably close to team total samples."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=500, seed=42)

    home_players = [ps for ps in result.players if ps.team == "BOS"]
    # Sum player pts samples per sim (n_sims,)
    sum_player_pts = sum(ps.samples[:, STATS.index("pts")] for ps in home_players)
    team_totals = result.home_team_total_samples
    per_sim_mae = float(np.abs(sum_player_pts - team_totals).mean())
    # With the soft renorm, mean absolute deviation should be < 15 pts on average
    assert per_sim_mae < 15.0, f"Per-sim coherence MAE too high: {per_sim_mae:.2f}"


# ---------------------------------------------------------------------------
# Test 3: AST mean preservation
# ---------------------------------------------------------------------------

def test_ast_mean_preserved():
    """sim_mean[ast] should be within tolerance of prior_q50_ast for each player."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=2000, seed=42)

    prior_map = {p.player_id: p for p in priors}
    for ps in result.players:
        target_ast = prior_map[ps.player_id].get("ast")
        sim_ast_mean = ps.sim_mean["ast"]
        # After mean-shift correction, should be within 0.5 AST of target
        assert abs(sim_ast_mean - target_ast) < 0.5, (
            f"AST mean not preserved for player {ps.player_id}: "
            f"prior={target_ast:.2f} sim_mean={sim_ast_mean:.2f}"
        )


def test_ast_samples_non_negative():
    """All AST samples should be non-negative."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=200, seed=0)
    for ps in result.players:
        ast_samples = ps.get_samples("ast")
        assert (ast_samples >= 0).all(), f"Negative AST samples for player {ps.player_id}"


# ---------------------------------------------------------------------------
# Test 4: Leak-free prior usage
# ---------------------------------------------------------------------------

def test_no_future_info_in_game_context():
    """GameContext with team_priors=None falls back to league means (no error)."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = GameContext(
        game_date="2025-01-15",
        home_team="BOS",
        away_team="NYK",
        team_priors=None,   # Should fall back to league means
    )
    result = simulate_game(priors, ctx, n_sims=200, seed=42)
    assert result.n_sims == 200
    # Should still produce plausible team totals (league mean ~110 pts)
    assert 80 < float(result.home_team_total_samples.mean()) < 140
    assert 80 < float(result.away_team_total_samples.mean()) < 140


def test_team_priors_affect_output():
    """Team priors should shift the team totals meaningfully vs league defaults."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx_high = _make_context(ppp_home=1.25, pace_home=105.0)  # high-scoring team
    ctx_low = _make_context(ppp_home=0.98, pace_home=92.0)    # low-scoring team

    result_high = simulate_game(priors, ctx_high, n_sims=1000, seed=42)
    result_low = simulate_game(priors, ctx_low, n_sims=1000, seed=42)

    mean_high = float(result_high.home_team_total_samples.mean())
    mean_low = float(result_low.home_team_total_samples.mean())
    assert mean_high > mean_low + 5.0, (
        f"High-ppp team should score more: high={mean_high:.1f} low={mean_low:.1f}"
    )


# ---------------------------------------------------------------------------
# Test 5: Result shape / stat coverage
# ---------------------------------------------------------------------------

def test_result_has_all_players_and_stats():
    """GameSimResult contains all input players and all 7 stats."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=100, seed=0)

    assert len(result.players) == len(priors)
    for ps in result.players:
        for s in STATS:
            assert s in ps.sim_mean
            assert s in ps.q10
            assert s in ps.q50
            assert s in ps.q90
            # samples shape
            assert ps.samples.shape == (100, len(STATS))


def test_quantile_ordering():
    """q10 <= q50 <= q90 for all stats and all players."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=500, seed=42)
    for ps in result.players:
        for s in STATS:
            q10 = ps.q10[s]; q50 = ps.q50[s]; q90 = ps.q90[s]
            assert q10 <= q50 + 1e-6, f"{ps.player_id} {s}: q10={q10} > q50={q50}"
            assert q50 <= q90 + 1e-6, f"{ps.player_id} {s}: q50={q50} > q90={q90}"


def test_non_negative_samples():
    """All stat samples should be non-negative."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=200, seed=0)
    for ps in result.players:
        for si, s in enumerate(STATS):
            vals = ps.samples[:, si]
            assert (vals >= 0).all(), f"Negative values for {ps.player_id} {s}"


def test_home_win_prob_between_0_and_1():
    """home_win_prob must be in [0, 1]."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=500, seed=42)
    assert 0.0 <= result.home_win_prob <= 1.0


# ---------------------------------------------------------------------------
# Test 6: Edge cases
# ---------------------------------------------------------------------------

def test_single_player_per_team():
    """Works with only 1 player per team (fallback path)."""
    priors = [
        _make_prior(1, "BOS", pts=30.0, proj_min=40.0),
        _make_prior(2, "NYK", pts=28.0, proj_min=40.0),
    ]
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=200, seed=0)
    assert len(result.players) == 2


def test_zero_ast_prior():
    """Player with zero AST prior should have near-zero sim AST mean."""
    priors = _make_five_players("BOS", 1)
    priors[0].q50["ast"] = 0.0
    priors += _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=500, seed=42)
    ps = result.player(1)
    assert ps is not None
    # AST mean should be near 0 (within 1.0 after shift correction)
    assert ps.sim_mean["ast"] < 1.0, f"Expected near-zero AST, got {ps.sim_mean['ast']:.2f}"


def test_correlated_pts_fg3m():
    """PTS-FG3M correlation in samples should be positive (hardcoded rho=0.55)."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=2000, seed=42)
    # Check top scorer
    ps = result.player(1)
    pts = ps.get_samples("pts")
    fg3m = ps.get_samples("fg3m")
    rho = float(np.corrcoef(pts, fg3m)[0, 1])
    assert rho > 0.0, f"PTS-FG3M should be positively correlated, got rho={rho:.3f}"


def test_player_lookup_by_id():
    """GameSimResult.player() returns correct PlayerSimStats by ID."""
    priors = _make_five_players("BOS", 1) + _make_five_players("NYK", 10)
    ctx = _make_context()
    result = simulate_game(priors, ctx, n_sims=100, seed=0)
    for p in priors:
        ps = result.player(p.player_id)
        assert ps is not None
        assert ps.player_id == p.player_id

    # Non-existent ID returns None
    assert result.player(99999) is None
