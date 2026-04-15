"""Benchmark: 10K possession simulations must complete in < 30s."""
import time
import pytest
from src.prediction.possession_simulator import PossessionSimulator


def test_10k_sims_under_30s() -> None:
    sim = PossessionSimulator()
    start = time.perf_counter()
    result = sim.simulate_game("LAL", "GSW", n_sims=10_000)
    elapsed = time.perf_counter() - start

    assert "win_probability" in result
    assert elapsed < 30.0, f"10K sims took {elapsed:.2f}s (limit 30s)"
    print(f"\n[benchmark] 10K sims: {elapsed:.2f}s")
