"""Fast regression tests for the possession sim engine (GPU when available).

Guards the role-aware + defense-aware sim: coherence, correct (negative) teammate correlation,
defense suppression, and GPU≈CPU equivalence. Uses small N so the suite stays fast.
"""
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from sim.basketball_sim import TeamModel, simulate_game  # noqa: E402

try:
    from sim.fast_sim import simulate_game_fast
    _HAS = True
except Exception:
    _HAS = False

_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache", "team_system")
pytestmark = pytest.mark.skipif(not os.path.exists(os.path.join(_CACHE, "player_rates.parquet")),
                                reason="team_system cache not built")


def _teams():
    return TeamModel.from_cache("SAS"), TeamModel.from_cache("NYK")


def _engine(h, a, **kw):
    """Prefer the fast GPU engine for speed; fall back to the CPU reference."""
    return simulate_game_fast(h, a, **kw) if _HAS else simulate_game(h, a, **kw)


def test_coherence_and_rho():
    h, a = _teams()
    res = _engine(h, a, n_sims=4000, seed=3, anchor=False, defense=False)
    sas = sum(d["mean"]["pts"] for d in res.players.values() if d["team"] == "SAS")
    assert abs(sas - res.home_total.mean()) < 0.5            # coherence: players sum to team total
    # teammate scoring correlation must be ~0/negative (the old engine bug was +0.645)
    bru = next(d["samples"]["pts"] for d in res.players.values() if "Brunson" in d["name"])
    kat = next(d["samples"]["pts"] for d in res.players.values() if "Towns" in d["name"])
    assert np.corrcoef(bru, kat)[0, 1] < 0.05


@pytest.mark.skipif(not _HAS, reason="torch not available")
def test_fast_matches_reference():
    h, a = _teams()                                          # the one CPU-reference call (ground truth)
    ref = simulate_game(h, a, n_sims=1200, seed=7, anchor=False, defense=False)
    fst = simulate_game_fast(h, a, n_sims=1200, seed=7, anchor=False, defense=False)
    errs = [abs(ref.players[p]["mean"]["pts"] - fst.players[p]["mean"]["pts"])
            for p in ref.players if ref.players[p]["mean"]["pts"] > 5]
    assert np.mean(errs) < 1.0                               # GPU engine ~= CPU reference within MC noise


@pytest.mark.skipif(not _HAS, reason="torch not available")
def test_defense_suppresses_scoring():
    h, a = _teams()                                          # SAS has the tougher defense (Wemby)
    off = simulate_game_fast(h, a, n_sims=4000, seed=11, anchor=True, defense=False)
    on = simulate_game_fast(h, a, n_sims=4000, seed=11, anchor=True, defense=True)
    nyk_drop = off.away_total.mean() - on.away_total.mean()
    sas_drop = off.home_total.mean() - on.home_total.mean()
    # matchup is centered on league-average D, so the test is RELATIVE: the team facing the tougher
    # defense (NYK vs SAS) is suppressed more, by a realistic differential.
    assert nyk_drop > sas_drop
    assert 0.5 < (nyk_drop - sas_drop) < 14


@pytest.mark.skipif(not _HAS, reason="torch not available")
def test_anchor_hits_targets_vs_average_defense():
    # vs a neutralized opponent defense the anchored star should be near his season average
    h, a = _teams()
    res = simulate_game_fast(h, a, n_sims=4000, seed=5, anchor=True, defense=False)
    bru = next(d for d in res.players.values() if "Brunson" in d["name"])
    assert abs(bru["mean"]["pts"] - 26.1) < 1.0
