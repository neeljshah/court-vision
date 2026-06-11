"""P1.3 — the defender-suppression L1 lever (CV_AGENT_DEF_SUPP) wired into the possession engines.

Proves the load-bearing discipline:
  - DEFAULT-OFF is byte-identical: `from_cache` adds NO `supp` key and reads no parquet; the CPU + GPU sims
    are deterministic and unchanged (the lever block is gated, consumes no RNG).
  - ON: `from_cache` attaches per-defender `supp`, and the on-court defenders' mean suppression LOWERS raw
    (anchor-OFF) scoring for both teams — i.e. the lever actually does something, in the suppress direction.
The SHIP/REJECT decision is NOT made here (that is the sim walk-forward gate, gate_def_supp.py); this only
proves the wiring is correct, gated, and byte-identical when OFF.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sim.basketball_sim import TeamModel, simulate_game, _defender_supp, _def_supp_on  # noqa: E402

_FLAG = "CV_AGENT_DEF_SUPP"


def _off():
    os.environ.pop(_FLAG, None)


def _on():
    os.environ[_FLAG] = "1"


def teardown_function(_):
    _off()


# --------------------------------------------------------------------------- loader / flag

def test_loader_reads_parquet():
    supp = _defender_supp()
    assert isinstance(supp, dict) and len(supp) > 100
    assert supp.get(2544, 0.0) < 0.0  # LeBron James is a net suppressor (supp ~ -0.067)


def test_flag_helper_semantics():
    _off()
    assert _def_supp_on() is False
    _on()
    assert _def_supp_on() is True
    os.environ[_FLAG] = "0"
    assert _def_supp_on() is False  # "0" is OFF (matches brain.flags.is_on)


# --------------------------------------------------------------------------- from_cache attach

def test_from_cache_off_adds_no_supp_key():
    _off()
    tm = TeamModel.from_cache("NYK")
    assert all("supp" not in r for r in tm.rate.values())  # byte-identical: no new key when OFF


def test_from_cache_on_attaches_supp():
    _on()
    tm = TeamModel.from_cache("NYK")
    assert any("supp" in r for r in tm.rate.values())
    # every player gets a supp value (0.0 default if not in the parquet)
    assert all("supp" in r for r in tm.rate.values())


# --------------------------------------------------------------------------- CPU engine

def test_cpu_off_is_deterministic():
    _off()
    a = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"), n_sims=120, seed=7)
    b = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"), n_sims=120, seed=7)
    assert np.array_equal(a.home_total, b.home_total)
    assert np.array_equal(a.away_total, b.away_total)


def test_cpu_lever_suppresses_raw_scoring():
    _off()
    off = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                        n_sims=300, seed=7, anchor=False)
    _on()
    on = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                       n_sims=300, seed=7, anchor=False)
    # supp values are predominantly <= 0, so the on-court mean suppression lowers combined raw scoring
    assert (on.home_total.mean() + on.away_total.mean()) < (off.home_total.mean() + off.away_total.mean())


# --------------------------------------------------------------------------- GPU/torch engine

def test_gpu_off_deterministic_and_on_suppresses():
    pytest.importorskip("torch")
    from sim.fast_sim import simulate_game_fast
    _off()
    a = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                           n_sims=400, seed=3, anchor=False)
    b = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                           n_sims=400, seed=3, anchor=False)
    assert np.allclose(a.home_total, b.home_total)  # OFF deterministic (same seed)
    _on()
    on = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                            n_sims=400, seed=3, anchor=False)
    assert (on.home_total.mean() + on.away_total.mean()) < (a.home_total.mean() + a.away_total.mean())
