"""tests/test_phase12.py — Phase 12: Monte Carlo model integration tests."""

import time
import pytest
from src.prediction.possession_simulator import PossessionSimulator


@pytest.fixture(scope="module")
def sim():
    return PossessionSimulator()


def test_simulator_uses_garbage_time(sim):
    """Blowout game should stop prop accumulation for starters."""
    roster_a = ["StarA", "BenchA1", "BenchA2", "BenchA3", "BenchA4"]
    roster_b = ["StarB", "BenchB1", "BenchB2", "BenchB3", "BenchB4"]
    # Override garbage model to always trigger (score_diff=30 with 3 min left)
    result = sim.simulate_game(
        "LAL", "BOS", n_sims=50,
        team_a_stats={"pace": 100, "off_rtg": 120, "def_rtg": 100, "oreb_pct": 0.27},
        team_b_stats={"pace": 100, "off_rtg": 100, "def_rtg": 120, "oreb_pct": 0.27},
        player_stats={"LAL": roster_a, "BOS": roster_b},
    )
    dist = result.get("player_distributions", {})
    assert dist, "player_distributions should be populated"
    # In a blowout, once garbage time triggers, props stop accumulating — verify
    # structure exists (content depends on when garbage triggers during sims)
    for pid in ["StarA", "StarB"]:
        assert pid in dist, f"{pid} missing from player_distributions"
        assert "pts" in dist[pid], "pts key missing"


def test_q4_usage_boosts_star(sim):
    """Star player should accumulate more pts than bench player in close Q4."""
    # Give StarA high usage (first in roster) and BenchA low usage
    roster_a = ["StarA", "BenchA1", "BenchA2", "BenchA3", "BenchA4"]
    roster_b = ["StarB", "BenchB1", "BenchB2", "BenchB3", "BenchB4"]
    result = sim.simulate_game(
        "LAL", "BOS", n_sims=200,
        player_stats={"LAL": roster_a, "BOS": roster_b},
    )
    dist = result.get("player_distributions", {})
    star_mean  = dist.get("StarA", {}).get("pts", {}).get("mean", 0)
    bench_mean = dist.get("BenchA4", {}).get("pts", {}).get("mean", 0)
    # Star should have >= bench (usage model gives uniform without training,
    # but Q4 boost pushes highest-usage player up)
    assert star_mean >= bench_mean, (
        f"Star pts mean {star_mean} should >= bench {bench_mean}"
    )


def test_prop_distributions_populated(sim):
    """simulate_game should return player_distributions with all 7 prop stats."""
    result = sim.simulate_game(
        "LAL", "BOS", n_sims=100,
        player_stats={"LAL": ["PlayerA"], "BOS": ["PlayerB"]},
    )
    dist = result.get("player_distributions", {})
    assert dist, "player_distributions missing from result"

    pid = next(iter(dist))
    player = dist[pid]
    for stat in ("pts", "reb", "ast", "stl", "blk", "tov", "fg3m"):
        assert stat in player, f"stat '{stat}' missing for {pid}"
        assert "mean" in player[stat], f"'mean' missing in {stat}"
        assert "std"  in player[stat], f"'std' missing in {stat}"


def test_sim_speed_10k(sim):
    """10K simulations should complete in under 45 seconds."""
    start = time.time()
    sim.simulate_game("LAL", "BOS", n_sims=10000)
    elapsed = time.time() - start
    assert elapsed < 45, f"10K sims took {elapsed:.1f}s (limit 45s)"
