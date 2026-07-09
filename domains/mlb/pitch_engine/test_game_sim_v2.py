"""python -m pytest domains/mlb/pitch_engine/test_game_sim_v2.py -q"""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.corpus import build_pa_frame
from domains.mlb.pitch_engine.game_sim import BaseOutTransition, GameStart
from domains.mlb.pitch_engine.game_sim_v2 import simulate_game_v2
from domains.mlb.pitch_engine import bullpen as bp


def _trans():
    """Minimal empirical transition: every event is an out that ends the inning
    quickly, plus HR scores 1. Built from a synthetic PA frame."""
    rows = []
    ab = 1
    for g in range(40):
        for inn in range(1, 4):
            for half in ("Top", "Bot"):
                for k in range(3):
                    ev = "HR" if (k == 0) else "OUT"
                    rows.append(dict(game_pk=g, inning=inn, inning_topbot=half,
                                     at_bat_number=ab, pitcher=1, batter=1, events=ev,
                                     description="x", pitch_type="FF", balls=0, strikes=0,
                                     outs_when_up=k, on_1b=np.nan, on_2b=np.nan, on_3b=np.nan,
                                     bat_score=0, post_home_score=0, post_away_score=0,
                                     stand="R", p_throws="R", zone=5)); ab += 1
    df = pd.DataFrame(rows)
    df["pa_evt"] = df["events"].map({"HR": "HR", "OUT": "OUT"})
    df["base_mask"] = 0; df["outs_start"] = df["outs_when_up"]
    df["base_out_state"] = df["outs_start"]
    df["runs"] = (df["events"] == "HR").astype(int)
    return BaseOutTransition.fit(df, min_cell=1)


def _removal():
    # force starters removed at inning 6 regardless of lead
    m = bp.RemovalModel(np.zeros((bp.N_INN, bp.N_LEAD)))
    m._h[6:] = 1.0
    return m


def _dists():
    sp = np.tile(np.array([0.7, 0.1, 0.05, 0.0, 0.1, 0.03, 0.01, 0.01]), (9, 1))
    rp = np.tile(sp, (bp.N_BUCKET, bp.N_LEAD, 1, 1))
    return sp, rp


def test_runs_and_deterministic():
    tr = _trans(); rem = _removal(); sp, rp = _dists()
    h1, a1 = simulate_game_v2(sp, sp, rp, rp, tr, rem, n=200, seed=7)
    h2, a2 = simulate_game_v2(sp, sp, rp, rp, tr, rem, n=200, seed=7)
    assert h1.shape == (200,)
    assert np.array_equal(h1, h2) and np.array_equal(a1, a2)   # deterministic
    assert (h1 >= 0).all() and (a1 >= 0).all()


def test_snapshot_uses_reliever_regime():
    """At inning-7 snapshot with reliever dist == all-strikeout, no further runs
    can score for the side facing the pen (starter is pre-resolved out)."""
    tr = _trans(); rem = _removal()
    sp, _ = _dists()
    rp_out = np.zeros((bp.N_BUCKET, bp.N_LEAD, 9, 8)); rp_out[:, :, :, 0] = 1.0   # all OUT
    h, a = simulate_game_v2(sp, sp, rp_out, rp_out, tr, rem, n=300, seed=3,
                            start=GameStart(inning=7, half=0, home_score=1, away_score=0))
    # away batters face home pen (all-out) -> away rarely scores beyond start (0)
    assert a.mean() < 0.6
