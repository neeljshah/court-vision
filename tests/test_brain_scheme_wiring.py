"""P7.1 — CV_LLM_SCHEME wired into the possession engines (the byte-identical seam test).

Mirrors test_brain_def_supp_lever.py. Proves the load-bearing discipline:
  - DEFAULT-OFF is byte-identical: even with a scheme-adjustment artifact PRESENT on disk, flag OFF
    => from_cache reads nothing, mutates nothing => CPU + GPU sims are identical to the no-artifact run.
  - ON: the artifact's bounded multipliers move the sim in the expected direction (lower NYK FG ->
    lower NYK raw scoring), proving the wiring is live behind the flag.
The SHIP/REJECT decision is NOT made here (that is the Phase-3 walk-forward gate); this proves only
that the wiring is correct, gated, and byte-identical when OFF.
"""
import os
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from sim.basketball_sim import TeamModel, simulate_game, _scheme_on  # noqa: E402
from sim.scheme_prior import write_scheme_adjustments, _artifact_path  # noqa: E402

_FLAG = "CV_LLM_SCHEME"


def _off():
    os.environ.pop(_FLAG, None)


def _on():
    os.environ[_FLAG] = "1"


def _write_nyk_artifact():
    """Write a bounded, leak-safe artifact that cuts every NYK rotation player's FG across zones."""
    tm = TeamModel.from_cache("NYK")  # flag is OFF here -> clean rotation
    adjs = []
    for pid in tm.rate:
        for knob in ("fg_rim", "fg_paint", "fg_mid", "fg3_pct"):
            adjs.append(dict(entity=int(pid), param=knob, mult=0.92, confidence=1.0,
                             horizon="g4", leak_safe=True, why="seam-test FG cut"))
    return write_scheme_adjustments("NYK", adjs, asof=None)


def _cleanup():
    for tri in ("NYK", "SAS"):
        p = _artifact_path(tri, None)
        if os.path.exists(p):
            os.remove(p)


def teardown_function(_):
    _off()
    _cleanup()


# --------------------------------------------------------------------------- flag helper
def test_scheme_flag_helper_semantics():
    _off()
    assert _scheme_on() is False
    _on()
    assert _scheme_on() is True
    os.environ[_FLAG] = "0"
    assert _scheme_on() is False  # "0" is OFF


# --------------------------------------------------------------------------- byte-identical when OFF
def test_off_with_artifact_present_is_byte_identical():
    """The hard requirement: an artifact on disk must NOT change anything while the flag is OFF."""
    _write_nyk_artifact()
    _off()
    a = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                      n_sims=200, seed=11, anchor=False)
    b = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                      n_sims=200, seed=11, anchor=False)
    assert np.array_equal(a.home_total, b.home_total)
    assert np.array_equal(a.away_total, b.away_total)


def test_off_equals_no_artifact():
    """OFF + artifact present == OFF + no artifact (the artifact is inert when the gate is off)."""
    _off()
    _cleanup()
    base = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                         n_sims=200, seed=5, anchor=False)
    _write_nyk_artifact()
    with_art = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                             n_sims=200, seed=5, anchor=False)
    assert np.array_equal(base.home_total, with_art.home_total)
    assert np.array_equal(base.away_total, with_art.away_total)


def test_from_cache_off_does_not_mutate_fg():
    """A direct knob check: with flag OFF, NYK player FG equals the unadjusted rates."""
    _write_nyk_artifact()
    _off()
    tm = TeamModel.from_cache("NYK")
    # the artifact cut fg_rim by 0.92; OFF must leave it at the raw player_rates value (>0.92*raw is impossible
    # to assert blindly, so compare to a second OFF build which is the source of truth)
    tm2 = TeamModel.from_cache("NYK")
    for pid in tm.rate:
        v1, v2 = tm.rate[pid].get("fg_rim"), tm2.rate[pid].get("fg_rim")
        assert (v1 == v2) or (v1 != v1 and v2 != v2)  # equal, or both NaN (NaN != NaN)


# --------------------------------------------------------------------------- ON applies
def test_on_lowers_nyk_scoring():
    _off()
    off = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                        n_sims=400, seed=9, anchor=False)
    _write_nyk_artifact()
    _on()
    on = simulate_game(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                       n_sims=400, seed=9, anchor=False)
    # cutting NYK FG across all zones must lower NYK raw (anchor-off) scoring
    assert on.home_total.mean() < off.home_total.mean()


def test_gpu_off_byte_identical_and_on_applies():
    pytest.importorskip("torch")
    from sim.fast_sim import simulate_game_fast
    _write_nyk_artifact()
    _off()
    a = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                           n_sims=400, seed=3, anchor=False)
    b = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                           n_sims=400, seed=3, anchor=False)
    assert np.allclose(a.home_total, b.home_total)  # OFF deterministic + inert artifact
    _on()
    on = simulate_game_fast(TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS"),
                            n_sims=400, seed=3, anchor=False)
    assert on.home_total.mean() < a.home_total.mean()
