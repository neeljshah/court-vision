"""Per-file tests for pitch_engine.outcome_platoon -- same-hand cell + backoff."""
import numpy as np
import pandas as pd

from domains.mlb.pitch_engine.outcome import BatterTiers, OutcomeModel, N_OUT
from domains.mlb.pitch_engine.outcome_platoon import (
    PlatoonOutcomeModel, assemble_platoon,
)
from domains.mlb.pitch_engine.selection import SelectionModel


def _pa_frame():
    rows = []
    for b, evt in [(1, "HR"), (2, "K"), (3, "1B")]:
        for _ in range(60):
            rows.append({"batter": b, "pclass": "FB", "pa_evt": evt})
    return pd.DataFrame(rows)


def _pitch_frame(n_same=200, n_opp=50):
    """FB in-zone count 0-0: same-handed mostly called_strike, opposite mostly ball
    -- a deliberately separated signal so a covered same_hand cell differs from
    backoff, and a thin cell (n_opp<MIN_CELL=40? no, 50>=40) still resolves."""
    rows = []
    for _ in range(n_same):
        rows.append({"pclass": "FB", "zbucket": "IZ", "cidx": 0, "batter": 1,
                     "outcome": "called_strike", "pidx": 0})
    for _ in range(n_opp):
        rows.append({"pclass": "FB", "zbucket": "IZ", "cidx": 0, "batter": 1,
                     "outcome": "ball", "pidx": 1})
    return pd.DataFrame(rows)


def test_platoon_cell_normalized_and_differs_from_backoff():
    t = BatterTiers.fit(_pa_frame())
    pf = _pitch_frame()
    base = OutcomeModel.fit(pf, t)
    pm = PlatoonOutcomeModel.fit(pf, t, base)
    tier = t.tier(1, 0)
    p_same = pm.outcome_probs(0, 0, 0, tier, same_hand=1)
    p_opp = pm.outcome_probs(0, 0, 0, tier, same_hand=0)
    assert abs(p_same.sum() - 1.0) < 1e-9
    assert abs(p_opp.sum() - 1.0) < 1e-9
    assert len(p_same) == N_OUT
    # same_hand=1 saw only called_strike -> dominant mass there
    assert p_same.argmax() == 1
    # opposite-hand saw only ball -> dominant mass there, and differs from same_hand
    assert p_opp.argmax() == 0
    assert not np.allclose(p_same, p_opp)


def test_thin_cell_backs_off_to_base():
    t = BatterTiers.fit(_pa_frame())
    pf = _pitch_frame()
    base = OutcomeModel.fit(pf, t)
    pm = PlatoonOutcomeModel.fit(pf, t, base)
    tier = t.tier(1, 0)
    # (class=1, zone=1, cidx=11, tier) never seen at all for any same_hand -> base backoff
    p = pm.outcome_probs(1, 1, 11, tier, same_hand=1)
    base_p = base.outcome_probs(1, 1, 11, tier)
    assert np.allclose(p, base_p)


def test_assemble_platoon_is_valid_pa_distribution():
    t = BatterTiers.fit(_pa_frame())
    pf = _pitch_frame()
    sel = SelectionModel.fit(
        pd.DataFrame({"pitcher": [7] * 250, "cidx": pf["cidx"].tolist(),
                     "pidx": pf["pidx"].tolist(), "bbucket": [0] * 250,
                     "pclass": pf["pclass"].tolist(),
                     "zbucket": pf["zbucket"].tolist()}))
    base = OutcomeModel.fit(pf, t)
    pm = PlatoonOutcomeModel.fit(pf, t, base)
    dist = assemble_platoon(sel, pm, t, pitcher=7, batter=1, pidx=0, bbucket=0)
    assert abs(dist.sum() - 1.0) < 1e-6
    assert len(dist) == 8
    assert (dist >= 0).all()
