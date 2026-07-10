"""python -m pytest domains/mlb/pitch_engine/test_game_sim_v3.py -q"""
from __future__ import annotations

import numpy as np

from domains.mlb.pitch_engine.game_sim import GameStart
from domains.mlb.pitch_engine.game_sim_v3 import simulate_game_v3
from domains.mlb.pitch_engine import bullpen as bp
from domains.mlb.pitch_engine.test_game_sim_v2 import _trans, _removal


def _dists_v3():
    """[9,8] starter dist + [N_BUCKET,N_LEAD,8] COMPOSITION-mixed reliever dist
    (no slot axis -- the v3 simplification)."""
    sp = np.tile(np.array([0.7, 0.1, 0.05, 0.0, 0.1, 0.03, 0.01, 0.01]), (9, 1))
    rp = np.tile(sp[0], (bp.N_BUCKET, bp.N_LEAD, 1))
    return sp, rp


def test_runs_and_deterministic():
    tr = _trans(); rem = _removal(); sp, rp = _dists_v3()
    h1, a1 = simulate_game_v3(sp, sp, rp, rp, tr, rem, n=200, seed=7)
    h2, a2 = simulate_game_v3(sp, sp, rp, rp, tr, rem, n=200, seed=7)
    assert h1.shape == (200,)
    assert np.array_equal(h1, h2) and np.array_equal(a1, a2)   # deterministic
    assert (h1 >= 0).all() and (a1 >= 0).all()


def test_snapshot_uses_reliever_regime():
    """At inning-7 snapshot with reliever dist == all-strikeout, no further runs
    can score for the side facing the pen (starter is pre-resolved out)."""
    tr = _trans(); rem = _removal()
    sp, _ = _dists_v3()
    rp_out = np.zeros((bp.N_BUCKET, bp.N_LEAD, 8)); rp_out[:, :, 0] = 1.0   # all OUT
    h, a = simulate_game_v3(sp, sp, rp_out, rp_out, tr, rem, n=300, seed=3,
                            start=GameStart(inning=7, half=0, home_score=1, away_score=0))
    assert a.mean() < 0.6
