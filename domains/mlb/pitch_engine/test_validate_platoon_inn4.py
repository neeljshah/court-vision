"""python -m pytest domains/mlb/pitch_engine/test_validate_platoon_inn4.py -q

Fast: synthetic pitch/PA frames only -- no parquet load (the full walk-forward
gate run is the CLI)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel
from domains.mlb.pitch_engine.outcome_platoon import PlatoonOutcomeModel
from domains.mlb.pitch_engine.selection import SelectionModel
from domains.mlb.pitch_engine.game_sim import simulate_game
from domains.mlb.pitch_engine.test_game_sim_v2 import _trans
from domains.mlb.pitch_engine.validate_platoon_inn4 import (
    _slot_dists_platoon, _fit, run, NAMED_BUCKET, _REGRESSION_EPS,
)


def _tiny_models():
    pa_rows = []
    for b, evt in [(1, "HR"), (2, "K")]:
        for _ in range(60):
            pa_rows.append({"batter": b, "pclass": "FB", "pa_evt": evt})
    tiers = BatterTiers.fit(pd.DataFrame(pa_rows))
    pitch_rows = []
    for _ in range(200):
        pitch_rows.append({"pclass": "FB", "zbucket": "IZ", "cidx": 0, "batter": 1,
                           "outcome": "called_strike", "pidx": 0,
                           "pitcher": 9, "bbucket": 0})
    pf = pd.DataFrame(pitch_rows)
    base = OutcomeModel.fit(pf, tiers)
    plat = PlatoonOutcomeModel.fit(pf, tiers, base)
    sel = SelectionModel.fit(pf)
    return sel, plat, tiers


def test_slot_dists_platoon_valid_probability_rows():
    sel, plat, tiers = _tiny_models()
    stand = {1: "R", 2: "L"}; throw = {9: "R"}
    m = _slot_dists_platoon(sel, plat, tiers, [1, 2], 9, throw, stand)
    assert m.shape == (9, 8)
    assert np.allclose(m.sum(axis=1), 1.0, atol=1e-6)
    assert (m >= 0).all()


def test_slot_dists_platoon_feeds_simulate_game():
    """The platoon-conditioned matrix is a drop-in for v1's simulate_game (the
    whole point of the seam: game_sim.py stays untouched)."""
    sel, plat, tiers = _tiny_models()
    stand = {1: "R", 2: "L"}; throw = {9: "R"}
    pa = _slot_dists_platoon(sel, plat, tiers, [1, 2], 9, throw, stand)
    h, a = simulate_game(pa, pa, _trans(), n=50, seed=3)
    assert len(h) == 50 and len(a) == 50


def test_module_wired_named_bucket_and_pieces():
    assert NAMED_BUCKET == "inn4|m2"
    assert _REGRESSION_EPS > 0
    assert callable(_fit)
    assert callable(run)
