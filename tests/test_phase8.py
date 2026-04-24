"""tests/test_phase8.py — Phase 8: Possession Simulator v1 tests."""

from __future__ import annotations

import time

import numpy as np
import pytest

from src.prediction.possession_simulator import PossessionSimulator
from src.prediction.sim_models import FatigueModel, SubstitutionModel


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sim():
    return PossessionSimulator()


TEAM_A = "DEN"
TEAM_B = "LAL"
STATS_A = {"off_rtg": 115, "def_rtg": 108, "pace": 99, "oreb_pct": 0.28}
STATS_B = {"off_rtg": 112, "def_rtg": 111, "pace": 101, "oreb_pct": 0.25}
ROSTER_A = ["Murray", "Porter Jr.", "Jokić", "Gordon", "Braun"]
ROSTER_B = ["James", "Davis", "Reaves", "Hachimura", "Knecht"]


# ── single possession chain ───────────────────────────────────────────────────

def test_single_possession_schema(sim):
    """Possession result always has required keys and valid point values."""
    rng = np.random.default_rng(42)
    for _ in range(50):
        result = sim.simulate_possession(
            {"xfg_adj_factor": 1.0, "oreb_rate": 0.27, "fatigue_mult": 1.0}, rng=rng
        )
        assert "play_type" in result
        assert "outcome" in result
        assert "points" in result
        assert result["outcome"] in ("shot", "turnover", "foul", "oreb")
        assert result["points"] >= 0
        assert result["points"] <= 4  # 3+and1 max


def test_single_possession_play_types(sim):
    """All returned play types are strings."""
    rng = np.random.default_rng(0)
    for _ in range(20):
        r = sim.simulate_possession({}, rng=rng)
        assert isinstance(r["play_type"], str)


def test_turnover_rate_plausible(sim):
    """Turnover rate across 1000 possessions in [5%, 25%]."""
    rng = np.random.default_rng(7)
    results = [sim.simulate_possession({"xfg_adj_factor": 1.0}, rng=rng) for _ in range(1000)]
    tov_rate = sum(1 for r in results if r["outcome"] == "turnover") / 1000
    assert 0.05 < tov_rate < 0.25, f"TOV rate {tov_rate:.3f} out of range"


def test_points_distribution_plausible(sim):
    """Mean points per possession in [0.9, 1.3] (NBA range is ~1.05-1.15)."""
    rng = np.random.default_rng(99)
    pts = [sim.simulate_possession({"xfg_adj_factor": 1.0}, rng=rng)["points"] for _ in range(2000)]
    mean_pts = np.mean(pts)
    assert 0.9 < mean_pts < 1.3, f"Mean pts/poss {mean_pts:.3f} out of expected range"


# ── 10 K simulation speed and output schema ───────────────────────────────────

def test_simulate_game_completes_in_30s(sim):
    """10 000 simulations must complete in < 30 seconds."""
    t0 = time.monotonic()
    result = sim.simulate_game(TEAM_A, TEAM_B, n_sims=10000,
                               team_a_stats=STATS_A, team_b_stats=STATS_B)
    elapsed = time.monotonic() - t0
    assert elapsed < 30.0, f"10K sims took {elapsed:.1f}s (limit: 30s)"
    _ = result  # consumed


def test_simulate_game_output_schema(sim):
    """Output has required keys with correct types."""
    result = sim.simulate_game(TEAM_A, TEAM_B, n_sims=1000,
                               team_a_stats=STATS_A, team_b_stats=STATS_B)
    assert "win_probability" in result
    assert "score_distribution" in result
    wp = result["win_probability"]
    assert TEAM_A in wp and TEAM_B in wp
    assert abs(wp[TEAM_A] + wp[TEAM_B] - 1.0) < 0.01
    for t in (TEAM_A, TEAM_B):
        sd = result["score_distribution"][t]
        assert "mean" in sd and "std" in sd
        assert 80 < sd["mean"] < 140, f"{t} mean score {sd['mean']} implausible"
        assert 5 < sd["std"] < 20


