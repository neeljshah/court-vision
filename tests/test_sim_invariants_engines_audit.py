"""Documented-invariant guards for the possession sim (basketball_sim + fast_sim).

Verifies the invariants recorded in vault/Intelligence/_Simulation_Signals.md by
RUNNING the real sim on NYK/SAS:

  - anchor pins the top scorer ~26.1 pts with defense=False (Brunson anchor)
  - coherence ~0  (sum of per-player pts == team total, per sim)
  - teammate-rho is NEGATIVE (shared-pie routing; doc band -0.06..-0.11)
  - GPU(fast_sim) ~= CPU(basketball_sim) per-player pts (MAE small)
  - dispersion HOLDS the team total and RE-PINS per-player means (marginals exact)

Kept at modest N for CI speed (so tolerances are a touch looser than the doc
headline numbers, which were measured at N=40k). Named *_engines_audit to avoid
any filename collision with concurrently-owned sim test files.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.setdefault("NBA_OFFLINE", "1")

_HAS_CACHE = os.path.exists(os.path.join(ROOT, "data", "cache", "team_system", "player_rates.parquet"))
pytestmark = pytest.mark.skipif(not _HAS_CACHE, reason="team_system sim cache not present")

N = 4000
SEED = 2026


@pytest.fixture(scope="module")
def teams():
    from sim.basketball_sim import TeamModel
    return TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")


@pytest.fixture(scope="module")
def cpu_res(teams):
    from sim.basketball_sim import simulate_game
    home, away = teams
    return simulate_game(home, away, n_sims=N, seed=SEED, anchor=True, defense=True,
                         context={"neutral_site": False})


def test_anchor_pins_top_scorer_defense_false(teams):
    from sim.basketball_sim import simulate_game
    home, away = teams
    res = simulate_game(home, away, n_sims=N, seed=SEED, anchor=True, defense=False,
                        context={"neutral_site": False})
    top = max((res.players[p]["mean"]["pts"] for p in res.players if res.players[p]["team"] == "NYK"))
    # Brunson anchor ~26.1 (defense=False); allow a small MC band.
    assert top == pytest.approx(26.1, abs=1.2), f"top NYK scorer {top:.2f} != ~26.1"


def test_coherence_sum_players_equals_team_total(cpu_res):
    res = cpu_res
    hp = [p for p in res.players if res.players[p]["team"] == "NYK"]
    player_sum = np.sum([res.players[p]["samples"]["pts"] for p in hp], axis=0)
    coh = np.abs(player_sum - res.home_total).mean()
    assert coh < 1e-6, f"coherence broken: mean|sum-total|={coh}"


def test_teammate_rho_is_negative(cpu_res):
    import itertools
    res = cpu_res
    hp = sorted((p for p in res.players if res.players[p]["team"] == "NYK"),
                key=lambda p: -res.players[p]["mean"]["pts"])[:6]
    rhos = []
    for a, b in itertools.combinations(hp, 2):
        r = np.corrcoef(res.players[a]["samples"]["pts"], res.players[b]["samples"]["pts"])[0, 1]
        if np.isfinite(r):
            rhos.append(r)
    mean_rho = float(np.mean(rhos))
    assert mean_rho < 0, f"teammate-rho should be NEGATIVE (shared-pie), got {mean_rho:+.3f}"
    # doc band is -0.06..-0.11; allow a wider envelope at small N.
    assert -0.20 < mean_rho < -0.01, f"teammate-rho {mean_rho:+.3f} outside sane negative band"


def test_gpu_matches_cpu_per_player_pts(teams, cpu_res):
    from sim.fast_sim import simulate_game_fast
    home, away = teams
    fast = simulate_game_fast(home, away, n_sims=N, seed=SEED, anchor=True, defense=True,
                              context={"neutral_site": False})
    common = [p for p in cpu_res.players if p in fast.players]
    assert common, "no common players between CPU and fast sims"
    mae = float(np.mean([abs(cpu_res.players[p]["mean"]["pts"] - fast.players[p]["mean"]["pts"])
                         for p in common]))
    assert mae < 0.5, f"GPU~CPU per-player pts MAE {mae:.3f} too large"


def test_dispersion_holds_total_and_repins_means(teams):
    from sim.basketball_sim import simulate_game
    home, away = teams
    on = simulate_game(home, away, n_sims=N, seed=SEED, anchor=True, defense=True,
                       dispersion=True, context={"neutral_site": False})
    off = simulate_game(home, away, n_sims=N, seed=SEED, anchor=True, defense=True,
                        dispersion=False, context={"neutral_site": False})
    common = [p for p in on.players if p in off.players]
    # per-player means re-pinned (marginals exact)
    mean_diff = float(np.mean([abs(on.players[p]["mean"]["pts"] - off.players[p]["mean"]["pts"])
                               for p in common]))
    assert mean_diff < 0.05, f"dispersion changed per-player means by {mean_diff:.4f} (should re-pin)"
    # team total mean held
    assert abs(on.home_total.mean() - off.home_total.mean()) < 0.5
    # dispersion ON must WIDEN per-player spread
    sd_on = np.mean([on.players[p]["samples"]["pts"].std() for p in common])
    sd_off = np.mean([off.players[p]["samples"]["pts"].std() for p in common])
    assert sd_on > sd_off, f"dispersion ON ({sd_on:.3f}) should exceed OFF ({sd_off:.3f})"