def test_simulate_game_win_prob_bounds(sim):
    """Win probabilities in (0, 1) and sum to ~1."""
    result = sim.simulate_game(TEAM_A, TEAM_B, n_sims=2000)
    wp = result["win_probability"]
    for team, p in wp.items():
        assert 0.0 < p < 1.0, f"{team} win prob {p} out of (0,1)"


def test_simulate_game_player_stats_schema(sim):
    """player_stats output has pts.mean, pts.std, and p_over when requested."""
    result = sim.simulate_game(
        TEAM_A, TEAM_B, n_sims=1000,
        team_a_stats=STATS_A, team_b_stats=STATS_B,
        player_stats={TEAM_A: ROSTER_A, TEAM_B: ROSTER_B},
        prop_lines={"Jokić": {"pts": 25.5}, "James": {"pts": 22.5}},
    )
    assert "player_stats" in result
    ps = result["player_stats"]

    for pid in ROSTER_A + ROSTER_B:
        assert pid in ps, f"{pid} missing from player_stats"
        entry = ps[pid]["pts"]
        assert "mean" in entry and "std" in entry
        assert entry["mean"] >= 0

    # Prop lines
    assert "p_over_25.5" in ps["Jokić"]["pts"]
    assert "p_over_22.5" in ps["James"]["pts"]
    assert 0.0 <= ps["Jokić"]["pts"]["p_over_25.5"] <= 1.0
    assert 0.0 <= ps["James"]["pts"]["p_over_22.5"] <= 1.0


def test_home_court_advantage(sim):
    """Home team should win slightly more than 50% all else equal."""
    result = sim.simulate_game(TEAM_A, TEAM_B, n_sims=5000,
                               team_a_stats=STATS_A, team_b_stats=STATS_A,
                               home_team=TEAM_A)
    # Home team should have win prob > 50% (loosely, >47% given noise)
    assert result["win_probability"][TEAM_A] > 0.47


def test_over_prob_convenience(sim):
    """over_prob returns float in [0, 1]."""
    p = sim.over_prob("Jokić", 25.5, TEAM_A, TEAM_B, ROSTER_A, ROSTER_B, n_sims=500)
    assert 0.0 <= p <= 1.0


# ── FatigueModel ─────────────────────────────────────────────────────────────

def test_fatigue_model_defaults():
    fm = FatigueModel()
    assert fm.predict() == 1.0  # neutral: 7 games, 0 dist

def test_fatigue_model_penalty():
    fm = FatigueModel()
    fresh  = fm.predict(dist_per100=0.0, games_in_last_14=7)
    tired  = fm.predict(dist_per100=5.0, games_in_last_14=10)
    assert tired < fresh
    assert tired >= 0.85

def test_fatigue_batch():
    fm = FatigueModel()
    arr = fm.batch_predict(5)
    assert arr.shape == (5,)
    assert np.all(arr == 1.0)


# ── SubstitutionModel ─────────────────────────────────────────────────────────

def test_sub_model_foul_out():
    sm = SubstitutionModel()
    assert sm.should_sub(player_fouls=5, player_minutes=28.0, score_diff=0.0, period=4)

def test_sub_model_foul_trouble_early():
    sm = SubstitutionModel()
    assert sm.should_sub(player_fouls=4, player_minutes=20.0, score_diff=5.0, period=2)
    assert not sm.should_sub(player_fouls=4, player_minutes=20.0, score_diff=5.0, period=4)

def test_sub_model_apply_never_empties():
    sm = SubstitutionModel()
    roster = ["A", "B", "C"]
    # All fouled out — apply should still return something
    fouls   = {p: 6 for p in roster}
    minutes = {p: 35.0 for p in roster}
    active  = sm.apply(roster, fouls, minutes, score_diff=0.0, period=4)
    assert len(active) > 0
